import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


SET_OPS = ("union", "intersection", "difference", "symmetric_difference")


@pytest.mark.parametrize("operation", SET_OPS)
def test_set_operations_reuse_unnamed_results(operation):
    m = Model()
    a = m.int_set("a", values=[0, 1, 2])
    b = m.int_set("b", values=[1, 2, 3])
    first = getattr(a, operation)(b)
    before = (m._top_id(), len(m._hard), len(m._pending_literal_defs))
    assert getattr(a, operation)(b) is first
    assert before == (m._top_id(), len(m._hard), len(m._pending_literal_defs))
    named = getattr(a, operation)(b, name="named")
    assert named is not first
    with pytest.raises(ValueError):
        getattr(a, operation)(b, name="named")


@pytest.mark.parametrize("operation", SET_OPS)
def test_cached_set_operation_exact_for_every_membership(operation):
    m = Model()
    a = m.int_set("a", values=[0, 1])
    b = m.int_set("b", values=[1, 2])
    out = getattr(a, operation)(b)
    assert getattr(a, operation)(b) is out
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for bits in itertools.product([False, True], repeat=4):
            av = {v for v, on in zip(a.universe, bits[:2]) if on}
            bv = {v for v, on in zip(b.universe, bits[2:]) if on}
            expected = {
                "union": av | bv,
                "intersection": av & bv,
                "difference": av - bv,
                "symmetric_difference": av ^ bv,
            }[operation]
            fixed = [
                lit.id if on else -lit.id
                for lit, on in zip(
                    [*a._member_lits.values(), *b._member_lits.values()], bits
                )
            ]
            for value, lit in out._member_lits.items():
                assert solver.solve(
                    assumptions=fixed + [lit.id if value in expected else -lit.id]
                )
                assert not solver.solve(
                    assumptions=fixed + [-lit.id if value in expected else lit.id]
                )


def test_set_cardinality_reuses_and_respects_disabled_guard():
    m = Model()
    s = m.int_set("s", values=[0, 1, 2])
    b = m.bool("b")
    first = s.card()
    before = m._top_id()
    assert s.card() is first and m._top_id() == before
    assert s.card(name="named") is not first
    m &= (first >= 2).only_if(b)
    m &= (s.card() == 1).iff(~b)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for bits, guard in itertools.product(
            itertools.product([False, True], repeat=3), [False, True]
        ):
            fixed = [
                lit.id if on else -lit.id
                for lit, on in zip(s._member_lits.values(), bits)
            ]
            fixed.append(b.id if guard else -b.id)
            count = sum(bits)
            assert solver.solve(assumptions=fixed) == (
                (not guard or count >= 2) and (not guard) == (count == 1)
            )


@pytest.mark.parametrize("operation", ["running_max", "running_min", "running_sum"])
def test_running_aggregates_reuse_and_are_exact(operation):
    m = Model()
    xs = m.int_vector("x", 3, -1, 2)
    first = getattr(xs, operation)()
    before = (m._top_id(), len(m._hard))
    assert getattr(xs, operation)() is first
    assert before == (m._top_id(), len(m._hard))
    named = getattr(xs, operation)(name="named")
    assert named is not first
    with pytest.raises(ValueError):
        getattr(xs, operation)(name="named")
    # Force realization of the defining clauses before exhaustive checks.
    for value in first:
        m &= value >= value.lb
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        function = {"running_max": max, "running_min": min, "running_sum": sum}[
            operation
        ]
        for values in itertools.product(range(-1, 3), repeat=3):
            fixed = [
                lit.id if i < v - owner.lb else -lit.id
                for owner, v in zip(xs, values)
                for i, lit in enumerate(owner._threshold_lits)
            ]
            assert solver.solve(assumptions=fixed)
            assignment = set(solver.get_model())
            for i, out in enumerate(first):
                assert out.lb + sum(
                    lit.id in assignment for lit in out._threshold_lits
                ) == function(values[: i + 1])
                expected = function(values[: i + 1])
                for index, lit in enumerate(out._threshold_lits):
                    wrong = -lit.id if index < expected - out.lb else lit.id
                    assert not solver.solve(assumptions=fixed + [wrong])


def test_mutable_constraint_results_remain_independent():
    m = Model()
    x = m.int("x", 0, 2)
    y = m.int("y", 0, 2)
    b = m.bool("b")
    first = x <= y
    second = x <= y
    first.extend(b, inplace=True)
    assert len(first) == len(second) + 1
    table = m.table([x, y], allowed=[(0, 0), (1, 1)])
    other = m.table([x, y], allowed=[(0, 0), (1, 1)])
    table.extend(b, inplace=True)
    assert len(table) == len(other) + 1


@pytest.mark.parametrize("operation", SET_OPS)
def test_set_cache_keeps_order_sources_and_models_distinct(operation):
    m = Model()
    a = m.int_set("a", values=[0, 1])
    b = m.int_set("b", values=[0, 1])
    c = m.int_set("c", values=[0, 1])
    result = getattr(a, operation)(b)
    assert getattr(a, operation)(c) is not result
    assert getattr(c, operation)(b) is not result
    with pytest.raises(ValueError):
        getattr(a, operation)(Model().int_set("foreign", values=[0, 1]))
    if operation == "difference":
        reverse = b.difference(a)
        m &= a == {0}
        m &= b == {1}
        m &= result == {0}
        m &= reverse == {1}
        assert m.solve().ok


@pytest.mark.parametrize("operation", ["running_max", "running_min", "running_sum"])
def test_running_cache_reuse_between_solves(operation):
    m = Model()
    xs = m.int_vector("x", 3, 0, 3)
    first = getattr(xs, operation)()
    assert m.solve(incremental=True, backend="sat").ok
    try:
        second = getattr(xs, operation)()
        assert second is first
        m &= xs[0] == 1
        m &= xs[1] == 2
        m &= xs[2] == 3
        expected = {"running_max": 3, "running_min": 1, "running_sum": 6}[operation]
        m &= second[2] != expected
        assert m.solve(incremental=True, backend="sat").status == "unsat"
    finally:
        m.close_incremental()
