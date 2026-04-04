from __future__ import annotations

import argparse
import os
import json
import random
import sys
import time
from pathlib import Path

from tests.fuzzing.compare import WCNFCompare
from tests.fuzzing.model import WeightedCNF
from tests.fuzzing.reducer import DeltaReducer, TargetFault
from tests.fuzzing.regression import regression_cases
from tests.fuzzing.solver_registry import solver_ids
from tests.fuzzing.wcnfuzz import WCNFuzz

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


def _is_tautology(clause: list[int]) -> bool:
    s = set(int(x) for x in clause)
    return any((-x) in s for x in s)


def _feature_tags(wcnf: WeightedCNF, case_id: str, reg_name: str | None) -> list[str]:
    tags: set[str] = set()
    if reg_name is not None:
        tags.add(f"regression:{reg_name}")
    else:
        tags.add("generated")

    if any(len(cl) == 0 for cl in wcnf.hard):
        tags.add("hard:empty_clause")
    if any(len(cl) == 0 for cl, _w in wcnf.soft):
        tags.add("soft:empty_clause")
    if any(_is_tautology(cl) for cl in wcnf.hard):
        tags.add("hard:tautology")
    if any(_is_tautology(cl) for cl, _w in wcnf.soft):
        tags.add("soft:tautology")
    if any(len(cl) == 1 for cl, _w in wcnf.soft):
        tags.add("soft:unit")

    all_sizes = [len(cl) for cl in wcnf.hard] + [len(cl) for cl, _w in wcnf.soft]
    if all_sizes:
        avg_size = sum(all_sizes) / len(all_sizes)
        if avg_size <= 1.5:
            tags.add("shape:mostly_unit")
        elif avg_size <= 2.5:
            tags.add("shape:mostly_binary")
        elif avg_size <= 3.5:
            tags.add("shape:mostly_ternary")
        else:
            tags.add("shape:large_clauses")

    soft_weights = [int(w) for _cl, w in wcnf.soft]
    if soft_weights:
        max_w = max(soft_weights)
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
    if h_ratio <= 1.0:
        tags.add("hard_ratio:low")
    elif h_ratio <= 2.5:
        tags.add("hard_ratio:mid")
    else:
        tags.add("hard_ratio:high")

    if s_ratio <= 2.5:
        tags.add("soft_ratio:low")
    elif s_ratio <= 4.5:
        tags.add("soft_ratio:mid")
    else:
        tags.add("soft_ratio:high")

    if "__reduced" in case_id:
        tags.add("reduced")

    return sorted(tags)


def _render_matrix_line(parts: list[str], widths: list[int]) -> str:
    cells = [parts[i].ljust(widths[i]) for i in range(len(parts))]
    return " | ".join(cells)


def _progress_bar(done: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return "[" + ("?" * width) + "]"
    done = max(0, min(done, total))
    fill = int((done / total) * width)
    return "[" + ("#" * fill) + ("-" * (width - fill)) + "]"


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
    current_case_faults: int,
    phase: str,
    solver_progress: str,
    iter_progress: str,
    last_alert: str,
    out_dir: Path,
) -> str:
    elapsed = time.monotonic() - start
    header = [
        "Hermax Fuzzing Dashboard",
        (
            f"cases={cases_ran} faults={total_faults} elapsed_s={elapsed:.1f} "
            f"per_solver_timeout={args.per_solver_timeout}s overall_timeout={args.overall_timeout}s"
        ),
        f"current_case={current_case} case_faults={current_case_faults}",
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


def _interactive_paint(text: str) -> None:
    if os.isatty(1):
        print("\x1b[2J\x1b[H", end="")
    print(text, end="", flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Grammar-aware MaxSAT fuzzing + delta debugging")
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--iterations", type=int, default=200)
    p.add_argument("--forever", action="store_true", help="run without iteration limit")
    p.add_argument("--per-solver-timeout", type=float, default=20.0)
    p.add_argument("--overall-timeout", type=float, default=3600.0, help="0 disables overall timeout")
    p.add_argument("--solvers", default=",".join(solver_ids()))
    p.add_argument("--no-regression-first", action="store_true")
    p.add_argument("--reduce", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--interactive", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument(
        "--all-failed-ignore",
        default="OpenWBO-PartMSU3",
        help="comma-separated solvers ignored for ALL_FAILED anomaly detection",
    )
    p.add_argument("--out-dir", default="tests/_fuzzing")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    fuzz = WCNFuzz(rng)

    selected_solvers = [s.strip() for s in args.solvers.split(",") if s.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir = out_dir / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    anomaly_dir = out_dir / "anomaly_logs"
    anomaly_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "seed": args.seed,
        "iterations": args.iterations,
        "forever": args.forever,
        "per_solver_timeout": args.per_solver_timeout,
        "overall_timeout": args.overall_timeout,
        "solvers": selected_solvers,
        "reduce": args.reduce,
        "interactive": args.interactive,
        "all_failed_ignore": args.all_failed_ignore,
    }
    (out_dir / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    reg_queue = [] if args.no_regression_first else regression_cases()
    live_dashboard_path = out_dir / "live_dashboard.txt"

    start = time.monotonic()
    deadline = None if args.overall_timeout <= 0 else (start + args.overall_timeout)

    i = 0
    total_faults = 0
    solver_status_counts = {sid: {c: 0 for c in STATUS_COLUMNS} for sid in selected_solvers}
    fault_counts: dict[str, int] = {}
    feature_fault_counts: dict[str, int] = {}
    skip_reason_counts: dict[str, int] = {}
    last_case_id = "-"
    last_case_faults = 0
    phase = "init"
    solver_progress = "-"
    last_alert = "-"
    ignored_for_all_failed = {s.strip() for s in args.all_failed_ignore.split(",") if s.strip()}
    if not args.interactive:
        print(
            f"[fuzz] start seed={args.seed} solvers={len(selected_solvers)} "
            f"iterations={'inf' if args.forever else args.iterations} out_dir={out_dir}",
            flush=True,
        )

    interrupted = False
    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                print("[fuzz] overall timeout reached")
                break
            if not args.forever and i >= args.iterations:
                break

            case_id = f"{int(start)}_{i:07d}_{rng.randrange(10**9):09d}"
            reg_name: str | None = None
            if reg_queue:
                reg_name, wcnf = reg_queue.pop(0)
                case_id = f"{case_id}__reg__{reg_name}"
            else:
                wcnf = fuzz.generate()

            case_json, _case_wcnf = _write_case(out_dir, case_id, wcnf)

            total_iters = args.iterations if not args.forever else 0
            iter_progress = (
                f"{_progress_bar(i, total_iters)} {i}/{total_iters}"
                if total_iters > 0
                else f"{i} cases"
            )
            if not args.interactive:
                print(f"[fuzz] begin case={case_id} progress={iter_progress}", flush=True)

            def _on_progress(evt: dict) -> None:
                nonlocal phase, solver_progress
                phase = str(evt.get("phase") or phase)
                idx = int(evt.get("solver_idx") or 0)
                tot = int(evt.get("solver_total") or 0)
                sid = str(evt.get("solver") or "-")
                solver_progress = f"{_progress_bar(idx - 1 if evt.get('event') == 'start' else idx, tot)} {idx}/{tot} {sid}"
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
                    if evt.get("event") == "start":
                        print(f"[solve] case={case_id} solver={sid} ({idx}/{tot})", flush=True)

            comparator = WCNFCompare(
                out_dir=out_dir,
                per_solver_timeout_s=args.per_solver_timeout,
                run_id=case_id,
                progress_cb=_on_progress,
            )
            phase = "solve"
            outcomes, summary = comparator.compare_case(wcnf, case_json, selected_solvers)
            solver_progress = f"{_progress_bar(len(selected_solvers), len(selected_solvers))} {len(selected_solvers)}/{len(selected_solvers)} done"
            (summaries_dir / f"{case_id}.summary.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )

            case_features = _feature_tags(wcnf, case_id, reg_name)
            for rec in summary["results"]:
                cell = _classify_cell(rec)
                solver_status_counts[rec["solver"]][cell] += 1
                if rec.get("fault") and not str(rec.get("fault")).startswith("SKIP_"):
                    fault = str(rec["fault"])
                    fault_counts[fault] = fault_counts.get(fault, 0) + 1
                    for tag in case_features:
                        feature_fault_counts[tag] = feature_fault_counts.get(tag, 0) + 1
                if str(rec.get("fault")).startswith("SKIP_"):
                    reason = str(rec.get("error") or rec.get("fault"))
                    reason = reason.splitlines()[0][:120]
                    skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1

            case_faults = [r for r in summary["results"] if r.get("fault") and not str(r.get("fault")).startswith("SKIP_")]
            total_faults += len(case_faults)
            last_case_id = case_id
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
                    "considered_solvers": [r.get("solver") for r in considered],
                    "considered_statuses": {r.get("solver"): _classify_cell(r) for r in considered},
                    "considered_fault_histogram": dict(sorted(fault_hist.items(), key=lambda kv: (-kv[1], kv[0]))),
                    "considered_o_solver_minus_o_model": delta_by_solver,
                    "case_summary": summary,
                    "case_features": case_features,
                    "case_stats": {
                        "nvars": int(wcnf.nvars),
                        "num_hard": len(wcnf.hard),
                        "num_soft": len(wcnf.soft),
                        "num_empty_hard": sum(1 for cl in wcnf.hard if not cl),
                        "num_empty_soft": sum(1 for cl, _w in wcnf.soft if not cl),
                    },
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
                    f"[fuzz] case={case_id} results={len(summary['results'])} faults={len(case_faults)} "
                    f"o_min={summary.get('o_min')} progress={iter_progress} solver={solver_progress}",
                    flush=True,
                )

            if args.reduce and case_faults and (deadline is None or time.monotonic() < deadline):
                phase = "reduce"
                reducer = DeltaReducer(comparator=comparator, solvers=selected_solvers, out_dir=out_dir / "reduction_tmp")
                for k, rec in enumerate(case_faults, start=1):
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    target = TargetFault(
                        solver_id=rec["solver"],
                        fault=rec["fault"],
                        exit_code=rec["exit_code"],
                    )
                    reduced = reducer.reduce(wcnf, target)
                    rid = f"{case_id}__reduced{k}__{target.solver_id}__{target.fault}"
                    red_json, _ = _write_case(out_dir, rid, reduced, kind="reduced")
                    red_comp = WCNFCompare(out_dir=out_dir, per_solver_timeout_s=args.per_solver_timeout, run_id=rid)
                    _o2, red_summary = red_comp.compare_case(reduced, red_json, selected_solvers)
                    (summaries_dir / f"{rid}.summary.json").write_text(
                        json.dumps(red_summary, indent=2), encoding="utf-8"
                    )
                    if not args.interactive:
                        print(
                            f"[reduce] base={case_id} target={target.solver_id}:{target.fault} "
                            f"size {len(wcnf.hard)}/{len(wcnf.soft)} -> {len(reduced.hard)}/{len(reduced.soft)}",
                            flush=True,
                        )

            i += 1
            phase = "idle"
    except KeyboardInterrupt:
        interrupted = True
        phase = "interrupted"
        print("\n[fuzz] interrupted by user (Ctrl+C); writing final summary...")

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
            current_case_faults=last_case_faults,
            phase=phase,
            solver_progress=solver_progress,
            iter_progress=(
                f"{_progress_bar(i, args.iterations)} {i}/{args.iterations}" if not args.forever else f"{i} cases"
            ),
            last_alert=last_alert,
            out_dir=out_dir,
        )
        _interactive_paint(dashboard)
        live_dashboard_path.write_text(dashboard, encoding="utf-8")
    print(json.dumps(final, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
