from __future__ import annotations

from itertools import product
from random import Random

from coretrail import CoreTrail


class Formula:
    def __init__(self, nv: int, hard: list[list[int]], soft: list[list[int]], wght: list[int]):
        self.nv = nv
        self.hard = hard
        self.soft = soft
        self.wght = wght
        self.atms: list[object] = []


def _satisfies(clause: list[int], assignment: tuple[bool, ...]) -> bool:
    return any((lit > 0) == assignment[abs(lit) - 1] for lit in clause)


def _brute_cost(formula: Formula, assumptions: list[int] | None = None) -> int | None:
    hard = [*formula.hard, *([lit] for lit in (assumptions or []))]
    best: int | None = None
    for assignment in product((False, True), repeat=formula.nv):
        if not all(_satisfies(clause, assignment) for clause in hard):
            continue
        cost = sum(
            weight
            for clause, weight in zip(formula.soft, formula.wght)
            if not _satisfies(clause, assignment)
        )
        best = cost if best is None else min(best, cost)
    return best


def _random_formula(rng: Random) -> Formula:
    nv = 3

    def clause() -> list[int]:
        return [rng.choice((-1, 1)) * rng.randrange(1, nv + 1) for _ in range(rng.randrange(1, 4))]

    hard = [clause() for _ in range(rng.randrange(5))]
    soft = [clause() for _ in range(rng.randrange(1, 5))]
    return Formula(nv, hard, soft, [rng.randrange(1, 5) for _ in soft])


def test_fixed_seed_small_wcnf_matches_bruteforce():
    rng = Random(0)
    for _ in range(100):
        formula = _random_formula(rng)
        expected = _brute_cost(formula)
        solver = CoreTrail(formula)
        try:
            feasible = solver.solve()
            assert feasible is (expected is not None)
            if expected is not None:
                assert solver.get_status() == 30
                assert solver.get_cost() == expected
            else:
                assert solver.get_status() == 20
        finally:
            solver.close()


def test_assumptions_are_temporary_and_match_bruteforce():
    formula = Formula(nv=2, hard=[], soft=[[1], [2]], wght=[2, 3])
    solver = CoreTrail(formula)
    try:
        assert solver.solve(assumptions=[-1]) is True
        assert solver.get_cost() == _brute_cost(formula, [-1]) == 2

        assert solver.solve() is True
        assert solver.get_cost() == _brute_cost(formula) == 0
    finally:
        solver.close()


def test_hard_clause_additions_after_optimum_match_bruteforce():
    rng = Random(1)
    for _ in range(50):
        formula = _random_formula(rng)
        solver = CoreTrail(formula)
        try:
            expected = _brute_cost(formula)
            assert solver.solve() is (expected is not None)
            if expected is not None:
                assert solver.get_cost() == expected

            added_hard = [rng.choice((-1, 1)) * rng.randrange(1, formula.nv + 1)]
            solver.add_clause(added_hard)
            formula.hard.append(added_hard)
            expected = _brute_cost(formula)
            assert solver.solve() is (expected is not None)
            if expected is not None:
                assert solver.get_cost() == expected
            else:
                assert solver.get_status() == 20
        finally:
            solver.close()


def test_new_unit_soft_terms_after_optimum_match_bruteforce():
    rng = Random(2)
    for _ in range(50):
        formula = _random_formula(rng)
        existing_units = {clause[0] for clause in formula.soft if len(clause) == 1}
        candidates = [lit for var in range(1, formula.nv + 1) for lit in (var, -var) if lit not in existing_units]
        if not candidates:
            continue
        literal = rng.choice(candidates)
        weight = rng.randrange(1, 5)

        solver = CoreTrail(formula)
        try:
            expected = _brute_cost(formula)
            assert solver.solve() is (expected is not None)
            if expected is not None:
                assert solver.get_cost() == expected

            solver.set_soft(literal, weight)
            formula.soft.append([literal])
            formula.wght.append(weight)
            expected = _brute_cost(formula)
            assert solver.solve() is (expected is not None)
            if expected is not None:
                assert solver.get_cost() == expected
        finally:
            solver.close()


def test_replacing_an_existing_negative_unit_term_matches_bruteforce():
    formula = Formula(
        nv=2,
        hard=[],
        soft=[[-1], [2], [1, -2]],
        wght=[2, 3, 5],
    )
    solver = CoreTrail(formula)
    try:
        assert solver.solve() is True
        assert solver.get_cost() == _brute_cost(formula)

        solver.set_soft(-1, 11)
        formula.wght[0] = 11
        assert solver.solve() is True
        assert solver.get_cost() == _brute_cost(formula)
    finally:
        solver.close()


def test_random_assumptions_are_temporary_and_match_bruteforce():
    rng = Random(3)
    for _ in range(50):
        formula = _random_formula(rng)
        assumptions = [rng.choice((-1, 1)) * rng.randrange(1, formula.nv + 1) for _ in range(rng.randrange(4))]
        solver = CoreTrail(formula)
        try:
            expected = _brute_cost(formula, assumptions)
            assert solver.solve(assumptions=assumptions) is (expected is not None)
            if expected is not None:
                assert solver.get_cost() == expected
            else:
                assert solver.get_status() == 20

            expected = _brute_cost(formula)
            assert solver.solve() is (expected is not None)
            if expected is not None:
                assert solver.get_cost() == expected
        finally:
            solver.close()


def _model_assignment(model: list[int], nv: int) -> tuple[bool, ...]:
    values = {abs(lit): lit > 0 for lit in model}
    return tuple(values[var] for var in range(1, nv + 1))


def test_timed_incremental_sequence_matches_bruteforce_after_every_resume():
    # This is deliberately small enough for exhaustive verification.  It
    # exercises the state transitions that matter here, not a random timeout.
    formula = Formula(
        nv=4,
        hard=[],
        soft=[[1], [-1], [2], [-2], [3], [-3], [4], [-4]],
        wght=[1] * 8,
    )
    solver = CoreTrail(formula)
    rng = Random(17)
    assumptions: list[int] = []
    try:
        for step in range(24):
            # An immediate deadline is deterministic: it can expose no
            # candidate or a valid one, but it must leave the instance usable.
            assert solver.solve(assumptions=assumptions, time_limit=1e-12) is False
            status = solver.get_status()
            assert status in (0, 10, 20)
            if status == 10:
                model = solver.get_model()
                assignment = _model_assignment(model, formula.nv)
                assert all(_satisfies(clause, assignment) for clause in formula.hard)
                assert all(_satisfies([lit], assignment) for lit in assumptions)
                exact = sum(
                    weight
                    for clause, weight in zip(formula.soft, formula.wght)
                    if not _satisfies(clause, assignment)
                )
                assert solver.get_cost() == exact

            expected = _brute_cost(formula, assumptions)
            assert solver.solve(assumptions=assumptions) is (expected is not None)
            if expected is None:
                assert solver.get_status() == 20
            else:
                assert solver.get_status() == 30
                assert solver.get_cost() == expected

            mode = step % 3
            if mode == 0:
                literal = rng.choice([1, -1, 2, -2, 3, -3, 4, -4])
                weight = rng.randrange(0, 6)
                index = formula.soft.index([literal])
                formula.wght[index] = weight
                solver.set_soft(literal, weight)
            elif mode == 1:
                clause = [rng.choice((-1, 1)) * rng.randrange(1, formula.nv + 1)]
                formula.hard.append(clause)
                solver.add_clause(clause)
            else:
                assumptions = [rng.choice((-1, 1)) * rng.randrange(1, formula.nv + 1)]
    finally:
        solver.close()
