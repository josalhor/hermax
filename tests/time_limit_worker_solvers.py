"""Deterministic worker fixtures for process-control tests."""

from __future__ import annotations

import os
import signal
import time

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible


class _WorkerSolver(IPAMIRSolver):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_var = 0
        self._model = None
        self._cost = None

    def add_clause(self, clause):
        for lit in clause:
            self._max_var = max(self._max_var, abs(int(lit)))

    def new_var(self):
        self._max_var += 1
        return self._max_var

    def set_soft(self, lit, weight):
        self._max_var = max(self._max_var, abs(int(lit)))

    def add_soft_unit(self, lit, weight):
        self.set_soft(lit, weight)

    def _set_incumbent(self):
        self._model = list(range(1, self._max_var + 1))
        self._cost = 0
        self._status = SolveStatus.INTERRUPTED_SAT

    def get_status(self):
        return self._status

    def get_cost(self):
        if not is_feasible(self._status):
            raise RuntimeError("No feasible result")
        return int(self._cost)

    def val(self, lit):
        if self._model is None:
            raise RuntimeError("No model")
        return 1 if int(lit) > 0 else -1

    def get_model(self):
        if not is_feasible(self._status):
            raise RuntimeError("No feasible result")
        return list(self._model)

    def signature(self):
        return type(self).__name__

    def close(self):
        pass


class FastOptimalSolver(_WorkerSolver):
    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        self._model = list(range(1, self._max_var + 1))
        self._cost = 0
        self._status = SolveStatus.OPTIMUM
        return True


class SigintIncumbentSolver(_WorkerSolver):
    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        interrupted = False

        def on_sigint(_signum, _frame):
            nonlocal interrupted
            interrupted = True

        previous = signal.signal(signal.SIGINT, on_sigint)
        try:
            while not interrupted:
                time.sleep(0.01)
        finally:
            signal.signal(signal.SIGINT, previous)
        self._set_incumbent()
        return True


class IgnoreSigintSolver(_WorkerSolver):
    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        time.sleep(30)
        return False


class SigintErrorSolver(_WorkerSolver):
    """Lets SIGINT raise KeyboardInterrupt, which the worker reports as an error."""

    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        while True:
            time.sleep(0.01)


class CrashSolver(_WorkerSolver):
    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        os._exit(86)


class ErrorSolver(_WorkerSolver):
    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        raise RuntimeError("intentional worker error")


class NoResponseSolver(_WorkerSolver):
    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        os._exit(0)
