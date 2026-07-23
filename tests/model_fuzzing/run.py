"""Standalone entry point for exhaustive semantic fuzzing of ``hermax.model``."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import random
import time
from pathlib import Path
from queue import Empty

from .ast import Case
from .grammar import Grammar
from .oracle import check_case
from .reducer import reduce_case


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fuzz hermax.model against an exhaustive integer AST oracle")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--forever", action="store_true", help="run without an iteration limit")
    parser.add_argument("--overall-timeout", type=float, default=3600.0, help="wall-clock seconds; 0 disables")
    parser.add_argument("--depth", type=int, default=3, help="maximum linear-expression width")
    parser.add_argument("--out-dir", default="tests/_model_fuzzing")
    parser.add_argument("--reduce", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--processes", type=int, default=1, help="worker processes; one preserves deterministic generation")
    parser.add_argument("--keep-going", action="store_true", help="continue after recording mismatches")
    parser.add_argument("--max-failures", type=int, default=0, help="stop after this many failures; 0 disables the limit")
    return parser.parse_args()


def _write_failure(out_dir: Path, case_id: str, case: Case, mismatch, reduced: Case | None, reduced_mismatch) -> Path:
    failures = out_dir / "failures"
    failures.mkdir(parents=True, exist_ok=True)
    payload = {
        "case": case.to_dict(),
        "mismatch": mismatch.to_dict(),
        "reduced_case": None if reduced is None else reduced.to_dict(),
        "reduced_mismatch": None if reduced_mismatch is None else reduced_mismatch.to_dict(),
    }
    json_path = failures / f"{case_id}.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    repro_path = failures / f"{case_id}.py"
    repro_path.write_text(
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[3]))\n"
        "from tests.model_fuzzing.ast import Case\n"
        "from tests.model_fuzzing.oracle import check_case\n\n"
        f"payload = json.loads({json.dumps(json.dumps(payload))})\n"
        "case = Case.from_dict(payload['reduced_case'] or payload['case'])\n"
        "print(check_case(case))\n",
        encoding="utf-8",
    )
    return json_path


def _case_assignments(case: Case) -> int:
    count = 2 ** case.bool_count
    for lb, ub in case.int_domains:
        count *= ub - lb + 1
    return count


def _write_summary(out_dir: Path, *, cases: int, assignments: int, faults: int, elapsed: float) -> None:
    summary = {"cases": cases, "assignments": assignments, "faults": faults, "elapsed_seconds": elapsed}
    (out_dir / "final_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def _record_failure(out_dir: Path, start: float, worker_id: int, local_case: int, ticket: int, case: Case, mismatch, reduce: bool) -> Path:
    reduced = reduced_mismatch = None
    if reduce:
        reduced, reduced_mismatch = reduce_case(case, mismatch)
    case_id = f"{int(start)}_w{worker_id}_{local_case:07d}_{ticket:09d}"
    return _write_failure(out_dir, case_id, case, mismatch, reduced, reduced_mismatch)


def _worker_main(
    worker_id: int,
    seed: int,
    depth: int,
    iterations: int | None,
    deadline: float | None,
    keep_going: bool,
    stop_event,
    events,
) -> None:
    """Generate independent cases; the parent owns reduction and artifacts."""
    rng = random.Random(seed)
    grammar = Grammar(rng, depth)
    local_case = pending_cases = pending_assignments = 0
    try:
        while not stop_event.is_set() and (iterations is None or local_case < iterations):
            if deadline is not None and time.monotonic() >= deadline:
                stop_event.set()
                break
            case = grammar.generate()
            mismatch = check_case(case)
            local_case += 1
            pending_cases += 1
            pending_assignments += _case_assignments(case)
            if mismatch is not None:
                events.put(
                    {
                        "kind": "failure",
                        "worker_id": worker_id,
                        "local_case": local_case,
                        "ticket": rng.randrange(10**9),
                        "case": case,
                        "mismatch": mismatch,
                    }
                )
                if not keep_going:
                    stop_event.set()
                    break
            if pending_cases >= 25:
                events.put({"kind": "progress", "cases": pending_cases, "assignments": pending_assignments})
                pending_cases = pending_assignments = 0
    finally:
        events.put({"kind": "done", "worker_id": worker_id, "cases": pending_cases, "assignments": pending_assignments})


def _run_parallel(args: argparse.Namespace, out_dir: Path, start: float, deadline: float | None) -> tuple[int, int, int]:
    context = multiprocessing.get_context("spawn")
    stop_event = context.Event()
    events = context.Queue()
    seed_rng = random.Random(args.seed)
    base, extra = divmod(args.iterations, args.processes)
    workers = []
    for worker_id in range(args.processes):
        iterations = None if args.forever else base + (1 if worker_id < extra else 0)
        worker = context.Process(
            target=_worker_main,
            args=(worker_id, seed_rng.randrange(2**63), args.depth, iterations, deadline, args.keep_going, stop_event, events),
            daemon=False,
        )
        worker.start()
        workers.append(worker)

    cases = assignments = faults = 0
    pending_workers = len(workers)
    interrupted = False
    try:
        while pending_workers:
            if deadline is not None and time.monotonic() >= deadline:
                stop_event.set()
            try:
                event = events.get(timeout=0.2)
            except Empty:
                continue
            kind = event["kind"]
            if kind == "progress":
                cases += event["cases"]
                assignments += event["assignments"]
            elif kind == "done":
                cases += event["cases"]
                assignments += event["assignments"]
                pending_workers -= 1
            elif kind == "failure":
                if not args.keep_going and faults:
                    continue
                if args.max_failures and faults >= args.max_failures:
                    continue
                faults += 1
                artifact = _record_failure(
                    out_dir,
                    start,
                    event["worker_id"],
                    event["local_case"],
                    event["ticket"],
                    event["case"],
                    event["mismatch"],
                    args.reduce,
                )
                print(
                    f"[model-fuzz] mismatch kind={event['mismatch'].kind} worker={event['worker_id']} "
                    f"case={event['local_case']} artifact={artifact}",
                    flush=True,
                )
                if not args.keep_going or (args.max_failures and faults >= args.max_failures):
                    stop_event.set()
            if cases and cases % 25 == 0:
                elapsed = time.monotonic() - start
                print(f"[model-fuzz] cases={cases} assignments={assignments} faults={faults} elapsed={elapsed:.1f}s", flush=True)
    except KeyboardInterrupt:
        interrupted = True
        stop_event.set()
        print("[model-fuzz] interrupted", flush=True)
    finally:
        stop_event.set()
        for worker in workers:
            worker.join(timeout=5)
            if worker.is_alive():
                worker.terminate()
                worker.join()
    if deadline is not None and time.monotonic() >= deadline and not interrupted:
        print("[model-fuzz] overall timeout reached", flush=True)
    return cases, assignments, faults


def _run_single(args: argparse.Namespace, out_dir: Path, start: float, deadline: float | None) -> tuple[int, int, int]:
    # Keep the pre-parallelization random stream and case order unchanged.
    rng = random.Random(args.seed)
    grammar = Grammar(rng, args.depth)
    cases = assignments = faults = 0
    try:
        while args.forever or cases < args.iterations:
            if deadline is not None and time.monotonic() >= deadline:
                print("[model-fuzz] overall timeout reached", flush=True)
                break
            case = grammar.generate()
            assignments += _case_assignments(case)
            mismatch = check_case(case)
            cases += 1
            if mismatch is not None:
                faults += 1
                artifact = _record_failure(out_dir, start, 0, cases, rng.randrange(10**9), case, mismatch, args.reduce)
                print(f"[model-fuzz] mismatch kind={mismatch.kind} case={cases} artifact={artifact}", flush=True)
                if not args.keep_going or (args.max_failures and faults >= args.max_failures):
                    break
            if cases % 25 == 0:
                elapsed = time.monotonic() - start
                print(f"[model-fuzz] cases={cases} assignments={assignments} faults={faults} elapsed={elapsed:.1f}s", flush=True)
    except KeyboardInterrupt:
        print("[model-fuzz] interrupted", flush=True)
    return cases, assignments, faults


def main() -> int:
    args = _parse_args()
    if args.iterations < 1 and not args.forever:
        raise SystemExit("--iterations must be positive unless --forever is used")
    if args.depth < 1:
        raise SystemExit("--depth must be positive")
    if args.processes < 1:
        raise SystemExit("--processes must be positive")
    if args.max_failures < 0:
        raise SystemExit("--max-failures cannot be negative")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(vars(args), indent=2, sort_keys=True), encoding="utf-8")
    deadline = None if args.overall_timeout <= 0 else time.monotonic() + args.overall_timeout
    start = time.monotonic()

    print(
        f"[model-fuzz] start seed={args.seed} iterations={'inf' if args.forever else args.iterations} "
        f"depth={args.depth} processes={args.processes}",
        flush=True,
    )
    if args.processes == 1:
        cases, assignments, faults = _run_single(args, out_dir, start, deadline)
    else:
        cases, assignments, faults = _run_parallel(args, out_dir, start, deadline)

    elapsed = time.monotonic() - start
    _write_summary(out_dir, cases=cases, assignments=assignments, faults=faults, elapsed=elapsed)
    print(f"[model-fuzz] done cases={cases} assignments={assignments} faults={faults} elapsed={elapsed:.1f}s", flush=True)
    return 1 if faults else 0
