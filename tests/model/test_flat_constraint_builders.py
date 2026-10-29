import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Clause, IntVector, Model


def _fixed(model, variable, value):
    return [model._lit_to_dimacs(lit) for lit in variable._exact_value_atoms(value)]


def test_large_reified_lexicographic_comparison_compiles_without_recursive_conjunctions():
    m = Model()
    left, right = m.int_vector("left", 1000, 0, 1), m.int_vector("right", 1000, 0, 1)
    flag = m.bool("flag")
    before = m._top_id(), len(m._hard)
    condition = left.lexicographic_less_than(right).iff(flag)
    assert (m._top_id(), len(m._hard)) == before
    m &= condition
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            av, bv = [0] * 999 + [a], [0] * 999 + [b]
            fixed = [lit for vector, values in [(left, av), (right, bv)]
                     for item, value in zip(vector, values) for lit in _fixed(m, item, value)]
            for on in [False, True]:
                assert solver.solve(assumptions=fixed + [flag.id if on else -flag.id]) is (on == (av < bv))


@pytest.mark.parametrize("target", ["relation", "pb", "global"])
@pytest.mark.parametrize("size", [0, 3, 512])
def test_clause_implication_builders_preserve_truth_when_reified(target, size):
    m = Model()
    flags = m.bool_vector("flags", size)
    x, y = m.int("x", 0, 2), m.int("y", 0, 2)
    indicator = m.bool("indicator")
    if target == "relation":
        consequent = x <= y
        truth = lambda a, b: a <= b
    elif target == "pb":
        consequent = 2 * x + y <= 2
        truth = lambda a, b: 2 * a + b <= 2
    else:
        consequent = IntVector(m, "view", [x, y]).all_different()
        truth = lambda a, b: a != b
    before = m._top_id(), len(m._hard)
    condition = Clause(m, list(flags)).implies(consequent).iff(indicator)
    assert (m._top_id(), len(m._hard)) == before
    m &= condition
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, active_position, on in itertools.product(range(3), range(3), [-1, 0, size - 1], [False, True]):
            fixed = _fixed(m, x, a) + _fixed(m, y, b)
            fixed.extend(flag.id if i == active_position else -flag.id for i, flag in enumerate(flags))
            fixed.append(indicator.id if on else -indicator.id)
            expected = not (size and active_position >= 0) or truth(a, b)
            assert solver.solve(assumptions=fixed) is (on == expected)


@pytest.mark.parametrize("size", [0, 1, 3])
def test_reified_lexicographic_comparison_matches_every_small_assignment(size):
    m = Model()
    left, right = m.int_vector("left", size, -1, 0), m.int_vector("right", size, -1, 0)
    flag = m.bool("flag")
    m &= left.lexicographic_less_than(right).iff(flag)
    values = list(itertools.product([-1, 0], repeat=size))
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, on in itertools.product(values, values, [False, True]):
            fixed = [lit for vector, chosen in [(left, a), (right, b)]
                     for item, value in zip(vector, chosen) for lit in _fixed(m, item, value)]
            fixed.append(flag.id if on else -flag.id)
            assert solver.solve(assumptions=fixed) is (on == (a < b))
