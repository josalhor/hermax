import pytest

from hermax.model import Model
from tests.model.test_soft_behavior import FakeIPSoft


class FailingWeights(FakeIPSoft):
    fail_at = None
    fail_after_write = False

    def set_soft(self, lit, weight):
        if self.fail_at is not None:
            self.fail_at -= 1
            if self.fail_at == 0:
                if self.fail_after_write:
                    super().set_soft(lit, weight)
                raise RuntimeError("injected weight failure")
        super().set_soft(lit, weight)


def _change(m, action, flags, term):
    a, b, _, d = flags
    if action == "add":
        m.obj.add(a + 2 * b, weight=3)
    elif action == "replace":
        m.obj = a
    elif action == "clear":
        m.obj.clear()
    elif action == "precision":
        m.set_objective_precision(decimals=2)
    elif action == "update":
        m.obj.update(term, weight=3)
    elif action == "add_new":
        m.obj.add(a + 2 * d, weight=3)
    elif action == "replace_new":
        m.obj = 2 * d
    else:
        raise AssertionError(action)


@pytest.mark.parametrize(
    "action,expected",
    [("add", 17), ("replace", 1), ("clear", 0), ("precision", 8),
     ("update", 11), ("add_new", 17), ("replace_new", 2)],
)
@pytest.mark.parametrize("fail_at", [1, 2])
@pytest.mark.parametrize("fail_after_write", [False, True])
def test_failed_objective_change_preserves_cost_and_can_be_retried(
    action, expected, fail_at, fail_after_write
):
    m = Model()
    flags = m.bool_vector("b", 4)
    for flag in flags:
        m &= flag
    a, b, c, _ = flags
    if action == "precision":
        with pytest.warns(FutureWarning):
            term = m.obj.add_soft(~a, 2)
        with pytest.warns(FutureWarning):
            m.obj.add_soft(~b, 4)
        with pytest.warns(FutureWarning):
            m.obj.add_soft(~c, 2)
    else:
        term = m.obj.add(a + 2 * b, weight=2)
        m.obj.add(c, weight=2)
    generation = m.obj._generation
    backend = FailingWeights()
    m.solve(backend="maxsat", solver=backend)
    backend.fail_at, backend.fail_after_write = fail_at, fail_after_write

    with pytest.raises(RuntimeError, match="injected weight failure"):
        _change(m, action, flags, term)

    assert not m._inc_state.bound
    assert m.obj._generation == generation
    assert term.weight == 2
    assert m._objective_precision_decimals is None
    assert m.solve().cost == 8

    _change(m, action, flags, term)
    assert (m.solve().cost or 0) == expected


@pytest.mark.parametrize("action", ["add", "replace", "clear", "update"])
def test_failed_objective_change_preserves_negative_offset_and_handle(action):
    m = Model()
    a, b, c = m.bool_vector("b", 3)
    for flag in (a, b, c):
        m &= flag
    term = m.obj.add(a + b - 3, weight=2)
    m.obj.add(c, weight=5)
    backend = FailingWeights()
    m.solve(backend="maxsat", solver=backend)
    backend.fail_at = 2

    with pytest.raises(RuntimeError, match="injected weight failure"):
        _change(m, action, [a, b, c, c], term)

    assert term.weight == 2
    assert m.solve().cost == 3
    m.obj.update(term, weight=3)
    assert m.solve().cost == 2


@pytest.mark.parametrize("activate_handle", [False, True])
@pytest.mark.parametrize("fail_at", [1, 2])
def test_failed_integer_objective_change_can_reuse_its_binary_definitions(
    activate_handle, fail_at
):
    m = Model()
    a = m.bool("a")
    x = m.int("x", 0, 40)
    m &= a
    m &= x == 13
    m.obj.add(a, weight=8)
    term = m.obj.add(x - 20, weight=0)
    assert x._binary_view is None
    backend = FailingWeights()
    m.solve(backend="maxsat", solver=backend)
    backend.fail_at = fail_at

    def change():
        if activate_handle:
            m.obj.update(term, weight=2)
        else:
            m.obj.add(x - 20, weight=2)

    with pytest.raises(RuntimeError, match="injected weight failure"):
        change()

    assert term.weight == 0
    assert m.solve().cost == 8
    assert x._binary_view is not None
    change()
    result = m.solve()
    assert result[x] == 13
    assert result.cost == -6
