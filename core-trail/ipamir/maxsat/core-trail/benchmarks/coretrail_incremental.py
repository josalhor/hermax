#!/usr/bin/env python3
"""Small reproducible performance smoke benchmark for standalone CoreTrail."""

from __future__ import annotations

import argparse
import time

from coretrail import CoreTrail


class Formula:
    def __init__(self, nv: int, hard: list[list[int]], soft: list[list[int]], wght: list[int]):
        self.nv = nv
        self.hard = hard
        self.soft = soft
        self.wght = wght
        self.atms: list[object] = []


def incremental_hardening(variable_count: int) -> float:
    solver = CoreTrail(
        Formula(
            variable_count,
            hard=[],
            soft=[[var] for var in range(1, variable_count + 1)],
            wght=[1] * variable_count,
        )
    )
    try:
        started = time.monotonic()
        for var in range(1, variable_count + 1):
            solver.add_clause([-var])
            if not solver.solve() or solver.get_cost() != var:
                raise RuntimeError(f"unexpected result at incremental step {var}")
        return time.monotonic() - started
    finally:
        solver.close()


def deadline_response(variable_count: int) -> tuple[float, int]:
    soft = [[var] for var in range(1, variable_count + 1)]
    soft.extend([[-var] for var in range(1, variable_count + 1)])
    solver = CoreTrail(Formula(variable_count, hard=[], soft=soft, wght=[1] * len(soft)))
    try:
        started = time.monotonic()
        solver.solve(time_limit=0.001)
        return time.monotonic() - started, int(solver.get_status())
    finally:
        solver.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variables", type=int, default=512)
    args = parser.parse_args()
    if args.variables <= 0:
        raise SystemExit("--variables must be positive")

    incremental_seconds = incremental_hardening(args.variables)
    deadline_seconds, status = deadline_response(args.variables)
    print(f"incremental_hardening variables={args.variables} seconds={incremental_seconds:.6f}")
    print(f"deadline_response variables={args.variables} seconds={deadline_seconds:.6f} status={status}")


if __name__ == "__main__":
    main()
