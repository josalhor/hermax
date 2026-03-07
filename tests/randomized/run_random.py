from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

from tests.fuzzing.compare import WCNFCompare
from tests.fuzzing.model import WeightedCNF
from tests.fuzzing.solver_registry import solver_ids

STATUS_COLUMNS = ["PASS", "SKIP", "ERR", "CRASH", "TIMEOUT"]


def _write_case(base_dir: Path, case_id: str, wcnf: WeightedCNF, kind: str = "case") -> tuple[Path, Path]:
    case_dir = base_dir / "cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    json_path = case_dir / f"{case_id}.{kind}.json"
    wcnf_path = case_dir / f"{case_id}.{kind}.wcnf"
    json_path.write_text(json.dumps(wcnf.to_dict(), indent=2), encoding="utf-8")
    wcnf_path.write_text(wcnf.to_wcnf(), encoding="utf-8")
    return json_path, wcnf_path


def _classify_cell(rec: dict) -> str:
    fault = rec.get("fault")
    status_name = str(rec.get("status_name") or "").upper()
    if rec.get("timed_out") or fault == "TIMEOUT":
        return "TIMEOUT"
    if fault == "CRASH":
        return "CRASH"
    if status_name in {"SKIP", "SKIPPED"} or fault == "SKIP" or str(fault).startswith("SKIP_"):
        return "SKIP"
    if fault:
        return "ERR"
    return "PASS"


def _render_matrix_line(parts: list[str], widths: list[int]) -> str:
    cells = [parts[i].ljust(widths[i]) for i in range(len(parts))]
    return " | ".join(cells)


def _progress_bar(done: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return "[" + ("?" * width) + "]"
    done = max(0, min(done, total))
    fill = int((done / total) * width)
    return "[" + ("#" * fill) + ("-" * (width - fill)) + "]"


def _interactive_paint(text: str) -> None:
    if os.isatty(1):
        print("\x1b[2J\x1b[H", end="")
    print(text, end="", flush=True)


def _load_wcnf(path: Path) -> WeightedCNF:
    try:
        from pysat.formula import WCNF
    except Exception as exc:
        raise RuntimeError("python-sat is required for tests.randomized (missing pysat.formula.WCNF).") from exc

    w = WCNF(from_file=str(path))
    hard = [[int(l) for l in cl] for cl in w.hard]
    soft = [([int(l) for l in cl], int(w.wght[i])) for i, cl in enumerate(w.soft)]
    nvars = int(w.nv)
    for cl in hard:
        for lit in cl:
            nvars = max(nvars, abs(int(lit)))
    for cl, _wt in soft:
        for lit in cl:
            nvars = max(nvars, abs(int(lit)))
    return WeightedCNF(hard=hard, soft=soft, nvars=nvars)


def _pick_assumptions(rng: random.Random, nvars: int, args: argparse.Namespace) -> list[int]:
    if not args.pick_assumptions or nvars <= 0:
        return []
    ub = int(nvars * 1.5) if args.add_outside_range else nvars
    ub = max(1, ub)
    k = rng.randint(0, min(args.num_random_vars_assum, ub))
    if k <= 0:
        return []
    vars_ = rng.sample(range(1, ub + 1), k=k)
    return [v if rng.getrandbits(1) else -v for v in vars_]


def _mutate_soft_weights(
    rng: random.Random, base: WeightedCNF, args: argparse.Namespace
) -> tuple[list[tuple[list[int], int]], list[dict]]:
    out = [([int(x) for x in cl], int(w)) for cl, w in base.soft]
    if not args.change_weight_soft or not out:
        return out, []

    k = min(args.num_random_vars_weight, len(out))
    if k <= 0:
        return out, []

    idxs = rng.sample(range(len(out)), k=k)
    changes: list[dict] = []
    pct = float(args.weight_pct_delta)

    for idx in idxs:
        cl, cur_w = out[idx]
        cur_w = max(int(args.weight_min), int(cur_w))
        lo = max(int(args.weight_min), int(math.ceil(cur_w * (1.0 - pct))))
        hi = max(lo, int(math.floor(cur_w * (1.0 + pct))))
        new_w = int(rng.randint(lo, hi))
        flipped = False
        if args.weight_allow_flip and len(cl) == 1 and rng.random() < args.weight_flip_prob:
            cl = [-int(cl[0])]
            flipped = True
        out[idx] = (cl, new_w)
        changes.append(
            {
                "soft_idx": idx,
                "old_weight": int(cur_w),
                "new_weight": int(new_w),
                "flipped": flipped,
                "new_clause": [int(x) for x in cl],
            }
        )
    return out, changes


def _feature_tags(
    wcnf: WeightedCNF,
    source_path: Path,
    assumptions: list[int],
    changes: list[dict],
    args: argparse.Namespace,
) -> list[str]:
    tags: set[str] = {
        "random",
        f"source:{source_path.name}",
        "assumptions:enabled" if args.pick_assumptions else "assumptions:disabled",
        "weights_mutation:on" if args.change_weight_soft else "weights_mutation:off",
    }

    if assumptions:
        tags.add("assumptions:used")
    else:
        tags.add("assumptions:none")
    if args.add_outside_range:
        tags.add("assumptions:outside_range")

    if changes:
        tags.add("soft:weight_changed")
        tags.add(f"soft:weight_changed_count:{len(changes)}")
        if any(c["flipped"] for c in changes):
            tags.add("soft:unit_flipped")
    else:
        tags.add("soft:no_weight_changes")

    max_w = max((int(w) for _cl, w in wcnf.soft), default=1)
    if max_w == 1:
        tags.add("weights:unweighted")
    elif max_w <= 32:
        tags.add("weights:small")
    elif max_w <= 256:
        tags.add("weights:medium")
    elif max_w <= 65535:
        tags.add("weights:large")
    elif max_w <= (2**32):
        tags.add("weights:very_large")
    else:
        tags.add("weights:extreme")

    nvars = max(1, int(wcnf.nvars))
    h_ratio = len(wcnf.hard) / nvars
    s_ratio = len(wcnf.soft) / nvars
    tags.add("hard_ratio:low" if h_ratio <= 1.0 else ("hard_ratio:mid" if h_ratio <= 2.5 else "hard_ratio:high"))
    tags.add("soft_ratio:low" if s_ratio <= 2.5 else ("soft_ratio:mid" if s_ratio <= 4.5 else "soft_ratio:high"))
    return sorted(tags)


def _render_dashboard(
    *,
    start: float,
    args: argparse.Namespace,
    selected_solvers: list[str],
    solver_status_counts: dict[str, dict[str, int]],
    fault_counts: dict[str, int],
    feature_fault_counts: dict[str, int],
    skip_reason_counts: dict[str, int],
    cases_ran: int,
    total_faults: int,
    current_case: str,
    current_source: str,
    current_case_faults: int,
    phase: str,
    solver_progress: str,
    iter_progress: str,
    last_alert: str,
    out_dir: Path,
) -> str:
    elapsed = time.monotonic() - start
    header = [
        "Hermax Random Testing Dashboard",
        (
            f"cases={cases_ran} faults={total_faults} elapsed_s={elapsed:.1f} "
            f"per_solver_timeout={args.per_solver_timeout}s overall_timeout={args.overall_timeout}s"
        ),
        f"current_case={current_case} source={current_source} case_faults={current_case_faults}",
        f"phase={phase}",
        f"iter_progress={iter_progress}",
        f"solver_progress={solver_progress}",
        f"last_alert={last_alert}",
        f"out_dir={out_dir}",
        "",
    ]

    widths = [max(6, len("solver"))] + [max(7, len(c)) for c in STATUS_COLUMNS]
    for sid in selected_solvers:
        widths[0] = max(widths[0], len(sid))
        for i, col in enumerate(STATUS_COLUMNS, start=1):
            widths[i] = max(widths[i], len(str(solver_status_counts[sid][col])))

    table = []
    table.append(_render_matrix_line(["solver"] + STATUS_COLUMNS, widths))
    table.append(_render_matrix_line(["-" * widths[0]] + ["-" * w for w in widths[1:]], widths))
    for sid in selected_solvers:
        row = [sid] + [str(solver_status_counts[sid][c]) for c in STATUS_COLUMNS]
        table.append(_render_matrix_line(row, widths))

    fault_lines = ["", "Fault Totals:"]
    if fault_counts:
        for fault, cnt in sorted(fault_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:12]:
            fault_lines.append(f"  {fault}: {cnt}")
    else:
        fault_lines.append("  none")

    feature_lines = ["", "Top Error-Trigger Features:"]
    if feature_fault_counts:
        for tag, cnt in sorted(feature_fault_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:15]:
            feature_lines.append(f"  {tag}: {cnt}")
    else:
        feature_lines.append("  none")

    skip_lines = ["", "Top Skip Reasons:"]
    if skip_reason_counts:
        for reason, cnt in sorted(skip_reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]:
            skip_lines.append(f"  {reason}: {cnt}")
    else:
        skip_lines.append("  none")

    return "\n".join(header + table + fault_lines + feature_lines + skip_lines) + "\n"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Random real-instance MaxSAT testing (dataset-based)")
    p.add_argument("--seed", type=int, default=1338)
    p.add_argument("--iterations", type=int, default=200)
    p.add_argument("--forever", action="store_true", help="run without iteration limit")
    p.add_argument("--batch", type=int, default=20, help="cases to run before picking a new source instance")
    p.add_argument("--per-solver-timeout", type=float, default=20.0)
    p.add_argument("--overall-timeout", type=float, default=3600.0, help="0 disables overall timeout")
    p.add_argument("--solvers", default=",".join(solver_ids()))
    p.add_argument("--data-dir", default="tests/data")
    p.add_argument("--interactive", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--all-failed-ignore", default="OpenWBO-PartMSU3")
    p.add_argument("--out-dir", default="tests/_random")

    p.add_argument("--pick-assumptions", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--num-random-vars-assum", type=int, default=1)
    p.add_argument("--add-outside-range", action=argparse.BooleanOptionalAction, default=False)

    p.add_argument("--change-weight-soft", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--num-random-vars-weight", type=int, default=4)
    p.add_argument("--weight-pct-delta", type=float, default=0.5)
    p.add_argument("--weight-min", type=int, default=1)
    p.add_argument("--weight-allow-flip", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--weight-flip-prob", type=float, default=0.5)
    return p.parse_args()


def _list_data_instances(data_dir: Path) -> list[Path]:
    files = sorted(set(data_dir.glob("*.wcnf")) | set(data_dir.glob("**/*.wcnf")))
    return [p for p in files if p.is_file()]


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    selected_solvers = [s.strip() for s in args.solvers.split(",") if s.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir = out_dir / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    anomaly_dir = out_dir / "anomaly_logs"
    anomaly_dir.mkdir(parents=True, exist_ok=True)
    live_dashboard_path = out_dir / "live_dashboard.txt"

    data_dir = Path(args.data_dir)
    instance_paths = _list_data_instances(data_dir)
    if not instance_paths:
        raise RuntimeError(f"No .wcnf files found under {data_dir}")

    cfg = {
        "seed": args.seed,
        "iterations": args.iterations,
        "forever": args.forever,
        "batch": args.batch,
        "per_solver_timeout": args.per_solver_timeout,
        "overall_timeout": args.overall_timeout,
        "solvers": selected_solvers,
        "data_dir": str(data_dir),
        "interactive": args.interactive,
        "all_failed_ignore": args.all_failed_ignore,
        "pick_assumptions": args.pick_assumptions,
        "num_random_vars_assum": args.num_random_vars_assum,
        "add_outside_range": args.add_outside_range,
        "change_weight_soft": args.change_weight_soft,
        "num_random_vars_weight": args.num_random_vars_weight,
        "weight_pct_delta": args.weight_pct_delta,
        "weight_min": args.weight_min,
        "weight_allow_flip": args.weight_allow_flip,
        "weight_flip_prob": args.weight_flip_prob,
    }
    (out_dir / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    start = time.monotonic()
    deadline = None if args.overall_timeout <= 0 else (start + args.overall_timeout)

    i = 0
    total_faults = 0
    solver_status_counts = {sid: {c: 0 for c in STATUS_COLUMNS} for sid in selected_solvers}
    fault_counts: dict[str, int] = {}
    feature_fault_counts: dict[str, int] = {}
    skip_reason_counts: dict[str, int] = {}
    last_case_id = "-"
    last_source = "-"
    last_case_faults = 0
    phase = "init"
    solver_progress = "-"
    last_alert = "-"
    ignored_for_all_failed = {s.strip() for s in args.all_failed_ignore.split(",") if s.strip()}
    cache: dict[Path, WeightedCNF] = {}

    if not args.interactive:
        print(
            f"[random] start seed={args.seed} solvers={len(selected_solvers)} "
            f"instances={len(instance_paths)} iterations={'inf' if args.forever else args.iterations} out_dir={out_dir}",
            flush=True,
        )

    current_base_path: Path | None = None
    batch_left = 0
    interrupted = False
    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                print("[random] overall timeout reached")
                break
            if not args.forever and i >= args.iterations:
                break

            if current_base_path is None or batch_left <= 0:
                current_base_path = rng.choice(instance_paths)
                batch_left = max(1, int(args.batch))
                if not args.interactive:
                    print(f"[random] selected source={current_base_path}", flush=True)

            base = cache.get(current_base_path)
            if base is None:
                base = _load_wcnf(current_base_path)
                cache[current_base_path] = base

            assumptions = _pick_assumptions(rng, base.nvars, args)
            soft_mut, changes = _mutate_soft_weights(rng, base, args)
            wcnf = WeightedCNF(
                hard=[[int(x) for x in cl] for cl in base.hard],
                soft=[([int(x) for x in cl], int(w)) for cl, w in soft_mut],
                nvars=int(base.nvars),
            )

            case_id = f"{int(start)}_{i:07d}_{rng.randrange(10**9):09d}__{current_base_path.stem}"
            case_json, _case_wcnf = _write_case(out_dir, case_id, wcnf)

            total_iters = args.iterations if not args.forever else 0
            iter_progress = (
                f"{_progress_bar(i, total_iters)} {i}/{total_iters}"
                if total_iters > 0
                else f"{i} cases"
            )
            if not args.interactive:
                print(f"[random] begin case={case_id} source={current_base_path.name} progress={iter_progress}", flush=True)

            def _on_progress(evt: dict) -> None:
                nonlocal phase, solver_progress
                phase = str(evt.get("phase") or phase)
                idx = int(evt.get("solver_idx") or 0)
                tot = int(evt.get("solver_total") or 0)
                sid = str(evt.get("solver") or "-")
                done = idx - 1 if evt.get("event") == "start" else idx
                solver_progress = f"{_progress_bar(done, tot)} {idx}/{tot} {sid}"
                if args.interactive:
                    dashboard = _render_dashboard(
                        start=start,
                        args=args,
                        selected_solvers=selected_solvers,
                        solver_status_counts=solver_status_counts,
                        fault_counts=fault_counts,
                        feature_fault_counts=feature_fault_counts,
                        skip_reason_counts=skip_reason_counts,
                        cases_ran=i,
                        total_faults=total_faults,
                        current_case=last_case_id if last_case_id != "-" else case_id,
                        current_source=last_source if last_source != "-" else current_base_path.name,
                        current_case_faults=last_case_faults,
                        phase=phase,
                        solver_progress=solver_progress,
                        iter_progress=iter_progress,
                        last_alert=last_alert,
                        out_dir=out_dir,
                    )
                    _interactive_paint(dashboard)
                    live_dashboard_path.write_text(dashboard, encoding="utf-8")
                elif evt.get("event") == "start":
                    print(f"[solve] case={case_id} solver={sid} ({idx}/{tot})", flush=True)

            comparator = WCNFCompare(
                out_dir=out_dir,
                per_solver_timeout_s=args.per_solver_timeout,
                run_id=case_id,
                progress_cb=_on_progress,
            )
            phase = "solve"
            _outcomes, summary = comparator.compare_case(
                wcnf, case_json, selected_solvers, assumptions=assumptions
            )
            solver_progress = (
                f"{_progress_bar(len(selected_solvers), len(selected_solvers))} "
                f"{len(selected_solvers)}/{len(selected_solvers)} done"
            )

            summary["random"] = {
                "source_path": str(current_base_path),
                "assumptions": [int(x) for x in assumptions],
                "weight_changes": changes,
            }
            (summaries_dir / f"{case_id}.summary.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )

            case_features = _feature_tags(wcnf, current_base_path, assumptions, changes, args)
            for rec in summary["results"]:
                cell = _classify_cell(rec)
                solver_status_counts[rec["solver"]][cell] += 1
                if rec.get("fault") and not str(rec.get("fault")).startswith("SKIP_"):
                    fault = str(rec["fault"])
                    fault_counts[fault] = fault_counts.get(fault, 0) + 1
                    for tag in case_features:
                        feature_fault_counts[tag] = feature_fault_counts.get(tag, 0) + 1
                if str(rec.get("fault")).startswith("SKIP_"):
                    reason = str(rec.get("error") or rec.get("fault")).splitlines()[0][:120]
                    skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1

            case_faults = [r for r in summary["results"] if r.get("fault") and not str(r.get("fault")).startswith("SKIP_")]
            total_faults += len(case_faults)
            last_case_id = case_id
            last_source = current_base_path.name
            last_case_faults = len(case_faults)

            considered = [
                r for r in summary["results"]
                if r.get("solver") not in ignored_for_all_failed and _classify_cell(r) != "SKIP"
            ]
            considered_statuses = {_classify_cell(r) for r in considered}
            all_failed = bool(considered) and considered_statuses.issubset({"ERR", "CRASH", "TIMEOUT"})
            if all_failed:
                fault_hist: dict[str, int] = {}
                delta_by_solver: dict[str, int | None] = {}
                for r in considered:
                    f = str(r.get("fault") or "UNKNOWN")
                    fault_hist[f] = fault_hist.get(f, 0) + 1
                    osolver = r.get("o_solver")
                    omodel = r.get("o_model")
                    delta_by_solver[str(r.get("solver"))] = (
                        (int(osolver) - int(omodel))
                        if osolver is not None and omodel is not None
                        else None
                    )
                anomaly = {
                    "kind": "ALL_FAILED",
                    "run_id": case_id,
                    "timestamp_epoch_s": time.time(),
                    "ignored_solvers": sorted(ignored_for_all_failed),
                    "selected_solvers": selected_solvers,
                    "source_path": str(current_base_path),
                    "case_features": case_features,
                    "considered_solvers": [r.get("solver") for r in considered],
                    "considered_statuses": {r.get("solver"): _classify_cell(r) for r in considered},
                    "considered_fault_histogram": dict(sorted(fault_hist.items(), key=lambda kv: (-kv[1], kv[0]))),
                    "considered_o_solver_minus_o_model": delta_by_solver,
                    "case_summary": summary,
                    "paths": {
                        "case_json": str(case_json),
                        "summary_json": str(summaries_dir / f"{case_id}.summary.json"),
                        "fault_logs_dir": str(out_dir / "fault_logs"),
                    },
                    "env": {
                        "python_executable": sys.executable,
                        "venv": os.environ.get("VIRTUAL_ENV", ""),
                        "ld_library_path": os.environ.get("LD_LIBRARY_PATH", ""),
                    },
                }
                apath = anomaly_dir / f"{case_id}__ALL_FAILED.json"
                apath.write_text(json.dumps(anomaly, indent=2), encoding="utf-8")
                last_alert = str(apath)
                print(f"[anomaly] all considered solvers failed on {case_id}; diagnostics: {apath}")

            if args.interactive:
                dashboard = _render_dashboard(
                    start=start,
                    args=args,
                    selected_solvers=selected_solvers,
                    solver_status_counts=solver_status_counts,
                    fault_counts=fault_counts,
                    feature_fault_counts=feature_fault_counts,
                    skip_reason_counts=skip_reason_counts,
                    cases_ran=i + 1,
                    total_faults=total_faults,
                    current_case=last_case_id,
                    current_source=last_source,
                    current_case_faults=last_case_faults,
                    phase=phase,
                    solver_progress=solver_progress,
                    iter_progress=iter_progress,
                    last_alert=last_alert,
                    out_dir=out_dir,
                )
                _interactive_paint(dashboard)
                live_dashboard_path.write_text(dashboard, encoding="utf-8")
            else:
                print(
                    f"[random] case={case_id} source={current_base_path.name} assumps={len(assumptions)} "
                    f"w_changes={len(changes)} results={len(summary['results'])} faults={len(case_faults)} "
                    f"o_min={summary.get('o_min')} progress={iter_progress} solver={solver_progress}",
                    flush=True,
                )

            i += 1
            batch_left -= 1
            phase = "idle"
    except KeyboardInterrupt:
        interrupted = True
        phase = "interrupted"
        print("\n[random] interrupted by user (Ctrl+C); writing final summary...")

    final = {
        "cases_ran": i,
        "total_fault_events": total_faults,
        "elapsed_s": round(time.monotonic() - start, 3),
        "solvers": selected_solvers,
        "seed": args.seed,
        "matrix": solver_status_counts,
        "fault_totals": fault_counts,
        "feature_fault_totals": dict(sorted(feature_fault_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "skip_reason_totals": dict(sorted(skip_reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "interrupted": interrupted,
    }
    (out_dir / "final_summary.json").write_text(json.dumps(final, indent=2), encoding="utf-8")

    if args.interactive:
        dashboard = _render_dashboard(
            start=start,
            args=args,
            selected_solvers=selected_solvers,
            solver_status_counts=solver_status_counts,
            fault_counts=fault_counts,
            feature_fault_counts=feature_fault_counts,
            skip_reason_counts=skip_reason_counts,
            cases_ran=i,
            total_faults=total_faults,
            current_case=last_case_id,
            current_source=last_source,
            current_case_faults=last_case_faults,
            phase=phase,
            solver_progress=solver_progress,
            iter_progress=f"{_progress_bar(i, args.iterations)} {i}/{args.iterations}" if not args.forever else f"{i} cases",
            last_alert=last_alert,
            out_dir=out_dir,
        )
        _interactive_paint(dashboard)
        live_dashboard_path.write_text(dashboard, encoding="utf-8")

    print(json.dumps(final, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
