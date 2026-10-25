import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


KINDS = ["floor_div", "modulo", "scale", "max", "min", "sum_var"]


def build(m, kind, xs, name=None):
    if kind in ("floor_div", "modulo", "scale"):
        return getattr(m, kind)(xs[0], -2 if kind == "scale" else 3, name=name)
    return getattr(m, kind)(xs, name=name)


@pytest.mark.parametrize("kind", KINDS)
def test_operation_reuse_names_and_argument_order(kind):
    m = Model()
    xs = [m.int("x", -3, 5), m.int("y", 0, 4)]
    first = build(m, kind, xs)
    before = (m._top_id(), len(m._hard), len(m._pending_literal_defs))
    assert build(m, kind, xs) is first
    assert before == (m._top_id(), len(m._hard), len(m._pending_literal_defs))
    if kind in ("max", "min", "sum_var"):
        assert build(m, kind, xs[::-1]) is first
    named = build(m, kind, xs, "named")
    assert named is not first
    with pytest.raises(ValueError):
        build(m, kind, xs, "named")


@pytest.mark.parametrize("kind", KINDS)
def test_shared_operations_under_guards_and_reification(kind):
    m = Model()
    xs = [m.int("x", -2, 3), m.int("y", 0, 3)]
    a, b = m.bool("a"), m.bool("b")
    first = build(m, kind, xs)
    m &= (first >= 1).only_if(a)
    second = build(m, kind, xs)
    assert first is second
    m &= (second <= 2).iff(b)
    functions = {
        "floor_div": lambda x, y: x // 3,
        "modulo": lambda x, y: x % 3,
        "scale": lambda x, y: -2 * x,
        "max": max,
        "min": min,
        "sum_var": lambda x, y: x + y,
    }
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for x, y, guard, truth in itertools.product(
            range(-2, 4), range(4), [False, True], [False, True]
        ):
            value = functions[kind](x, y)
            fixed = [
                lit.id if i < v - owner.lb else -lit.id
                for owner, v in zip(xs, [x, y])
                for i, lit in enumerate(owner._threshold_lits)
            ]
            fixed += [a.id if guard else -a.id, b.id if truth else -b.id]
            assert solver.solve(assumptions=fixed) == (
                (not guard or value >= 1) and truth == (value <= 2)
            )


@pytest.mark.parametrize("kind", ["lower_bound", "upper_bound"])
def test_bounds_remain_fresh(kind):
    m = Model()
    xs = [m.int("x", 0, 10), m.int("y", 0, 10)]
    first = getattr(m, kind)(xs)
    second = getattr(m, kind)(xs)
    assert first is not second
    for x in xs:
        m &= x == 7
    m &= first >= (5 if kind == "lower_bound" else 9)
    m &= second <= (2 if kind == "lower_bound" else 8)
    assert m.solve().ok


def test_nested_and_boolean_sum_reuse():
    m = Model()
    x = m.int("x", -10, 20)
    assert ((x // 3) % 2)._realize() is ((x // 3) % 2)._realize()
    a, b = m.bool("a"), m.bool("b")
    assert m.sum_var([a, ~b, a]) is m.sum_var([a, a, ~b])
    assert m.sum_var([a, a, b]) is not m.sum_var([a, a, ~b])


@pytest.mark.parametrize("kind", KINDS)
def test_reuse_after_incremental_binding(kind):
    m = Model()
    xs = [m.int("x", -2, 4), m.int("y", 0, 4)]
    first = build(m, kind, xs)
    assert m.solve(incremental=True, backend="sat").ok
    try:
        second = build(m, kind, xs)
        assert first is second
        m &= second == second.ub
        assert m.solve(incremental=True, backend="sat").ok
        m &= first != second.ub
        assert m.solve(incremental=True, backend="sat").status == "unsat"
    finally:
        m.close_incremental()


def test_validation_stays_active_on_cached_parameters():
    m = Model()
    x = m.int("x", 0, 8)
    for method in (m.floor_div, m.modulo, m.scale):
        first = method(x, 1)
        assert (
            method(x=x, **{"factor" if method.__name__ == "scale" else "divisor": 1})
            is first
        )
        with pytest.raises(ValueError):
            method(x, True)
        with pytest.raises(TypeError):
            method(x, 1.0)
    foreign = Model().int("x", 0, 8)
    with pytest.raises(ValueError):
        m.floor_div(foreign, 1)


def test_failed_model_construction_is_not_reused(monkeypatch):
    m = Model()
    x = m.int("x", 0, 8)
    before = len(m._operation_cache._results)

    def fail(*args):
        raise RuntimeError("deliberate construction failure")

    with monkeypatch.context() as patch:
        patch.setattr(Model, "_register_literal_definition", fail)
        with pytest.raises(RuntimeError):
            m.floor_div(x, 2)
    assert len(m._operation_cache._results) == before
    assert m.floor_div(x, 2) is m.floor_div(x, 2)


def test_sources_models_and_duplicate_inputs_stay_distinct():
    m = Model()
    x, y = m.int("x", 0, 8), m.int("y", 0, 8)
    assert m.floor_div(x, 2) is not m.floor_div(y, 2)
    assert m.floor_div(x, 2) is not m.floor_div(x, 3)
    assert m.floor_div(x, 2) is not m.modulo(x, 2)
    assert m.sum_var([x, x, y]) is not m.sum_var([x, y, y])
    other = Model()
    z = other.int("x", 0, 8)
    assert m.floor_div(x, 2) is not other.floor_div(z, 2)
