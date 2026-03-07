from __future__ import annotations

import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Optional

import pytest

from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible
from hermax.portfolio import PortfolioSolver
from hermax.portfolio.solver import _WorkerProc, AdjustTimeout
from hermax.internal.subprocess_oneshot import _dumps_frame


class _FakeProc:
    def __init__(self, code: Optional[int]):
        self._code = code

    def poll(self):
        return self._code

    def wait(self, timeout=None):
        return self._code


@dataclass
class _Clock:
    t: float = 0.0

    def monotonic(self) -> float:
        return float(self.t)

    def sleep(self, dt: float) -> None:
        self.t += float(dt)


def _mk_done_worker(
    *,
    solver_name: str,
    status: SolveStatus,
    cost: Optional[int],
    model: Optional[list[int]],
    start_s: float = 0.0,
    timeout_s: float = 30.0,
) -> _WorkerProc:
    out = tempfile.TemporaryFile()
    err = tempfile.TemporaryFile()
    payload = {
        "ok": True,
        "status": int(status),
        "cost": cost,
        "model": model,
    }
    err.write(_dumps_frame(payload))
    err.flush()
    err.seek(0)
    return _WorkerProc(
        solver_name=solver_name,
        worker_class_path="tests.fake",
        proc=_FakeProc(0),
        stdout_file=out,
        stderr_file=err,
        start_s=float(start_s),
        deadline_s=float(start_s + timeout_s),
        timeout_s=float(timeout_s),
        grace_s=0.0,
        request_assumptions=[],
    )


def _mk_alive_worker(
    *,
    solver_name: str,
    start_s: float = 0.0,
    timeout_s: float = 30.0,
) -> _WorkerProc:
    out = tempfile.TemporaryFile()
    err = tempfile.TemporaryFile()
    return _WorkerProc(
        solver_name=solver_name,
        worker_class_path="tests.fake",
        proc=_FakeProc(None),
        stdout_file=out,
        stderr_file=err,
        start_s=float(start_s),
        deadline_s=float(start_s + timeout_s),
        timeout_s=float(timeout_s),
        grace_s=0.0,
        request_assumptions=[],
    )


def _mk_solver(*, overall_timeout_s: float = 2.5) -> PortfolioSolver:
    return PortfolioSolver(
        [RC2Reentrant, RC2Reentrant],
        formula=None,
        per_solver_timeout_s=30.0,
        overall_timeout_s=float(overall_timeout_s),
        selection_policy="best_valid_until_timeout",
        validate_model=False,
        recompute_cost_from_model=False,
    )


def test_portfolio_set_callback_accepts_legacy_zero_arg_and_event_forms():
    p = _mk_solver()

    calls = {"z": 0, "e": 0}

    def cb0():
        calls["z"] += 1

    def cb1(event):
        assert event is not None
        calls["e"] += 1

    # must not raise and must remain configurable via the same method
    p.set_callback(cb0)
    p.set_callback(cb1)
    p.set_callback(None)
    p.close()


def test_portfolio_callback_exception_is_interpreted_as_stop(monkeypatch):
    p = _mk_solver(overall_timeout_s=10.0)
    workers = [_mk_alive_worker(solver_name="W0"), _mk_alive_worker(solver_name="W1")]
    clock = _Clock(0.0)
    timed_out = {"n": 0}

    def spawn(self, cls, assumptions, now=None):
        if workers:
            return workers.pop(0)
        return None

    def timeout(self, w):
        timed_out["n"] += 1
        w.done = True
        w.exit_code = 0

    def bad_callback(_event):
        raise RuntimeError("boom")

    monkeypatch.setattr("hermax.portfolio.solver.time.monotonic", clock.monotonic)
    monkeypatch.setattr("hermax.portfolio.solver.time.sleep", clock.sleep)
    monkeypatch.setattr(PortfolioSolver, "_spawn_worker", spawn)
    monkeypatch.setattr(PortfolioSolver, "_timeout_worker", timeout)
    p.set_callback(bad_callback)

    ok = p.solve()
    assert ok is False
    assert p.get_status() in {SolveStatus.INTERRUPTED, SolveStatus.ERROR}
    assert timed_out["n"] >= 1
    p.close()


def test_portfolio_heartbeat_default_interval_is_one_second(monkeypatch):
    p = _mk_solver(overall_timeout_s=2.2)
    workers = [_mk_alive_worker(solver_name="W0")]
    clock = _Clock(0.0)
    heartbeats = {"n": 0}

    def spawn(self, cls, assumptions, now=None):
        if workers:
            return workers.pop(0)
        return None

    def timeout(self, w):
        w.done = True
        w.exit_code = 0

    def on_event(ev):
        if getattr(ev, "event_type", None) == "HEARTBEAT":
            heartbeats["n"] += 1

    monkeypatch.setattr("hermax.portfolio.solver.time.monotonic", clock.monotonic)
    monkeypatch.setattr("hermax.portfolio.solver.time.sleep", clock.sleep)
    monkeypatch.setattr(PortfolioSolver, "_spawn_worker", spawn)
    monkeypatch.setattr(PortfolioSolver, "_timeout_worker", timeout)
    p.set_callback(on_event)

    _ = p.solve()
    # around t=1.0 and t=2.0 before overall timeout
    assert heartbeats["n"] >= 2
    p.close()


def test_portfolio_incumbent_callback_strict_improvement_only_and_coalesced(monkeypatch):
    p = _mk_solver(overall_timeout_s=5.0)
    workers = [
        _mk_done_worker(solver_name="W0", status=SolveStatus.INTERRUPTED_SAT, cost=20, model=[1]),
        _mk_done_worker(solver_name="W1", status=SolveStatus.INTERRUPTED_SAT, cost=10, model=[1]),
    ]
    clock = _Clock(0.0)
    incumbent_costs: list[int] = []

    def spawn(self, cls, assumptions, now=None):
        if workers:
            return workers.pop(0)
        return None

    def timeout(self, w):
        w.done = True
        w.exit_code = 0

    def on_event(ev):
        if getattr(ev, "event_type", None) == "INCUMBENT":
            incumbent_costs.append(int(ev.cost))

    monkeypatch.setattr("hermax.portfolio.solver.time.monotonic", clock.monotonic)
    monkeypatch.setattr("hermax.portfolio.solver.time.sleep", clock.sleep)
    monkeypatch.setattr(PortfolioSolver, "_spawn_worker", spawn)
    monkeypatch.setattr(PortfolioSolver, "_timeout_worker", timeout)
    p.set_callback(on_event)

    ok = p.solve()
    assert ok is True
    assert is_feasible(p.get_status())
    # Two improvements happened before callback dispatch cadence; only latest should be sent.
    assert incumbent_costs == [10]
    p.close()


def test_portfolio_adjust_timeout_action_shortens_deadline(monkeypatch):
    p = _mk_solver(overall_timeout_s=10.0)
    workers = [_mk_alive_worker(solver_name="W0")]
    clock = _Clock(0.0)
    timed_out = {"n": 0}

    def spawn(self, cls, assumptions, now=None):
        if workers:
            return workers.pop(0)
        return None

    def timeout(self, w):
        timed_out["n"] += 1
        w.done = True
        w.exit_code = 0

    def on_event(ev):
        if getattr(ev, "event_type", None) == "HEARTBEAT":
            # new_timeout_s interpreted from now by default
            return AdjustTimeout(new_timeout_s=0.05)
        return None

    monkeypatch.setattr("hermax.portfolio.solver.time.monotonic", clock.monotonic)
    monkeypatch.setattr("hermax.portfolio.solver.time.sleep", clock.sleep)
    monkeypatch.setattr(PortfolioSolver, "_spawn_worker", spawn)
    monkeypatch.setattr(PortfolioSolver, "_timeout_worker", timeout)
    p.set_callback(on_event)

    ok = p.solve()
    assert ok is False
    assert timed_out["n"] >= 1
    p.close()
