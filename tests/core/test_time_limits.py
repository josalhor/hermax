import math
import threading
import time

import pytest

from hermax.core.ipamir_native_incremental_base import NativeIncrementalSolverBase
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus
from hermax.core.time_limits import validate_time_limit
from hermax.model import Model
from hermax.model.core import SolveResult
from hermax.portfolio import PortfolioSolver
from hermax.portfolio._test_solvers import SlowTestSolver


class _LiveInterruptiblePySAT:
    """Minimal PySAT double that verifies a limited live call remains reusable."""

    instances: list["_LiveInterruptiblePySAT"] = []

    def __init__(self, *, name: str):
        self.name = name
        self.clauses: list[list[int]] = []
        self.interrupted = threading.Event()
        self.clear_calls = 0
        self.limited_calls = 0
        self.solve_calls = 0
        type(self).instances.append(self)

    def append_formula(self, clauses):
        self.clauses.extend([list(clause) for clause in clauses])

    def add_clause(self, clause):
        self.clauses.append(list(clause))

    def solve_limited(self, assumptions, expect_interrupt):
        self.limited_calls += 1
        assert expect_interrupt is True
        assert self.interrupted.wait(timeout=1.0)
        return None

    def interrupt(self):
        self.interrupted.set()

    def clear_interrupt(self):
        self.clear_calls += 1
        self.interrupted.clear()

    def solve(self, assumptions):
        self.solve_calls += 1
        return True

    def get_model(self):
        return [1]

    def delete(self):
        pass


class _FakeNativeSolver(NativeIncrementalSolverBase):
    def __init__(self, *, interruptible: bool, reusable: bool):
        self.interruptible = interruptible
        self.reusable = reusable
        self.backend = []
        self.rebuilds = 0
        super().__init__()

    def signature(self):
        return "fake-native"

    def add_clause(self, clause):
        cl = self._normalize_clause(clause)
        self.backend.append(("hard", cl))
        self._record_hard_clause(cl)

    def set_soft(self, lit, weight):
        self.backend.append(("soft", int(lit), int(weight)))
        self._record_soft_unit(int(lit), int(weight))

    def add_soft_unit(self, lit, weight):
        self.set_soft(lit, weight)

    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        self._prepare_live_time_limit(time_limit)
        self._finish_live_time_limit(interrupted=time_limit is not None)
        self._set_feasible_result(
            list(range(1, self.num_vars + 1)),
            0,
            status=SolveStatus.OPTIMUM,
        )
        return True

    def _backend_new_var(self, var_id):
        self.backend.append(("var", var_id))

    def _reset_backend_for_rebuild(self):
        self.backend = []
        self.rebuilds += 1

    def _can_interrupt(self):
        return self.interruptible

    def _can_reuse_after_interrupt(self):
        return self.reusable


def test_native_solver_without_interruption_rejects_live_limit():
    solver = _FakeNativeSolver(interruptible=False, reusable=False)

    with pytest.raises(NotImplementedError, match="cannot be interrupted"):
        solver.solve(time_limit=1.0)


def test_interruptible_reusable_native_solver_needs_no_rebuild():
    solver = _FakeNativeSolver(interruptible=True, reusable=True)
    solver.add_clause([1])

    assert solver.solve(time_limit=1.0)
    assert solver.rebuilds == 0
    assert solver.backend == [("var", 1), ("hard", [1])]


def test_interruptible_nonreusable_native_solver_rebuilds_from_journal():
    solver = _FakeNativeSolver(interruptible=True, reusable=False)
    solver.add_clause([1, -2])
    solver.set_soft(-2, 3)

    with pytest.raises(RuntimeError, match="set_rebuild_on_interrupt"):
        solver.solve(time_limit=1.0)

    solver.set_rebuild_on_interrupt(True)
    assert solver.solve(time_limit=1.0)
    assert solver.rebuilds == 1
    assert solver.backend == [
        ("var", 1),
        ("var", 2),
        ("hard", [1, -2]),
        ("soft", -2, 3),
    ]


@pytest.mark.parametrize("value", [0, -1, 0.0, -0.1, math.inf, -math.inf, math.nan])
def test_time_limit_rejects_non_positive_or_non_finite_values(value):
    with pytest.raises(ValueError, match="finite positive"):
        validate_time_limit(value)


@pytest.mark.parametrize("value", [True, False, "1", object()])
def test_time_limit_rejects_values_that_are_not_numbers(value):
    with pytest.raises(TypeError, match="finite positive"):
        validate_time_limit(value)


def test_interrupted_sat_result_is_feasible():
    model = Model()
    x = model.bool("x")
    result = SolveResult(
        model,
        status="interrupted_sat",
        raw_model=[x.id],
        cost=0,
        backend="test",
    )
    assert result.ok


def test_live_model_limit_interrupts_and_keeps_the_same_sat_backend(monkeypatch):
    _LiveInterruptiblePySAT.instances.clear()
    monkeypatch.setattr("hermax.model.core.PySATSolver", _LiveInterruptiblePySAT)
    model = Model()
    x = model.bool("x")
    model &= x

    interrupted = model.solve(incremental=True, time_limit=0.01)
    assert interrupted.status == "interrupted"

    resumed = model.solve(incremental=True)
    assert resumed.status == "sat"
    assert resumed.assignment[x] is True

    assert len(_LiveInterruptiblePySAT.instances) == 1
    backend = _LiveInterruptiblePySAT.instances[0]
    assert backend.limited_calls == 1
    assert backend.clear_calls == 1
    assert backend.solve_calls == 1


def test_one_shot_pysat_model_accepts_a_time_limit():
    model = Model()
    x = model.bool("x")
    model &= x

    result = model.solve(incremental=False, time_limit=1.0)

    assert result.ok
    assert result.assignment[x] is True


def test_in_process_replay_solver_rejects_unenforceable_time_limit():
    from hermax.non_incremental import RC2

    solver = RC2()
    try:
        with pytest.raises(NotImplementedError, match="does not support time_limit"):
            solver.solve(time_limit=1.0)
    finally:
        solver.close()


def test_subprocess_replay_limit_overrides_its_default_limit():
    from hermax.non_incremental.incomplete import NuWLSCIBR

    if not NuWLSCIBR.is_available():
        pytest.skip("NuWLS-c-IBR is not available in this build")
    solver = NuWLSCIBR(default_time_limit=30.0)
    try:
        solver.add_clause([1])
        assert not solver.solve(time_limit=1e-12)
        assert solver.get_status() == SolveStatus.INTERRUPTED
    finally:
        solver.close()


def test_subprocess_wrapper_defaults_to_no_deadline_and_validates_configuration():
    from hermax.non_incremental.incomplete import NuWLSCIBR

    solver = NuWLSCIBR()
    try:
        assert solver._default_time_limit is None
    finally:
        solver.close()

    with pytest.raises(ValueError, match="finite positive"):
        NuWLSCIBR(default_time_limit=0)


def test_portfolio_per_call_limit_bounds_the_whole_run():
    portfolio = PortfolioSolver(
        [SlowTestSolver],
        per_solver_time_limit_s=1.0,
        overall_time_limit_s=1.0,
        time_limit_grace_s=0.01,
    )
    started = time.monotonic()
    try:
        assert not portfolio.solve(time_limit=0.02)
        assert portfolio.get_status() == SolveStatus.INTERRUPTED
    finally:
        portfolio.close()
    assert time.monotonic() - started < 0.5


def test_rebuild_setting_is_not_part_of_ipamir():
    assert not hasattr(IPAMIRSolver, "set_rebuild_on_interrupt")
    assert not hasattr(PortfolioSolver, "set_rebuild_on_interrupt")


def test_model_rebuild_setting_requires_boolean():
    with pytest.raises(TypeError, match="enabled must be a bool"):
        Model().set_rebuild_on_interrupt(1)


def test_model_forwards_rebuild_setting_to_a_supplied_live_solver_instance():
    model = Model()
    x = model.bool("x")
    model.obj[1] += x
    solver = _FakeNativeSolver(interruptible=True, reusable=False)

    model.set_rebuild_on_interrupt(True)
    result = model.solve(solver=solver, backend="maxsat")

    assert result.ok
    assert solver._rebuild_on_interrupt is True
