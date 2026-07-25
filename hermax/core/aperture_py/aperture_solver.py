from __future__ import annotations

import importlib
import importlib.util
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_native_incremental_base import NativeIncrementalSolverBase
from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible

_MAX_I32 = (1 << 31) - 1
_MAX_U64 = (1 << 64) - 1


class ApertureSolver(NativeIncrementalSolverBase):
    """Incremental MaxSAT adapter for the native Aperture IPAMIR backend."""

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("hermax.core._aperture_native") is not None

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        backend = importlib.import_module("hermax.core._aperture_native")
        self.solver = backend.Aperture()
        self._anon_soft_by_lit: dict[int, int] = {}
        super().__init__(formula=formula, *args, **kwargs)

    def _normalize_lit(self, lit: int) -> int:
        ilit = super()._normalize_lit(lit)
        if abs(ilit) > _MAX_I32:
            raise OverflowError(f"Literal exceeds Aperture's int32 range: {lit}")
        return ilit

    @staticmethod
    def _normalize_nonnegative_weight(weight: int) -> int:
        value = NativeIncrementalSolverBase._normalize_nonnegative_weight(weight)
        if value > _MAX_U64:
            raise OverflowError(f"Weight exceeds Aperture's uint64 range: {weight}")
        return value

    def _backend_new_var(self, var_id: int) -> None:
        allocated = int(self.solver.new_var())
        if allocated != var_id:
            raise RuntimeError(f"Aperture allocated variable {allocated}, expected {var_id}.")

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
        # Aperture's IPAMIR wrapper charges a weighted literal when that
        # literal is true. Hermax set_soft(lit, weight) represents a soft unit
        # clause [lit], so its violation literal has the opposite polarity.
        self.solver.set_soft(-ilit, w)
        self._anon_soft_by_lit[ilit] = w
        self._record_soft_unit(ilit, w)
        self._invalidate_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), self._normalize_positive_weight(weight))

    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None) -> bool:
        self._validate_live_time_limit(time_limit)
        self._require_open()
        self._invalidate_solution()
        assumps = self._normalize_assumptions(assumptions)
        for lit in assumps:
            self.solver.assume(lit)
        result = int(self.solver.solve())

        if result in (int(SolveStatus.OPTIMUM), int(SolveStatus.INTERRUPTED_SAT)):
            model = []
            for var in range(1, self.num_vars + 1):
                value = int(self.solver.value(var))
                model.append(var if value == var else -var)
            for lit in assumps:
                model[abs(lit) - 1] = abs(lit) if lit > 0 else -abs(lit)
            self._set_feasible_result(
                model=model,
                cost=int(self.solver.objective_value()),
                status=SolveStatus(result),
            )
        elif result == int(SolveStatus.UNSAT):
            self._set_infeasible_result(status=SolveStatus.UNSAT)
        elif result == int(SolveStatus.INTERRUPTED):
            self._set_infeasible_result(status=SolveStatus.INTERRUPTED)
        else:
            self._set_infeasible_result(status=SolveStatus.ERROR)
        self._maybe_raise_on_abnormal(raise_on_abnormal)
        return is_feasible(self._status)

    def signature(self) -> str:
        self._require_open()
        return str(self.solver.signature())

    def close(self) -> None:
        if getattr(self, "solver", None) is not None:
            self.solver = None
        super().close()
