import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.non_incremental import RC2
from tests.model.test_soft_behavior import FakeIPSoft


@pytest.mark.parametrize("strategy", [None, "incremental"])
def test_sequential_tiers_reject_solver_instances_before_replay(strategy):
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    m &= a
    m.tier_obj.set_lexicographic(2 * a, b, 5 * ~b)
    backend = FakeIPSoft()
    with pytest.raises(ValueError, match="class or factory"):
        m.solve(solver=backend, lex_strategy=strategy)
    assert backend.clauses == []
    assert backend.soft_map == {}


@pytest.mark.parametrize("strategy", ["incremental", "stratified"])
def test_tiered_solver_factories_preserve_priority(strategy):
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    m &= a
    m.tier_obj.set_lexicographic(2 * a, b, 5 * ~b)
    result = m.solve(solver=lambda **kwargs: RC2(**kwargs), lex_strategy=strategy)
    assert result[b] is False
    assert result.tier_costs == [2, 0, 5]


@pytest.mark.parametrize("operation", ["running_sum", "running_min", "running_max"])
def test_prefix_aggregates_share_by_contents_across_temporary_views(operation):
    m = Model()
    grid = m.int_matrix("grid", 2, 3, 0, 3)
    first = getattr(grid.row(0), operation)()
    before = m._next_id, len(m._hard)
    second = getattr(grid.row(0), operation)()
    assert second is first
    assert (m._next_id, len(m._hard)) == before
    other = getattr(grid.row(1), operation)()
    assert other is not first


@pytest.mark.parametrize("operation", ["running_sum", "running_min", "running_max"])
def test_distinct_unnamed_views_can_have_prefix_aggregates(operation):
    m = Model()
    xs = m.int_vector("x", 4, 0, 3)
    for x, value in zip(xs, (1, 2, 3, 0)):
        m &= x == value
    left = getattr(m.vector([xs[0], xs[1]]), operation)()
    right = getattr(m.vector([xs[2], xs[3]]), operation)()
    result = m.solve()
    function = {"running_sum": sum, "running_min": min, "running_max": max}[operation]
    assert result[left] == [1, function([1, 2])]
    assert result[right] == [3, function([3, 0])]


@pytest.mark.parametrize("operation", ["running_sum", "running_min", "running_max"])
def test_prefix_cache_preserves_order_and_duplicate_items(operation):
    m = Model()
    a, b = m.int("a", 0, 3), m.int("b", 0, 3)
    m &= a == 1
    m &= b == 3
    vectors = [m.vector(items) for items in ([a, b], [b, a], [a, a, b])]
    outputs = [getattr(vector, operation)() for vector in vectors]
    result = m.solve()
    function = {"running_sum": sum, "running_min": min, "running_max": max}[operation]
    for values, output in zip(([1, 3], [3, 1], [1, 1, 3]), outputs):
        assert result[output] == [function(values[:i + 1]) for i in range(len(values))]


@pytest.mark.parametrize("operation", ["running_sum", "running_min", "running_max"])
def test_prefix_caches_are_independent_between_live_models(operation):
    first, second = Model(), Model()
    left, right = first.int_vector("x", 2, 0, 4), second.int_vector("x", 2, 0, 4)
    for model, vector, values in [(first, left, [1, 2]), (second, right, [3, 4])]:
        for item, value in zip(vector, values):
            model &= item == value
    a, b = getattr(left, operation)(), getattr(right, operation)()
    assert getattr(left, operation)() is a
    assert getattr(right, operation)() is b
    assert a is not b
    function = {"running_sum": sum, "running_min": min, "running_max": max}[operation]
    assert first.solve()[a] == [1, function([1, 2])]
    assert second.solve()[b] == [3, function([3, 4])]


@pytest.mark.parametrize("comparison", [operator.le, operator.lt, operator.ge,
                                        operator.gt, operator.eq, operator.ne])
def test_integer_lookup_only_builds_requested_comparison(comparison):
    m = Model()
    values = m.int_vector("v", 3, 0, 4)
    index = m.int("index", 0, 2)
    m &= comparison(values[index], 2)
    if comparison not in (operator.eq, operator.ne):
        assert all(not value._eq_lits for value in values)
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for row, chosen in itertools.product(itertools.product(range(5), repeat=3), range(3)):
            fixed = [m._lit_to_dimacs(lit) for var, val in zip([*values, index], [*row, chosen])
                     for lit in var._exact_value_atoms(val)]
            assert solver.solve(assumptions=fixed) is comparison(row[chosen], 2)


def test_lexicographic_less_than_does_not_build_unused_final_equality():
    m = Model()
    a, b = m.int_vector("a", 1, 0, 10), m.int_vector("b", 1, 0, 10)
    m &= a.lexicographic_less_than(b)
    assert ("==intvar", id(b[0])) not in a[0]._cmp_cache
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for av, bv in itertools.product(range(11), repeat=2):
            fixed = [m._lit_to_dimacs(lit) for var, val in [(a[0], av), (b[0], bv)]
                     for lit in var._exact_value_atoms(val)]
            assert solver.solve(assumptions=fixed) is (av < bv)
