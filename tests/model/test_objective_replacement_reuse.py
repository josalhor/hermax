import itertools

import pytest

from hermax.model import Model
from tests.model.test_soft_behavior import FakeIPSoft


@pytest.mark.parametrize("method", ["assignment", "set", "replace"])
def test_repeated_replacement_reuses_soft_entries(method):
    m = Model()
    flags = m.bool_vector("b", 20)
    expression = sum(flags)
    for i in range(100):
        cost = (i % 3 + 1) * expression
        if method == "assignment":
            m.obj = cost
        elif method == "set":
            m.obj.set(cost)
        else:
            m.obj.replace_with(cost)
    assert len(m._soft) == len(flags)
    assert sum(w > 0 for w, _ in m._soft) == len(flags)


@pytest.mark.parametrize("incremental", [False, True])
def test_replacement_reuses_both_polarities_and_preserves_exact_costs(incremental):
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    expressions = [
        (2 * a - 3 * b - 4, lambda x, y: 2 * x - 3 * y - 4),
        (5 * b + 2, lambda x, y: 5 * y + 2),
        (0, lambda x, y: 0),
        (~a, lambda x, y: 1 - x),
    ]
    for _ in range(3):
        for expression, expected in expressions:
            m.obj = expression
            for x, y in itertools.product((False, True), repeat=2):
                result = m.solve(
                    assumptions=[a if x else ~a, b if y else ~b],
                    incremental=incremental,
                )
                assert result.cost == expected(x, y)
    assert len(m._soft) == 5


def test_clear_reuses_entries_without_reviving_old_handles():
    m = Model()
    a = m.bool("a")
    m &= a
    old = m.obj.add(a, weight=3)
    m.obj.clear()
    current = m.obj.add(a, weight=7)
    with pytest.raises(ValueError, match="cleared|replaced"):
        m.obj.update(old, weight=99)
    m.obj.update(current, weight=2)
    assert m.solve().cost == 2
    assert len(m._soft) == 1


def test_clear_allows_precision_change_and_reuse_with_new_units():
    m = Model()
    a = m.bool("a")
    m &= a
    m.obj.add(a, weight=3)
    m.obj.clear()
    m.set_objective_precision(decimals=2)
    m.obj.add(a, weight=1.25)
    assert m.solve().cost == 1.25
    assert len(m._soft) == 1


@pytest.mark.parametrize("dedup", [False, True])
def test_replacement_disables_legacy_preferences_and_invalidates_handles(dedup):
    m = Model()
    m.set_soft_dedup(dedup)
    a, b = m.bool("a"), m.bool("b")
    old = m.obj.add(a, weight=2)
    with pytest.warns(FutureWarning):
        legacy = m.obj.add_soft(~a, 9)
    m.obj = 4 * a + b
    with pytest.raises(ValueError, match="cleared|replaced"):
        m.obj.update(old, weight=99)
    with pytest.raises(ValueError, match="cleared|replaced"):
        m.obj.update(legacy, weight=99)
    for x, y in itertools.product((False, True), repeat=2):
        result = m.solve(assumptions=[a if x else ~a, b if y else ~b])
        assert result.cost == 4 * x + y


def test_replacement_reuses_incremental_units_without_new_hard_clauses():
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    m.obj = a + b
    solver = FakeIPSoft()
    m.solve(backend="maxsat", solver=solver)
    hard = list(solver.clauses)
    for _ in range(3):
        m.obj = 3 * a
        assert solver.soft_map[-a.id] == 3
        assert solver.soft_map[-b.id] == 0
        m.obj = 2 * b
        assert solver.soft_map[-a.id] == 0
        assert solver.soft_map[-b.id] == 2
    assert solver.clauses == hard
    assert len(m._soft) == 2
