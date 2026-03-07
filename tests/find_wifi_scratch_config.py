#!/usr/bin/env python3
"""Search for wifi.py scratch-mode configs with solve times in a target band.

This runner executes examples/wifi.py as a subprocess, streams stdout in real
time, parses "Solve Time: X.XXXX seconds" lines, and enforces:
 - per-query timeout (time from event start to solve-time line)
 - per-run timeout
 - optional stall timeout (no stdout activity)

On timeout/stall it force-kills the child process.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import queue
import re
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path


SOLVE_RE = re.compile(r"Solve Time:\s*([0-9]+(?:\.[0-9]+)?)\s*seconds")
ITER_RE = re.compile(r"--- Event Iteration\s+([0-9]+)\s+---")


@dataclass
class RunResult:
    status: str  # PASS | TIMEOUT | STALL | ERR
    reason: str
    returncode: int | None
    solve_times: list[float]
    lines: int
    elapsed_s: float


@dataclass
class ConfigSummary:
    nodes: int
    edge_prob: float
    freqs: int
    runs: int
    queries: int
    within_count: int
    within_ratio: float
    mean_s: float
    median_s: float
    stdev_s: float
    min_s: float
    max_s: float
    status: str
    failures: int
    timeouts: int
    stalls: int
    errs: int
    skipped: bool = False
    skip_reason: str = ""


def parse_csv_ints(s: str) -> list[int]:
    out: list[int] = []
    for x in s.split(","):
        x = x.strip()
        if not x:
            continue
        out.append(int(x))
    if not out:
        raise ValueError("Expected at least one integer")
    return out


def parse_csv_floats(s: str) -> list[float]:
    out: list[float] = []
    for x in s.split(","):
        x = x.strip()
        if not x:
            continue
        out.append(float(x))
    if not out:
        raise ValueError("Expected at least one float")
    return out


def stream_reader(pipe, q: queue.Queue[str]) -> None:
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            q.put(line.rstrip("\n"))
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def run_wifi_once(
    wifi_script: Path,
    nodes: int,
    edge_prob: float,
    freqs: int,
    seed: int,
    iterations: int,
    query_timeout_s: float,
    run_timeout_s: float,
    stall_timeout_s: float,
    verbose: bool,
) -> RunResult:
    cmd = [
        sys.executable,
        "-u",
        str(wifi_script),
        "--mode",
        "scratch",
        "--nodes",
        str(nodes),
        "--edge-prob",
        str(edge_prob),
        "--freqs",
        str(freqs),
        "--iterations",
        str(iterations),
        "--seed",
        str(seed),
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert proc.stdout is not None
    q: queue.Queue[str] = queue.Queue()
    t = threading.Thread(target=stream_reader, args=(proc.stdout, q), daemon=True)
    t.start()

    t0 = time.monotonic()
    last_output_t = t0
    current_iter_start_t: float | None = None
    solve_times: list[float] = []
    lines = 0
    status = "PASS"
    reason = "ok"

    while True:
        try:
            line = q.get(timeout=0.1)
            lines += 1
            last_output_t = time.monotonic()
            if verbose:
                print(f"  [wifi] {line}", flush=True)
            if ITER_RE.search(line):
                current_iter_start_t = time.monotonic()
            m = SOLVE_RE.search(line)
            if m:
                solve_times.append(float(m.group(1)))
                current_iter_start_t = None
        except queue.Empty:
            pass

        now = time.monotonic()
        elapsed = now - t0

        if run_timeout_s > 0 and elapsed > run_timeout_s:
            status = "TIMEOUT"
            reason = f"run timeout after {run_timeout_s:.1f}s"
            proc.kill()
            break

        if (
            stall_timeout_s > 0
            and (now - last_output_t) > stall_timeout_s
            and proc.poll() is None
        ):
            status = "STALL"
            reason = f"no stdout for {stall_timeout_s:.1f}s"
            proc.kill()
            break

        if (
            query_timeout_s > 0
            and current_iter_start_t is not None
            and (now - current_iter_start_t) > query_timeout_s
            and proc.poll() is None
        ):
            status = "TIMEOUT"
            reason = f"query timeout after {query_timeout_s:.1f}s"
            proc.kill()
            break

        if proc.poll() is not None and q.empty():
            break

    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)

    # Drain remaining lines quickly.
    drain_t0 = time.monotonic()
    while time.monotonic() - drain_t0 < 1.0:
        try:
            line = q.get_nowait()
            lines += 1
            if verbose:
                print(f"  [wifi] {line}", flush=True)
            m = SOLVE_RE.search(line)
            if m:
                solve_times.append(float(m.group(1)))
        except queue.Empty:
            break

    rc = proc.returncode
    total_elapsed = time.monotonic() - t0

    if status == "PASS" and rc != 0:
        status = "ERR"
        reason = f"process exited with code {rc}"

    return RunResult(
        status=status,
        reason=reason,
        returncode=rc,
        solve_times=solve_times,
        lines=lines,
        elapsed_s=total_elapsed,
    )


def summarize_config(
    nodes: int,
    edge_prob: float,
    freqs: int,
    results: list[RunResult],
    target_min: float,
    target_max: float,
) -> ConfigSummary:
    all_times = [x for r in results for x in r.solve_times]
    runs = len(results)
    failures = sum(1 for r in results if r.status != "PASS")
    timeouts = sum(1 for r in results if r.status == "TIMEOUT")
    stalls = sum(1 for r in results if r.status == "STALL")
    errs = sum(1 for r in results if r.status == "ERR")

    if all_times:
        within_count = sum(1 for t in all_times if target_min <= t <= target_max)
        within_ratio = within_count / len(all_times)
        mean_s = statistics.fmean(all_times)
        median_s = statistics.median(all_times)
        stdev_s = statistics.pstdev(all_times) if len(all_times) > 1 else 0.0
        min_s = min(all_times)
        max_s = max(all_times)
    else:
        within_count = 0
        within_ratio = 0.0
        mean_s = float("inf")
        median_s = float("inf")
        stdev_s = float("inf")
        min_s = float("inf")
        max_s = float("inf")

    status = "PASS" if failures == 0 else "FAIL"

    return ConfigSummary(
        nodes=nodes,
        edge_prob=edge_prob,
        freqs=freqs,
        runs=runs,
        queries=len(all_times),
        within_count=within_count,
        within_ratio=within_ratio,
        mean_s=mean_s,
        median_s=median_s,
        stdev_s=stdev_s,
        min_s=min_s,
        max_s=max_s,
        status=status,
        failures=failures,
        timeouts=timeouts,
        stalls=stalls,
        errs=errs,
    )


def score_summary(s: ConfigSummary, target_mid: float) -> float:
    if s.status != "PASS" or s.queries == 0:
        return float("inf")
    dist = abs(s.median_s - target_mid)
    penalty = (1.0 - s.within_ratio) * 100.0
    spread = s.stdev_s
    return dist + penalty + 0.2 * spread


def format_num(x: float) -> str:
    if math.isinf(x):
        return "inf"
    return f"{x:.3f}"


def is_harder_or_equal(a: tuple[int, float, int], b: tuple[int, float, int]) -> bool:
    """True if config a is at least as hard as b under monotone assumptions.

    Harder dimensions:
    - more nodes => harder
    - higher edge_prob => harder
    - fewer freqs => harder
    """
    na, pa, fa = a
    nb, pb, fb = b
    return na >= nb and pa >= pb and fa <= fb


def is_easier_or_equal(a: tuple[int, float, int], b: tuple[int, float, int]) -> bool:
    """True if config a is at least as easy as b."""
    na, pa, fa = a
    nb, pb, fb = b
    return na <= nb and pa <= pb and fa >= fb


def main() -> int:
    ap = argparse.ArgumentParser(description="Find wifi.py scratch-mode configs with 5-10s/query timing.")
    ap.add_argument("--wifi-script", default="examples/wifi.py")
    ap.add_argument("--nodes", default="35,40,45,50,55,60")
    ap.add_argument("--edge-probs", default="0.15,0.2,0.25,0.3")
    ap.add_argument("--freqs", default="6,7,8,9")
    ap.add_argument("--iterations", type=int, default=3, help="queries per run")
    ap.add_argument("--seeds", default="42,1337,2025", help="comma-separated seeds")
    ap.add_argument("--target-min", type=float, default=5.0)
    ap.add_argument("--target-max", type=float, default=10.0)
    ap.add_argument("--required-ratio", type=float, default=1.0, help="required fraction in target band")
    ap.add_argument("--query-timeout", type=float, default=20.0, help="per-query timeout (seconds)")
    ap.add_argument("--run-timeout", type=float, default=120.0, help="per-run timeout (seconds)")
    ap.add_argument("--stall-timeout", type=float, default=20.0, help="kill if no stdout for this many seconds")
    ap.add_argument("--max-candidates", type=int, default=0, help="0 = all, otherwise stop after N candidates")
    ap.add_argument("--out-json", default="tests/_wifi_tuning_results.json")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--prune-useless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="skip dominated configs using monotonic hardness assumptions (default: enabled)",
    )
    ap.add_argument(
        "--stall-means-hard",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="treat any STALL as too-hard for pruning (default: enabled)",
    )
    args = ap.parse_args()

    wifi_script = Path(args.wifi_script).resolve()
    if not wifi_script.exists():
        print(f"wifi script not found: {wifi_script}", file=sys.stderr)
        return 2

    nodes = parse_csv_ints(args.nodes)
    edge_probs = parse_csv_floats(args.edge_probs)
    freqs = parse_csv_ints(args.freqs)
    seeds = parse_csv_ints(args.seeds)

    combos = list(itertools.product(nodes, edge_probs, freqs))
    # Evaluate easier instances first so "too hard" findings prune aggressively.
    combos.sort(key=lambda t: (t[0], t[1], -t[2]))
    if args.max_candidates > 0:
        combos = combos[: args.max_candidates]

    print(f"wifi_script={wifi_script}")
    print(f"candidates={len(combos)} seeds={len(seeds)} iterations={args.iterations}")
    print(
        f"target=[{args.target_min:.1f}, {args.target_max:.1f}] required_ratio={args.required_ratio:.2f} "
        f"query_timeout={args.query_timeout:.1f}s run_timeout={args.run_timeout:.1f}s stall_timeout={args.stall_timeout:.1f}s"
    )

    summaries: list[ConfigSummary] = []
    details: list[dict] = []
    too_hard_frontier: list[tuple[int, float, int]] = []
    too_easy_frontier: list[tuple[int, float, int]] = []
    skipped_count = 0

    for idx, (n, p, f) in enumerate(combos, start=1):
        cfg = (n, p, f)
        if args.prune_useless:
            hard_dom = next((x for x in too_hard_frontier if is_harder_or_equal(cfg, x)), None)
            if hard_dom is not None:
                skipped_count += 1
                reason = (
                    f"dominated by too-hard config nodes={hard_dom[0]} edge_prob={hard_dom[1]} freqs={hard_dom[2]}"
                )
                print(f"\n[{idx}/{len(combos)}] nodes={n} edge_prob={p} freqs={f} -> SKIP ({reason})", flush=True)
                s = ConfigSummary(
                    nodes=n,
                    edge_prob=p,
                    freqs=f,
                    runs=0,
                    queries=0,
                    within_count=0,
                    within_ratio=0.0,
                    mean_s=float("inf"),
                    median_s=float("inf"),
                    stdev_s=float("inf"),
                    min_s=float("inf"),
                    max_s=float("inf"),
                    status="SKIP",
                    failures=0,
                    timeouts=0,
                    stalls=0,
                    errs=0,
                    skipped=True,
                    skip_reason=reason,
                )
                summaries.append(s)
                details.append(
                    {
                        "config": {"nodes": n, "edge_prob": p, "freqs": f},
                        "summary": asdict(s),
                        "runs": [],
                    }
                )
                continue

            easy_dom = next((x for x in too_easy_frontier if is_easier_or_equal(cfg, x)), None)
            if easy_dom is not None:
                skipped_count += 1
                reason = (
                    f"dominated by too-easy config nodes={easy_dom[0]} edge_prob={easy_dom[1]} freqs={easy_dom[2]}"
                )
                print(f"\n[{idx}/{len(combos)}] nodes={n} edge_prob={p} freqs={f} -> SKIP ({reason})", flush=True)
                s = ConfigSummary(
                    nodes=n,
                    edge_prob=p,
                    freqs=f,
                    runs=0,
                    queries=0,
                    within_count=0,
                    within_ratio=0.0,
                    mean_s=float("inf"),
                    median_s=float("inf"),
                    stdev_s=float("inf"),
                    min_s=float("inf"),
                    max_s=float("inf"),
                    status="SKIP",
                    failures=0,
                    timeouts=0,
                    stalls=0,
                    errs=0,
                    skipped=True,
                    skip_reason=reason,
                )
                summaries.append(s)
                details.append(
                    {
                        "config": {"nodes": n, "edge_prob": p, "freqs": f},
                        "summary": asdict(s),
                        "runs": [],
                    }
                )
                continue

        print(f"\n[{idx}/{len(combos)}] nodes={n} edge_prob={p} freqs={f}", flush=True)
        run_results: list[RunResult] = []
        for seed in seeds:
            print(f"  seed={seed} ... ", end="", flush=True)
            rr = run_wifi_once(
                wifi_script=wifi_script,
                nodes=n,
                edge_prob=p,
                freqs=f,
                seed=seed,
                iterations=args.iterations,
                query_timeout_s=args.query_timeout,
                run_timeout_s=args.run_timeout,
                stall_timeout_s=args.stall_timeout,
                verbose=args.verbose,
            )
            run_results.append(rr)
            print(
                f"{rr.status} queries={len(rr.solve_times)} elapsed={rr.elapsed_s:.2f}s reason={rr.reason}",
                flush=True,
            )

        s = summarize_config(n, p, f, run_results, args.target_min, args.target_max)
        summaries.append(s)
        details.append(
            {
                "config": {"nodes": n, "edge_prob": p, "freqs": f},
                "summary": asdict(s),
                "runs": [asdict(r) for r in run_results],
            }
        )

        if args.prune_useless:
            # Observed too hard:
            # - PASS run but already above target max
            # - any timeout observed
            # - any stall observed (configurable)
            # - all runs stalled/timed out with no usable timings
            if (
                (s.status == "PASS" and s.queries > 0 and s.median_s > args.target_max)
                or s.timeouts > 0
                or (args.stall_means_hard and s.stalls > 0)
                or (s.queries == 0 and (s.stalls + s.timeouts) == s.runs and s.runs > 0)
            ):
                too_hard_frontier.append(cfg)

            # Observed too easy: PASS runs with median below target min.
            if s.status == "PASS" and s.queries > 0 and s.median_s < args.target_min:
                too_easy_frontier.append(cfg)

        print(
            "  summary: "
            f"status={s.status} within={s.within_count}/{s.queries} ({s.within_ratio:.2%}) "
            f"median={format_num(s.median_s)}s stdev={format_num(s.stdev_s)} "
            f"min={format_num(s.min_s)} max={format_num(s.max_s)} "
            f"timeouts={s.timeouts} stalls={s.stalls} errs={s.errs}",
            flush=True,
        )

    target_mid = (args.target_min + args.target_max) / 2.0
    ranked = sorted(summaries, key=lambda x: score_summary(x, target_mid))

    print("\nTop candidates")
    print("nodes | edge_prob | freqs | status | within_ratio | median_s | stdev_s | min_s | max_s | failures")
    print("----- | --------- | ----- | ------ | ----------- | -------- | ------- | ----- | ----- | --------")
    for s in ranked[:10]:
        print(
            f"{s.nodes:>5} | {s.edge_prob:>9.3f} | {s.freqs:>5} | {s.status:>6} | "
            f"{s.within_ratio:>11.2%} | {format_num(s.median_s):>8} | {format_num(s.stdev_s):>7} | "
            f"{format_num(s.min_s):>5} | {format_num(s.max_s):>5} | {s.failures:>8}"
        )

    acceptable = [
        s
        for s in ranked
        if s.status == "PASS" and (not s.skipped) and s.within_ratio >= args.required_ratio and s.queries > 0
    ]
    if acceptable:
        best = acceptable[0]
        print("\nRecommended config")
        print(
            f"--nodes {best.nodes} --edge-prob {best.edge_prob} --freqs {best.freqs} "
            f"(median={best.median_s:.3f}s within_ratio={best.within_ratio:.2%})"
        )
    else:
        print("\nNo config met the required ratio; inspect JSON for nearest candidates.")

    out = {
        "meta": {
            "wifi_script": str(wifi_script),
            "target_min": args.target_min,
            "target_max": args.target_max,
            "required_ratio": args.required_ratio,
            "iterations": args.iterations,
            "seeds": seeds,
            "query_timeout": args.query_timeout,
            "run_timeout": args.run_timeout,
            "stall_timeout": args.stall_timeout,
            "prune_useless": args.prune_useless,
            "stall_means_hard": args.stall_means_hard,
        },
        "skipped_count": skipped_count,
        "summaries": [asdict(s) for s in summaries],
        "details": details,
    }
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\njson_report={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
