from __future__ import annotations

import importlib
import importlib.util
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_native_incremental_base import NativeIncrementalSolverBase
from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible

_MAX_I32 = (1 << 31) - 1
_MAX_I64 = (1 << 63) - 1


class CoreTrailSolver(NativeIncrementalSolverBase):
    """Incremental MaxSAT adapter for the native CoreTrail backend."""

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("hermax.core.coretrail_native") is not None

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        self.solver = self._create_backend()
        super().__init__(formula=formula, *args, **kwargs)

    @staticmethod
    def _create_backend():
        backend = importlib.import_module("hermax.core.coretrail_native")
        # The shared journal owns Hermax's formula state and replays it after
        # interruption.  CoreTrail therefore starts with no duplicate formula.
        return backend.CoreTrail(WCNF())

    def _normalize_lit(self, lit: int) -> int:
        ilit = super()._normalize_lit(lit)
        if abs(ilit) > _MAX_I32:
            raise OverflowError(f"Literal exceeds CoreTrail's int32 range: {lit}")
        return ilit

    @staticmethod
    def _normalize_nonnegative_weight(weight: int) -> int:
        value = NativeIncrementalSolverBase._normalize_nonnegative_weight(weight)
        if value > _MAX_I64:
            raise OverflowError(f"Weight exceeds CoreTrail's int64 range: {weight}")
        return value

    def _can_interrupt(self) -> bool:
        return True

    def _can_reuse_after_interrupt(self) -> bool:
        return False

    def _reset_backend_for_rebuild(self) -> None:
        old_solver = self.solver
        self.solver = self._create_backend()
        old_solver.close()

    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        cl = self._normalize_clause(clause)
        self.solver.add_clause(cl)
        self._record_hard_clause(cl)
        self._invalidate_solution()

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        ilit = self._normalize_lit(lit)
        w = self._normalize_nonnegative_weight(weight)
        self._ensure_var(abs(ilit))
        self.solver.set_soft(ilit, w)
        self._record_soft_unit(ilit, w)
        self._invalidate_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), self._normalize_positive_weight(weight))

    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None) -> bool:
        self._prepare_live_time_limit(time_limit)
        self._require_open()
        self._invalidate_solution()
        assumps = self._normalize_assumptions(assumptions)
        self.solver.solve(assumptions=assumps, time_limit=time_limit)
        status = SolveStatus(int(self.solver.get_status()))
        interrupted = status in {SolveStatus.INTERRUPTED, SolveStatus.INTERRUPTED_SAT}

        if is_feasible(status):
            self._set_feasible_result(
                model=self.solver.get_model(),
                cost=int(self.solver.get_cost()),
                status=status,
            )
        elif status in {SolveStatus.UNSAT, SolveStatus.INTERRUPTED}:
            self._set_infeasible_result(status=status)
        else:
            self._set_infeasible_result(status=SolveStatus.ERROR)

        self._finish_live_time_limit(interrupted=interrupted)
        self._maybe_raise_on_abnormal(raise_on_abnormal)
        return is_feasible(self._status)

    def signature(self) -> str:
        self._require_open()
        return str(self.solver.signature())

    def close(self) -> None:
        if getattr(self, "solver", None) is not None:
            self.solver.close()
            self.solver = None
        super().close()
