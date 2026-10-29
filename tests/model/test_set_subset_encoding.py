import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


def _subset(left, right, api):
    return left.subset_of(right) if api == "subset" else right.superset_of(left)


@pytest.mark.parametrize("api", ["subset", "superset"])
@pytest.mark.parametrize("reified", [False, True])
def test_subset_encoding_ignores_values_outside_the_left_universe(api, reified):
    m = Model()
    left = m.int_set("left", values=[1, 2, 3])
    right = m.int_set("right", lb=1, ub=1000)
    flag = m.bool("flag")
    before = m._top_id(), len(m._hard)
    condition = _subset(left, right, api)
    m &= condition.iff(flag) if reified else condition
    formula = m.to_cnf()
    assert m._top_id() - before[0] == (3 if reified else 0)
    assert len(formula.clauses) - before[1] == (10 if reified else 3)


@pytest.mark.parametrize("api", ["subset", "superset"])
def test_subset_values_missing_on_the_right_use_units_without_boolean_constants(api):
    m = Model()
    left = m.int_set("left", values=[1, 2])
    right = m.int_set("right", values=[2, 3])
    before = m._top_id(), len(m._hard)
    m &= _subset(left, right, api)
    assert m._top_id() == before[0]
    assert len(m._hard) - before[1] == 2
    assert sorted(map(len, m.to_cnf().clauses)) == [1, 2]


@pytest.mark.parametrize("api", ["subset", "superset"])
@pytest.mark.parametrize("left_values,right_values", [([1, 2], [2, 3]),
    ([], [1, 2]), ([1, 2], []), ([], []), ([1, 2], [1, 2, 3])])
@pytest.mark.parametrize("mode", ["post", "only_if", "iff"])
def test_subset_truth_tables_with_different_universes(api, left_values, right_values, mode):
    m = Model()
    left = m.int_set("left", values=left_values)
    right = m.int_set("right", values=right_values)
    flag = m.bool("flag")
    condition = _subset(left, right, api)
    m &= condition if mode == "post" else getattr(condition, mode)(flag)
    literals = [left.contains(v) for v in left_values] + [right.contains(v) for v in right_values]
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for bits in itertools.product((False, True), repeat=len(literals) + 1):
            chosen_left = {v for v, on in zip(left_values, bits) if on}
            chosen_right = {v for v, on in zip(right_values, bits[len(left_values):]) if on}
            enabled = bits[-1]
            expected = chosen_left <= chosen_right
            if mode == "only_if":
                expected = not enabled or expected
            elif mode == "iff":
                expected = enabled == expected
            fixed = [m._lit_to_dimacs(lit if on else ~lit) for lit, on in zip(literals + [flag], bits)]
            assert solver.solve(assumptions=fixed) is expected, bits


@pytest.mark.parametrize("api", ["subset", "superset"])
def test_reflexive_subset_is_true_without_expanding_the_universe(api):
    m = Model()
    selected = m.int_set("selected", lb=1, ub=1000)
    flag = m.bool("flag")
    before = m._top_id(), len(m._hard)
    m &= _subset(selected, selected, api).iff(flag)
    assert m._top_id() == before[0]
    assert len(m._hard) - before[1] == 1
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        assert solver.solve(assumptions=[flag.id])
        assert not solver.solve(assumptions=[-flag.id])
