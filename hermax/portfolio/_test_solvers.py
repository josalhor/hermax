from __future__ import annotations

from typing import List, Optional

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

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
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
