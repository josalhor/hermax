#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

# Avoid local package shadowing (`tests/randomized`) when executing this file directly.
if sys.path and os.path.basename(sys.path[0]) == "tests":
    sys.path.pop(0)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import random


def _rand_lits(rng: random.Random, n: int, vmax: int = 80):
    vals = set()
    while len(vals) < n:
        v = rng.randint(1, vmax)
        vals.add(v if rng.random() < 0.5 else -v)
    return list(vals)


def _make_initial_case(
    rng: random.Random,
    init_min_lits: int,
    init_max_lits: int,
    lit_vmax: int,
    fixed_top_id: int,
):
    lits = _rand_lits(rng, rng.randint(init_min_lits, init_max_lits), vmax=lit_vmax)
    ubound = rng.randint(0, max(len(lits), 1))
    top_id = fixed_top_id
    return lits, ubound, top_id


def _make_op(
    rng: random.Random,
    n_lits_now: int,
    op_add_max_lits: int,
    merge_max_lits: int,
    lit_vmax: int,
    fixed_top_id: int,
):
    op = rng.choice(["increase", "extend", "merge"])
    if op == "increase":
        return {"op": "increase"}

    if op == "extend":
        add_n = rng.randint(0, op_add_max_lits)
        add_lits = _rand_lits(rng, add_n, vmax=lit_vmax)
        return {
            "op": "extend",
            "lits": add_lits,
            "ubound": None if rng.random() < 0.4 else rng.randint(0, max(n_lits_now + add_n + 4, 3)),
            "top_id": fixed_top_id,
        }

    # merge
    other_lits = _rand_lits(rng, rng.randint(1, merge_max_lits), vmax=lit_vmax)
    return {
        "op": "merge",
        "other_lits": other_lits,
        "other_ub": rng.randint(0, max(len(other_lits), 1)),
        "other_top": fixed_top_id,
        "ubound": None if rng.random() < 0.4 else rng.randint(0, max(n_lits_now + len(other_lits) + 4, 3)),
        "top_id": fixed_top_id,
    }


def _build_workload(
    seed: int,
    cases: int,
    steps: int,
    init_min_lits: int,
    init_max_lits: int,
    op_add_max_lits: int,
    merge_max_lits: int,
    lit_vmax: int,
    fixed_top_id: int,
):
    rng = random.Random(seed)
    workloads = []
    for _ in range(cases):
        lits, ubound, top_id = _make_initial_case(rng, init_min_lits, init_max_lits, lit_vmax, fixed_top_id)
        ops = []
        lit_count = len(lits)
        for _ in range(steps):
            op = _make_op(rng, lit_count, op_add_max_lits, merge_max_lits, lit_vmax, fixed_top_id)
            if op["op"] == "extend":
                lit_count += len(op["lits"])
            elif op["op"] == "merge":
                lit_count += len(op["other_lits"])
            ops.append(op)
        workloads.append({"init": (lits, ubound, top_id), "ops": ops})
    return workloads


def _run_impl(ITotalizer, workloads, fixed_top_id: int):
    t_total = 0.0
    per_op = {"new": 0.0, "increase": 0.0, "extend": 0.0, "merge": 0.0}
    counts = {"new": 0, "increase": 0, "extend": 0, "merge": 0}

    for case in workloads:
        lits, ubound, top_id = case["init"]
        t0 = time.perf_counter()
        t_new0 = time.perf_counter()
        t = ITotalizer(lits=lits, ubound=ubound, top_id=top_id)
        per_op["new"] += (time.perf_counter() - t_new0)
        counts["new"] += 1
        t_total += (time.perf_counter() - t0)

        try:
            for op in case["ops"]:
                kind = op["op"]
                if kind == "increase":
                    max_bound = len(t.lits)
                    for b in range(1, max_bound + 1):
                        if max_bound <= 1:
                            top_for_step = 0
                        else:
                            top_for_step = ((b - 1) * fixed_top_id) // (max_bound - 1)
                        t1 = time.perf_counter()
                        t.increase(ubound=b, top_id=top_for_step)
                        dt = time.perf_counter() - t1
                        per_op[kind] += dt
                        counts[kind] += 1
                        t_total += dt
                elif kind == "extend":
                    t1 = time.perf_counter()
                    t.extend(lits=op["lits"], ubound=op["ubound"], top_id=op["top_id"])
                    dt = time.perf_counter() - t1
                    per_op[kind] += dt
                    counts[kind] += 1
                    t_total += dt
                else:
                    t1 = time.perf_counter()
                    t2 = ITotalizer(lits=op["other_lits"], ubound=op["other_ub"], top_id=op["other_top"])
                    try:
                        t.merge_with(t2, ubound=op["ubound"], top_id=op["top_id"])
                    finally:
                        t2.delete()
                    dt = time.perf_counter() - t1
                    per_op[kind] += dt
                    counts[kind] += 1
                    t_total += dt
        finally:
            t.delete()

    return t_total, per_op, counts


def _warmup_new(
    ITotalizer,
    seed: int,
    warmup_new: int,
    init_min_lits: int,
    init_max_lits: int,
    lit_vmax: int,
    fixed_top_id: int,
):
    if warmup_new <= 0:
        return

    rng = random.Random(seed)
    for _ in range(warmup_new):
        lits = _rand_lits(rng, rng.randint(init_min_lits, init_max_lits), vmax=lit_vmax)
        ubound = rng.randint(0, max(len(lits), 1))
        t = ITotalizer(lits=lits, ubound=ubound, top_id=fixed_top_id)
        t.delete()


def main():
    parser = argparse.ArgumentParser(description="Benchmark ITotalizer parity performance (Hermax vs PySAT).")
    parser.add_argument("--cases", type=int, default=25_000, help="Number of random scenarios.")
    parser.add_argument("--steps", type=int, default=1, help="Operations per scenario.")
    parser.add_argument("--seed", type=int, default=1337, help="Random seed.")
    parser.add_argument(
        "--warmup-new",
        type=int,
        default=300,
        help="Unmeasured warmup iterations for ITotalizer constructor (new).",
    )
    parser.add_argument("--json-out", type=str, default="", help="Optional path to write JSON report.")
    parser.add_argument("--init-min-lits", type=int, default=20, help="Min literals for initial totalizer.")
    parser.add_argument("--init-max-lits", type=int, default=40, help="Max literals for initial totalizer.")
    parser.add_argument("--op-add-max-lits", type=int, default=10, help="Max literals added in one extend op.")
    parser.add_argument("--merge-max-lits", type=int, default=10, help="Max literals in merge partner.")
    parser.add_argument("--lit-vmax", type=int, default=10_000, help="Max variable id used for random literals.")
    parser.add_argument("--fixed-top-id", type=int, default=12_000, help="Deterministic top_id upper bound.")
    args = parser.parse_args()

    if args.init_min_lits < 1 or args.init_max_lits < args.init_min_lits:
        raise SystemExit("invalid init literal bounds")
    if args.op_add_max_lits < 0 or args.merge_max_lits < 1 or args.lit_vmax < 1 or args.fixed_top_id < 0:
        raise SystemExit("invalid literal generation parameters")

    from hermax.internal.card import ITotalizer as HermaxITotalizer
    from pysat.card import ITotalizer as PySATITotalizer

    _warmup_new(
        HermaxITotalizer,
        seed=args.seed ^ 0x13579BDF,
        warmup_new=args.warmup_new,
        init_min_lits=args.init_min_lits,
        init_max_lits=args.init_max_lits,
        lit_vmax=args.lit_vmax,
        fixed_top_id=args.fixed_top_id,
    )
    _warmup_new(
        PySATITotalizer,
        seed=args.seed ^ 0x2468ACE0,
        warmup_new=args.warmup_new,
        init_min_lits=args.init_min_lits,
        init_max_lits=args.init_max_lits,
        lit_vmax=args.lit_vmax,
        fixed_top_id=args.fixed_top_id,
    )

    workloads = _build_workload(
        args.seed,
        args.cases,
        args.steps,
        args.init_min_lits,
        args.init_max_lits,
        args.op_add_max_lits,
        args.merge_max_lits,
        args.lit_vmax,
        args.fixed_top_id,
    )

    h_total, h_per_op, counts = _run_impl(HermaxITotalizer, workloads, args.fixed_top_id)
    p_total, p_per_op, _ = _run_impl(PySATITotalizer, workloads, args.fixed_top_id)

    def speedup(a, b):
        return (b / a) if a > 0 else float("inf")

    print(
        f"cases={args.cases} steps={args.steps} seed={args.seed} "
        f"warmup_new={args.warmup_new} total_ops={sum(counts.values())}"
    )
    print("impl   | total_s | ops_per_s")
    print("------ | ------- | ---------")
    total_ops = sum(counts.values())
    print(f"hermax | {h_total:.6f} | {total_ops / h_total:.2f}")
    print(f"pysat  | {p_total:.6f} | {total_ops / p_total:.2f}")
    print(f"speedup_hermax_vs_pysat={speedup(h_total, p_total):.3f}x")
    print("")
    print("op      | count | hermax_s | pysat_s | speedup")
    print("------- | ----- | -------- | ------- | -------")
    for op in ["new", "increase", "extend", "merge"]:
        hs = h_per_op[op]
        ps = p_per_op[op]
        print(f"{op:<7} | {counts[op]:>5} | {hs:>8.6f} | {ps:>7.6f} | {speedup(hs, ps):.3f}x")

    if args.json_out:
        payload = {
            "cases": args.cases,
            "steps": args.steps,
            "seed": args.seed,
            "warmup_new": args.warmup_new,
            "init_min_lits": args.init_min_lits,
            "init_max_lits": args.init_max_lits,
            "op_add_max_lits": args.op_add_max_lits,
            "merge_max_lits": args.merge_max_lits,
            "lit_vmax": args.lit_vmax,
            "fixed_top_id": args.fixed_top_id,
            "counts": counts,
            "hermax_total_s": h_total,
            "pysat_total_s": p_total,
            "speedup_hermax_vs_pysat": speedup(h_total, p_total),
            "hermax_per_op_s": h_per_op,
            "pysat_per_op_s": p_per_op,
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\njson_report={args.json_out}")


if __name__ == "__main__":
    main()
