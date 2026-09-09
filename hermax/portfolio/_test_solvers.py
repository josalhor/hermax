from __future__ import annotations

from typing import List, Optional
import time

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible


class BadModelCostSolver(IPAMIRSolver):
    """Test helper that intentionally returns an invalid model/cost pair."""

    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._model: Optional[List[int]] = None
        self._cost = None

    def add_clause(self, clause: list[int]) -> None:
        pass

    def set_soft(self, lit: int, weight: int) -> None:
        pass

    def add_soft_unit(self, lit: int, weight: int) -> None:
        pass

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False,
        time_limit: Optional[float] = None,
    ) -> bool:
        self._model = [-1, -2, -3]
        self._cost = 0
        self._status = SolveStatus.OPTIMUM
        return True

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("No cost")
        return int(self._cost)

    def val(self, lit: int) -> int:
        if self._model is None:
            raise RuntimeError("No model")
        s = set(self._model)
        lit = int(lit)
        return 1 if lit in s else -1 if -lit in s else 0

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._status):
            raise RuntimeError("No model")
        return list(self._model) if self._model is not None else None

    def signature(self) -> str:
        return "BadModelCostSolver(test helper)"

    def close(self) -> None:
        pass


class ContradictoryModelSolver(BadModelCostSolver):
    """Test helper that returns both polarities of one variable."""

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False,
        time_limit: Optional[float] = None,
    ) -> bool:
        self._model = [1, -1]
        self._cost = 0
        self._status = SolveStatus.OPTIMUM
        return True

    def signature(self) -> str:
        return "ContradictoryModelSolver(test helper)"


class NonIntegerModelSolver(BadModelCostSolver):
    """Test helper that returns a model containing a non-integer literal."""

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False,
        time_limit: Optional[float] = None,
    ) -> bool:
        self._model = [1.5]  # type: ignore[list-item]
        self._cost = 0
        self._status = SolveStatus.OPTIMUM
        return True

    def signature(self) -> str:
        return "NonIntegerModelSolver(test helper)"


class NonIntegerCostSolver(BadModelCostSolver):
    """Test helper that reports a cost which is not an integer."""

    def __init__(self, raw_cost=1.5, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raw_cost = raw_cost

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False,
        time_limit: Optional[float] = None,
    ) -> bool:
        self._model = [-1]
        self._cost = self.raw_cost
        self._status = SolveStatus.OPTIMUM
        return True

    def get_cost(self):
        if not is_feasible(self._status):
            raise RuntimeError("No cost")
        return self._cost

    def signature(self) -> str:
        return "NonIntegerCostSolver(test helper)"


class SlowTestSolver(BadModelCostSolver):
    """Worker fixture that stays alive long enough for deadline tests."""

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False,
        time_limit: Optional[float] = None,
    ) -> bool:
        time.sleep(0.5)
        self._status = SolveStatus.INTERRUPTED
        self._model = None
        self._cost = None
        return False

    def signature(self) -> str:
        return "SlowTestSolver(test helper)"
