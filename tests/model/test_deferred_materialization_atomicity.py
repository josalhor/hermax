import pytest

from hermax.encoder import PBCompiler
from hermax.model import Model


def test_failed_deferred_pb_commit_preserves_pending_constraint(monkeypatch):
    model = Model()
    a = model.bool("a")
    b = model.bool("b")
    model &= a + b <= 1
    before_pending = list(model._pending_pb_constraints)
    before_hard = list(model._hard)

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic encoder failure")

    monkeypatch.setattr(PBCompiler, "compile_batch_with_options", staticmethod(fail))
    with pytest.raises(RuntimeError, match="synthetic encoder failure"):
        model._commit_pb()

    assert model._pending_pb_constraints == before_pending
    assert model._hard == before_hard


def test_late_deferred_pb_failure_does_not_leave_partial_hard_formula(monkeypatch):
    model = Model()
    a, b, c, d = (model.bool(name) for name in "abcd")
    model &= a + b <= 1
    model &= c + d <= 1
    before_pending = list(model._pending_pb_constraints)

    original = PBCompiler.compile_batch_with_options
    calls = 0

    def fail_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic late encoder failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(PBCompiler, "compile_batch_with_options", staticmethod(fail_on_second))
    with pytest.raises(RuntimeError, match="synthetic late encoder failure"):
        model._commit_pb()

    assert model._pending_pb_constraints == before_pending
    assert model._hard == []
