from __future__ import annotations

from random import Random

from pysat.examples.rc2 import RC2
from pysat.formula import WCNF

from coretrail import CoreTrail


class Formula:
    def __init__(self, nv: int, hard: list[list[int]], soft: list[list[int]], wght: list[int]):
        self.nv = nv
        self.hard = hard
        self.soft = soft
        self.wght = wght
        self.atms: list[object] = []


def _medium_formula(rng: Random) -> Formula:
    nv = 10

    def clause() -> list[int]:
        return [
            rng.choice((-1, 1)) * rng.randrange(1, nv + 1)
            for _ in range(rng.randrange(1, 4))
        ]

    hard = [clause() for _ in range(12)]
    soft = [clause() for _ in range(18)]
    return Formula(nv, hard, soft, [rng.randrange(1, 20) for _ in soft])


def _rc2_cost(formula: Formula) -> int | None:
    wcnf = WCNF()
    for clause in formula.hard:
        wcnf.append(clause)
    for clause, weight in zip(formula.soft, formula.wght):
        wcnf.append(clause, weight=weight)
    with RC2(wcnf) as solver:
        return None if solver.compute() is None else int(solver.cost)


def test_fixed_seed_medium_wcnf_matches_rc2():
    rng = Random(41)
    for _ in range(30):
        formula = _medium_formula(rng)
        expected = _rc2_cost(formula)
        solver = CoreTrail(formula)
        try:
            assert solver.solve() is (expected is not None)
            if expected is None:
                assert solver.get_status() == 20
            else:
                assert solver.get_status() == 30
                assert solver.get_cost() == expected
        finally:
            solver.close()


def test_long_incremental_hardening_sequence_keeps_exact_cost():
    variable_count = 512
    solver = CoreTrail(
        Formula(
            variable_count,
            hard=[],
            soft=[[var] for var in range(1, variable_count + 1)],
            wght=[1] * variable_count,
        )
    )
    try:
        for var in range(1, variable_count + 1):
            solver.add_clause([-var])
            assert solver.solve() is True
            assert solver.get_status() == 30
            assert solver.get_cost() == var

        # Re-solving an unchanged, long-lived instance must not duplicate
        # buffered clauses or change the established objective value.
        assert solver.solve() is True
        assert solver.get_cost() == variable_count
    finally:
        solver.close()
