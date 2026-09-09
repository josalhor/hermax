import pytest

from hermax.model import Model
from tests.model.test_model_incremental_native import FakeIPSolver


class _FailingUpdateSolver(FakeIPSolver):
    def __init__(self, formula=None):
        super().__init__(formula=formula)
        self.fail_updates = False

    def set_soft(self, lit: int, weight: int) -> None:
        if self.fail_updates:
            raise RuntimeError("synthetic live soft update failure")
        super().set_soft(lit, weight)


class _FailingBindSolver(FakeIPSolver):
    def add_soft_relaxed(self, clause, weight, relaxation_lit):
        raise RuntimeError("synthetic relaxed-soft bind failure")


def test_incremental_soft_update_failure_does_not_diverge_model_from_backend():
    model = Model()
    a = model.bool("a")
    ref = model.obj.add_soft(~a, 5)
    solver = _FailingUpdateSolver()
    model.solve(incremental=True, backend="maxsat", solver=solver)
    solver.fail_updates = True

    with pytest.raises(RuntimeError, match="synthetic live soft update failure"):
        model.obj.update_soft(ref, 9)

    soft_id = ref.soft_ids[0]
    soft_index = model._soft_id_to_index[soft_id]
    assert model._soft[soft_index][0] == 5
    assert model._soft_raw_weight_by_id[soft_id] == 5.0


def test_incremental_maxsat_bind_failure_does_not_leave_partial_binding():
    model = Model()
    a = model.bool("a")
    b = model.bool("b")
    model.obj.add_soft(a | b, 3)

    with pytest.raises(RuntimeError, match="synthetic relaxed-soft bind failure"):
        model.solve(incremental=True, backend="maxsat", solver=_FailingBindSolver)

    assert model._inc_state.mode is None
    assert model._inc_state.ip_solver is None
    assert model._inc_state.soft_lit_by_id == {}
