import pytest

from hermax.model import Model
from tests.model.test_soft_behavior import FakeIPSoft


@pytest.mark.parametrize("operation", ["add", "replace", "update", "legacy_update"])
def test_cost_inactive_at_binding_can_be_reactivated(operation):
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    m &= a
    m &= b
    if operation == "legacy_update":
        with pytest.warns(FutureWarning):
            term = m.obj.add_soft(~a, 3)
        m.obj.update(term, weight=0)
    else:
        term = m.obj.add(a, weight=3)
        if operation == "update":
            m.obj.update(term, weight=0)
        else:
            m.obj.clear()
    m.obj.add(b, weight=2)
    assert m.solve(backend="maxsat").cost == 2

    if operation == "add":
        m.obj.add(a, weight=4)
    elif operation == "replace":
        m.obj = 4 * a
    else:
        m.obj.update(term, weight=4)
    assert m.solve().cost == (4 if operation == "replace" else 6)


def test_routing_and_weight_updates_do_not_scan_all_mapped_soft_entries():
    class NoScanning(dict):
        def items(self):
            raise AssertionError("Weight updates must not scan all mapped entries")

        def values(self):
            raise AssertionError("Routing must not scan all mapped entries")

    m = Model()
    flags = m.bool_vector("b", 100)
    term = m.obj.add(sum(flags))
    backend = FakeIPSoft()
    m._inc_state.soft_lit_by_id = NoScanning()
    m.solve(backend="maxsat", solver=backend)
    m.obj.update(term, weight=2)
    assert backend.soft_map == {-flag.id: 2 for flag in flags}


def test_duplicate_units_and_rebinding_preserve_aggregate_weights():
    m = Model()
    a = m.bool("a")
    m &= a
    m.set_soft_dedup(False)
    first = m.obj.add(a, weight=2)
    with pytest.warns(FutureWarning):
        second = m.obj.add_soft(~a, 3)
    backend = FakeIPSoft()
    m.solve(backend="maxsat", solver=backend)
    for left, right in [(0, 3), (4, 0), (2, 5), (0, 0), (1, 2)]:
        m.obj.update(first, weight=left)
        m.obj.update(second, weight=right)
        assert backend.soft_map[-a.id] == left + right
    m.close_incremental()
    assert m.solve(backend="maxsat").cost == 3
