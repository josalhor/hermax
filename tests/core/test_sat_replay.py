from __future__ import annotations

import threading

from hermax.internal.sat_replay import PySATReplaySolver, solve_pysat_with_time_limit


def test_pysat_replay_solver_uses_journaled_hard_clauses_and_assumptions():
    solver = PySATReplaySolver("g4")
    solver.add_clause([1, 2])
    solver.add_clause([-1])

    result = solver.solve(assumptions=[-2])

    assert result.status == "unsat"
    assert solver._journal.snapshot()["hard_clauses"] == [[1, 2], [-1]]


def test_pysat_replay_solver_returns_a_sat_model():
    solver = PySATReplaySolver("g4")
    solver.ensure_var(2)
    solver.add_clause([1])

    result = solver.solve()

    assert result.status == "sat"
    assert result.model is not None
    assert 1 in result.model
    assert -2 in result.model


class _InterruptibleFakeSolver:
    def __init__(self):
        self.interrupted = threading.Event()
        self.cleared = False

    def solve(self, assumptions):
        return True

    def solve_limited(self, assumptions, expect_interrupt):
        assert expect_interrupt is True
        assert self.interrupted.wait(timeout=1.0)
        return None

    def interrupt(self):
        self.interrupted.set()

    def clear_interrupt(self):
        self.cleared = True


def test_pysat_deadline_interrupts_and_clears_the_solver():
    solver = _InterruptibleFakeSolver()

    result = solve_pysat_with_time_limit(
        solver,
        assumptions=[],
        time_limit=0.01,
    )

    assert result is None
    assert solver.interrupted.is_set()
    assert solver.cleared
