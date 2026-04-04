from __future__ import annotations

import random

import pytest
from pysat.solvers import Solver


def _pick_solver_name() -> str:
    for name in ("cadical153", "cadical195", "g4", "g3", "m22", "mgh"):
        try:
            solver = Solver(name=name)
            solver.delete()
            return name
        except Exception:
            continue
    pytest.skip("No usable PySAT backend solver is available in this environment.")


def _assignment_units(lits: list[int], mask: int) -> list[int]:
    return [lit if (mask >> i) & 1 else -lit for i, lit in enumerate(lits)]


def _expected_pb(weights: list[int], mask: int, bound: int) -> bool:
    total = 0
    for i, weight in enumerate(weights):
        if (mask >> i) & 1:
            total += weight
    return total <= bound


def _sat_under_assignment(clauses: list[list[int]], assumptions: list[int], solver_name: str) -> bool:
    with Solver(name=solver_name, bootstrap_with=clauses) as solver:
        return bool(solver.solve(assumptions=assumptions))


def test_manual_lpw_surface_matches_semantics_and_best() -> None:
    try:
        from hermax.internal.pb import EncType, PBEnc  # type: ignore
        from hermax.internal import _pblib as native_pblib  # type: ignore
    except Exception as exc:
        pytest.skip(f"PBLib bindings are unavailable: {exc}")

    assert hasattr(EncType, "lpw")
    assert hasattr(native_pblib, "PB_LPW")

    solver_name = _pick_solver_name()
    rng = random.Random(0x1A2B3C)

    for _case in range(40):
        n = rng.randint(1, 6)
        lits = list(range(1, n + 1))
        weights = [rng.randint(1, 10) for _ in range(n)]
        bound = rng.randint(0, sum(weights))

        lpw_cnf = PBEnc.leq(lits=lits, weights=weights, bound=bound, encoding=EncType.lpw)
        best_cnf = PBEnc.leq(lits=lits, weights=weights, bound=bound, encoding=EncType.best)

        for mask in range(1 << n):
            assumptions = _assignment_units(lits, mask)
            expected = _expected_pb(weights, mask, bound)
            lpw_sat = _sat_under_assignment(lpw_cnf.clauses, assumptions, solver_name)
            best_sat = _sat_under_assignment(best_cnf.clauses, assumptions, solver_name)
            assert lpw_sat == expected, (weights, bound, mask, lpw_cnf.clauses)
            assert best_sat == expected, (weights, bound, mask, best_cnf.clauses)
            assert lpw_sat == best_sat
