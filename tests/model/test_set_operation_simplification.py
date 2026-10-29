import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


OPERATIONS = ["union", "intersection", "difference", "symmetric_difference"]


@pytest.mark.parametrize("operation,clauses", [("union", 2000), ("intersection", 1000),
                                              ("difference", 1500), ("symmetric_difference", 2000)])
def test_disjoint_universes_use_only_necessary_set_operation_clauses(operation, clauses):
    m = Model()
    left = m.int_set("left", lb=1, ub=500)
    right = m.int_set("right", lb=501, ub=1000)
    before = m._top_id(), len(m._hard)
    result = getattr(left, operation)(right, name="result")
    assert len(m._hard) == before[1]
    formula = m.to_cnf()
    assert m._top_id() - before[0] == 1000
    assert len(formula.clauses) - before[1] == clauses
    assert result.name == "result" and result.universe == tuple(range(1, 1001))
    assert result.contains(1000).name == "result::in[1000]"


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("left_values,right_values", [([1, 2], [2, 3]),
    ([], [1, 2]), ([1, 2], []), ([], []), ([1, 2], [1, 2]), ([1], [2]), ([1], [1, 2])])
def test_set_operations_define_every_result_member_in_both_directions(operation, left_values, right_values):
    m = Model()
    left = m.int_set("left", values=left_values)
    right = m.int_set("right", values=right_values)
    result = getattr(left, operation)(right)
    assert result.universe == tuple(sorted(set(left_values) | set(right_values)))
    source = [left.contains(v) for v in left_values] + [right.contains(v) for v in right_values]
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for bits in itertools.product((False, True), repeat=len(source)):
            a = {v for v, on in zip(left_values, bits) if on}
            b = {v for v, on in zip(right_values, bits[len(left_values):]) if on}
            expected = getattr(a, operation)(b)
            fixed = [m._lit_to_dimacs(lit if on else ~lit) for lit, on in zip(source, bits)]
            assert solver.solve(assumptions=fixed)
            for value in result.universe:
                member = result.contains(value)
                correct = member.id if value in expected else -member.id
                assert solver.solve(assumptions=fixed + [correct])
                assert not solver.solve(assumptions=fixed + [-correct])


def test_constant_set_disequality_is_one_clause_without_helper_variables():
    m = Model()
    selected = m.int_set("selected", lb=1, ub=1000)
    before = m._top_id(), len(m._hard)
    condition = selected != {1, 2, 3}
    assert (m._top_id(), len(m._hard)) == before
    m &= condition
    assert m._top_id() == before[0]
    assert len(m.to_cnf().clauses) - before[1] == 1


@pytest.mark.parametrize("universe", [[], [1], [1, 2, 3]])
@pytest.mark.parametrize("constant", [set(), {1}, {1, 3}, {5}])
@pytest.mark.parametrize("mode", ["post", "only_if", "iff"])
def test_constant_set_disequality_truth_tables(universe, constant, mode):
    m = Model()
    selected = m.int_set("selected", values=universe)
    flag = m.bool("flag")
    condition = selected != constant
    m &= condition if mode == "post" else getattr(condition, mode)(flag)
    literals = [selected.contains(v) for v in universe] + [flag]
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for bits in itertools.product((False, True), repeat=len(literals)):
            value = {v for v, on in zip(universe, bits) if on}
            truth = value != constant
            if mode == "only_if":
                truth = not bits[-1] or truth
            elif mode == "iff":
                truth = bits[-1] == truth
            fixed = [m._lit_to_dimacs(lit if on else ~lit) for lit, on in zip(literals, bits)]
            assert solver.solve(assumptions=fixed) is truth


def test_constant_set_disequality_captures_the_original_constant():
    m = Model()
    selected = m.int_set("selected", values=[1, 2])
    constant = {1}
    condition = selected != constant
    constant.add(2)
    m &= selected == {1}
    m &= condition
    assert not m.solve().ok
