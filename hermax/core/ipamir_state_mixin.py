from __future__ import annotations

from typing import List, Optional

from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible


class IPAMIRStateMixin:

    _ABNORMAL_STATUSES = {
        SolveStatus.INTERRUPTED,
        SolveStatus.ERROR,
        SolveStatus.UNKNOWN,
    }

    def _init_ipamir_state(self) -> None:
        self._closed: bool = False
        self._status: SolveStatus = SolveStatus.UNKNOWN
        self._model: Optional[List[int]] = None
        self._last_cost: Optional[int] = None

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Solver is closed")

    def _invalidate_solution(self) -> None:
        self._status = SolveStatus.UNKNOWN
        self._model = None
        self._last_cost = None

    def _set_result(
        self,
        *,
        status: SolveStatus,
        model: Optional[List[int]] = None,
        cost: Optional[int] = None,
        num_vars: Optional[int] = None,
        pad_missing_with_negative: bool = True,
    ) -> None:
        self._status = status

        if model is None:
            self._model = None
        else:
            out = [int(x) for x in model]
            if num_vars is not None:
                n = int(num_vars)
                if n < 0:
                    raise ValueError("num_vars must be non-negative")
                if len(out) < n:
                    if not pad_missing_with_negative:
                        raise ValueError("Model is shorter than num_vars")
                    for i in range(len(out) + 1, n + 1):
                        out.append(-i)
                out = out[:n]
            self._model = out

        self._last_cost = None if cost is None else int(cost)

    def _maybe_raise_on_abnormal(self, raise_on_abnormal: bool) -> None:
        if raise_on_abnormal and self._status in self._ABNORMAL_STATUSES:
            raise RuntimeError(f"Solver terminated with abnormal status: {self._status.name}")

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        self._require_open()
        if not is_feasible(self._status):
            raise RuntimeError("Cost is only available for feasible status.")
        if self._last_cost is None:
            raise RuntimeError("Objective value unavailable")
        return int(self._last_cost)

    def get_model(self) -> Optional[List[int]]:
        self._require_open()
        if not is_feasible(self._status):
            raise RuntimeError("No model available")
        return list(self._model) if self._model is not None else None

    def val(self, lit: int) -> int:
        self._require_open()
        if not is_feasible(self._status) or self._model is None:
            raise RuntimeError("No model available")

        lit = int(lit)
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")

        num_vars = len(self._model)
        v = abs(lit)
        if v > num_vars:
            raise ValueError("Invalid literal for val().")

        m = self._model[v - 1]
        return 1 if m == (v if lit > 0 else -v) else -1

    def close(self) -> None:
        self._closed = True
        self._invalidate_solution()
