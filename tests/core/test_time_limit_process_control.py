from __future__ import annotations

import os

import pytest

from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.core.ipamir_subprocess_replay_base import OneShotSubprocessReplaySolverBase
from hermax.internal.subprocess_oneshot import run_oneshot_worker
from hermax.model import Model
from hermax.portfolio import PortfolioSolver
from tests.time_limit_worker_solvers import (
    CrashSolver,
    ErrorSolver,
    FastOptimalSolver,
    IgnoreSigintSolver,
    NoResponseSolver,
    SigintErrorSolver,
    SigintIncumbentSolver,
)


class _FixtureReplaySolver(OneShotSubprocessReplaySolverBase):
    worker_solver_class_path = "tests.time_limit_worker_solvers.SigintIncumbentSolver"
    default_signature = "fixture-replay"
    timeout_error_prefix = "fixture"


class _NoResponseReplaySolver(OneShotSubprocessReplaySolverBase):
    worker_solver_class_path = "tests.time_limit_worker_solvers.NoResponseSolver"
    default_signature = "no-response-replay"
    timeout_error_prefix = "fixture"


class _SigintErrorReplaySolver(OneShotSubprocessReplaySolverBase):
    worker_solver_class_path = "tests.time_limit_worker_solvers.SigintErrorSolver"
    default_signature = "sigint-error-replay"
    timeout_error_prefix = "fixture"


class _ErrorReplaySolver(OneShotSubprocessReplaySolverBase):
    worker_solver_class_path = "tests.time_limit_worker_solvers.ErrorSolver"
    default_signature = "error-replay"
    timeout_error_prefix = "fixture"


def _request(cls):
    return {
        "solver_class_path": f"{cls.__module__}.{cls.__qualname__}",
        "snapshot": {"num_vars": 1, "hard_clauses": [[1]], "soft_units": [], "soft_nonunit": []},
        "assumptions": [],
    }


def test_oneshot_worker_happy_path_returns_optimum():
    run = run_oneshot_worker(_request(FastOptimalSolver), time_limit=None)

    assert run.ok
    assert not run.timed_out
    assert run.response["status"] == int(SolveStatus.OPTIMUM)
    assert run.response["model"] == [1]


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_oneshot_worker_returns_incumbent_after_sigint():
    run = run_oneshot_worker(_request(SigintIncumbentSolver), time_limit=0.2, grace_s=0.5)

    assert run.timed_out
    assert run.interrupted
    assert not run.killed
    assert run.response["status"] == int(SolveStatus.INTERRUPTED_SAT)
    assert run.response["model"] == [1]
    assert run.response["cost"] == 0


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_oneshot_worker_reports_a_structured_error_after_sigint():
    run = run_oneshot_worker(_request(SigintErrorSolver), time_limit=0.2, grace_s=0.5)

    assert run.timed_out
    assert run.interrupted
    assert not run.killed
    assert run.response is not None
    assert run.response["ok"] is False
    assert run.response["error_type"] == "KeyboardInterrupt"


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_oneshot_worker_kills_a_process_that_ignores_sigint():
    run = run_oneshot_worker(_request(IgnoreSigintSolver), time_limit=0.2, grace_s=0.05)

    assert run.timed_out
    assert run.interrupted
    assert run.killed
    assert run.response is None


@pytest.mark.parametrize("solver_class", [CrashSolver, NoResponseSolver])
def test_oneshot_worker_handles_crash_or_missing_response(solver_class):
    run = run_oneshot_worker(_request(solver_class), time_limit=1.0)

    assert not run.ok
    assert not run.timed_out
    assert run.response is None


def test_oneshot_worker_returns_a_structured_error_response():
    run = run_oneshot_worker(_request(ErrorSolver), time_limit=1.0)

    assert not run.ok
    assert not run.timed_out
    assert run.response["ok"] is False
    assert run.response["error_type"] == "RuntimeError"


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_replay_wrapper_preserves_a_timed_incumbent():
    solver = _FixtureReplaySolver()
    try:
        solver.add_clause([1])
        assert solver.solve(time_limit=0.2)
        assert solver.get_status() == SolveStatus.INTERRUPTED_SAT
        assert solver.get_model() == [1]
        assert solver.get_cost() == 0
    finally:
        solver.close()


def test_replay_wrapper_reports_a_missing_worker_response_as_error():
    solver = _NoResponseReplaySolver()
    try:
        solver.add_clause([1])
        assert not solver.solve(time_limit=1.0)
        assert solver.get_status() == SolveStatus.ERROR
    finally:
        solver.close()


def test_replay_wrapper_keeps_a_predeadline_structured_error():
    solver = _ErrorReplaySolver()
    try:
        solver.add_clause([1])
        assert not solver.solve(time_limit=1.0)
        assert solver.get_status() == SolveStatus.ERROR
    finally:
        solver.close()


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_replay_wrapper_maps_a_timed_structured_error_to_interrupted():
    solver = _SigintErrorReplaySolver()
    try:
        solver.add_clause([1])
        assert not solver.solve(time_limit=0.2)
        assert solver.get_status() == SolveStatus.INTERRUPTED
        assert solver._last_error == "timeout: KeyboardInterrupt"
    finally:
        solver.close()


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_portfolio_preserves_a_timed_incumbent():
    solver = PortfolioSolver(
        [SigintIncumbentSolver],
        per_solver_time_limit_s=1.0,
        overall_time_limit_s=1.0,
        time_limit_grace_s=0.5,
    )
    solver.add_clause([1])
    try:
        assert solver.solve(time_limit=0.2)
        assert solver.get_status() == SolveStatus.INTERRUPTED_SAT
        assert solver.get_model() == [1]
        assert solver.get_cost() == 0
        assert solver.last_run_details[0]["timed_out"]
        assert solver.last_run_details[0]["status"] == "INTERRUPTED_SAT"
    finally:
        solver.close()


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_portfolio_reports_killed_and_crashed_workers_without_a_result():
    killed = PortfolioSolver(
        [IgnoreSigintSolver],
        per_solver_time_limit_s=1.0,
        overall_time_limit_s=1.0,
        time_limit_grace_s=0.05,
    )
    try:
        assert not killed.solve(time_limit=0.2)
        assert killed.get_status() == SolveStatus.INTERRUPTED
        assert killed.last_run_details[0]["killed"]
        assert killed.last_run_details[0]["status"] == "TIMEOUT"
    finally:
        killed.close()

    crashed = PortfolioSolver([CrashSolver])
    try:
        assert not crashed.solve(time_limit=1.0)
        assert crashed.get_status() == SolveStatus.ERROR
        assert crashed.last_run_details[0]["status"] == "ERR"
    finally:
        crashed.close()


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_portfolio_maps_a_timed_structured_error_to_interrupted():
    solver = PortfolioSolver(
        [SigintErrorSolver],
        per_solver_time_limit_s=1.0,
        overall_time_limit_s=1.0,
        time_limit_grace_s=0.5,
    )
    solver.add_clause([1])
    try:
        assert not solver.solve(time_limit=0.2)
        assert solver.get_status() == SolveStatus.INTERRUPTED
        assert solver.last_run_details[0]["timed_out"]
        assert solver.last_run_details[0]["status"] == "TIMEOUT"
        assert solver.last_run_details[0]["timeout_error_type"] == "KeyboardInterrupt"
    finally:
        solver.close()


def test_portfolio_keeps_a_predeadline_structured_error():
    solver = PortfolioSolver([ErrorSolver])
    solver.add_clause([1])
    try:
        assert not solver.solve(time_limit=1.0)
        assert solver.get_status() == SolveStatus.ERROR
        assert not solver.last_run_details[0]["timed_out"]
        assert solver.last_run_details[0]["status"] == "ERR"
    finally:
        solver.close()


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_model_maps_a_timed_incumbent_to_interrupted_sat():
    model = Model()
    x = model.bool("x")
    model &= x

    result = model.solve(
        solver=SigintIncumbentSolver,
        incremental=False,
        time_limit=0.2,
    )

    assert result.ok
    assert result.status == "interrupted_sat"
    assert result.assignment[x] is True


@pytest.mark.skipif(os.name == "nt", reason="SIGINT process-group behavior is POSIX-specific")
def test_model_maps_a_timed_structured_error_to_interrupted():
    model = Model()
    model &= model.bool("x")

    result = model.solve(
        solver=SigintErrorSolver,
        incremental=False,
        time_limit=0.2,
    )

    assert not result.ok
    assert result.status == "interrupted"


def test_model_reports_a_crashed_one_shot_worker_as_error():
    model = Model()
    model &= model.bool("x")

    result = model.solve(
        solver=CrashSolver,
        incremental=False,
        time_limit=1.0,
    )

    assert not result.ok
    assert result.status == "error"
