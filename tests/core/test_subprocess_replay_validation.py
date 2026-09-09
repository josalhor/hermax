import pytest

from hermax.core.ipamir_subprocess_replay_base import OneShotSubprocessReplaySolverBase
from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.internal.subprocess_oneshot import OneShotRunResult


class _ReplayProbe(OneShotSubprocessReplaySolverBase):
    worker_solver_class_path = "tests.fake.Worker"
    default_signature = "replay-probe"
    timeout_error_prefix = "replay-probe"


def _worker_result(model):
    return OneShotRunResult(
        ok=True,
        response={
            "ok": True,
            "status": int(SolveStatus.OPTIMUM),
            "signature": "fake-worker",
            "model": model,
            "cost": 0,
        },
        exit_code=0,
        timed_out=False,
        interrupted=False,
        killed=False,
        elapsed_s=0.0,
        stdout_raw=b"",
        stderr_raw=b"",
    )


@pytest.mark.xfail(
    strict=True,
    reason="OneShotSubprocessReplaySolverBase coerces worker model literals with int() before validation",
)
def test_subprocess_replay_rejects_non_integer_worker_model(monkeypatch):
    monkeypatch.setattr(
        "hermax.core.ipamir_subprocess_replay_base.run_oneshot_worker",
        lambda *args, **kwargs: _worker_result([1.5]),
    )
    solver = _ReplayProbe()
    solver.add_clause([1])

    assert solver.solve() is False
    assert solver.get_status() is SolveStatus.ERROR


@pytest.mark.xfail(
    strict=True,
    reason="OneShotSubprocessReplaySolverBase accepts a feasible worker response without a model",
)
def test_subprocess_replay_rejects_feasible_worker_response_without_model(monkeypatch):
    monkeypatch.setattr(
        "hermax.core.ipamir_subprocess_replay_base.run_oneshot_worker",
        lambda *args, **kwargs: _worker_result(None),
    )
    solver = _ReplayProbe()
    solver.add_clause([1])

    assert solver.solve() is False
    assert solver.get_status() is SolveStatus.ERROR
