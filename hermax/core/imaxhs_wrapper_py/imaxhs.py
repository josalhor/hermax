from __future__ import annotations

import importlib
import importlib.util
import os
from typing import Callable, List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_native_incremental_base import NativeIncrementalSolverBase
from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible

_MAX_I64 = (1 << 63) - 1


def _import_backend():
    if os.environ.get("FORCE_IMAXHS_NOT_COMPILED", "").strip() == "1":
        raise ImportError("FORCE_IMAXHS_NOT_COMPILED=1")
    return importlib.import_module("hermax.core.imaxhs_py")


class IMaxHSSolver(NativeIncrementalSolverBase):
    @classmethod
    def is_available(cls) -> bool:
        if os.environ.get("FORCE_IMAXHS_NOT_COMPILED", "").strip() == "1":
            return False
        spec = importlib.util.find_spec("hermax.core.imaxhs_py")
        return spec is not None

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        if not self.is_available():
            raise RuntimeError(
                "IMaxHS native module is not available in this build "
                "(likely built without CPLEX)."
            )
        backend = _import_backend()
        self.solver = backend.IMaxHS()
        self._last_solve_result: Optional[int] = None
        self._anon_soft_by_lit: dict[int, int] = {}
        self._terminate_cb: Optional[Callable[[], int]] = None
        super().__init__(formula=formula, *args, **kwargs)

    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        cl = self._normalize_clause(clause)
        self.solver.addClause([int(x) for x in cl], None)
        self._record_hard_clause(cl)
        self._invalidate_solution()

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        ilit = self._normalize_lit(lit)
        w = self._normalize_nonnegative_weight(weight)
        if int(w) > _MAX_I64:
            raise OverflowError(f"Weight exceeds int64 max: {weight}")
        self._ensure_var(abs(ilit))
        if w == 0:
            raise NotImplementedError(
                "set_soft(lit, 0) is not supported by this native incremental backend."
            )

        self.solver.addClause([int(ilit)], int(w))
        self._anon_soft_by_lit[int(ilit)] = int(w)
        self._record_soft_unit(ilit, w)
        self._invalidate_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), self._normalize_positive_weight(weight))

    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None) -> bool:
        self._validate_live_time_limit(time_limit)
        self._require_open()
        self._invalidate_solution()
        if self._terminate_cb is not None and int(self._terminate_cb()) != 0:
            self._set_infeasible_result(status=SolveStatus.INTERRUPTED)
            self._last_solve_result = int(SolveStatus.INTERRUPTED)
            self._maybe_raise_on_abnormal(raise_on_abnormal)
            return is_feasible(self._status)

        assumps = self._normalize_assumptions(assumptions)
        if assumps:
            self.solver.assume([int(x) for x in assumps])

        r = int(self.solver.solve())
        self._last_solve_result = r

        if r == int(SolveStatus.OPTIMUM):
            model: list[int] = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                if v is True:
                    model.append(i)
                elif v is False:
                    model.append(-i)
                elif i in assumps:
                    model.append(i)
                elif -i in assumps:
                    model.append(-i)
                else:
                    model.append(-i)
            for a in assumps:
                vi = abs(int(a))
                if 1 <= vi <= self.num_vars:
                    model[vi - 1] = vi if a > 0 else -vi
            self._set_feasible_result(
                model=model,
                cost=self._compute_cost_from_model(model),
                status=SolveStatus.OPTIMUM,
            )
            self._maybe_raise_on_abnormal(raise_on_abnormal)
            return is_feasible(self._status)

        if r == int(SolveStatus.INTERRUPTED_SAT):
            model = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                if v is True:
                    model.append(i)
                elif v is False:
                    model.append(-i)
                elif i in assumps:
                    model.append(i)
                elif -i in assumps:
                    model.append(-i)
                else:
                    model.append(-i)
            self._set_feasible_result(
                model=model,
                cost=self._compute_cost_from_model(model),
                status=SolveStatus.INTERRUPTED_SAT,
            )
            self._maybe_raise_on_abnormal(raise_on_abnormal)
            return is_feasible(self._status)

        if r == int(SolveStatus.UNSAT):
            self._set_infeasible_result(status=SolveStatus.UNSAT)
        elif r == int(SolveStatus.INTERRUPTED):
            self._set_infeasible_result(status=SolveStatus.INTERRUPTED)
        else:
            self._set_infeasible_result(status=SolveStatus.ERROR)
        self._maybe_raise_on_abnormal(raise_on_abnormal)
        return is_feasible(self._status)

    def _compute_cost_from_model(self, model: List[int]) -> int:
        assign_true = {lit for lit in model if lit > 0}
        cost = 0
        for lit, w in self._anon_soft_by_lit.items():
            v = abs(lit)
            is_true = v in assign_true
            sat = is_true if lit > 0 else (not is_true)
            if not sat:
                cost += int(w)
        return int(cost)

    def signature(self) -> str:
        return str(self.solver.signature())

    def close(self) -> None:
        if getattr(self, "solver", None) is not None:
            s = self.solver
            self.solver = None
            del s
        super().close()

    def set_terminate(self, callback: Optional[Callable[[], int]]) -> None:
        self._terminate_cb = callback
        self.solver.set_terminate(callback)
