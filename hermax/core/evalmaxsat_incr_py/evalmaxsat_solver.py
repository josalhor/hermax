from __future__ import annotations

from typing import List, Optional

import hermax.core.evalmaxsat_incr as evalmaxsat_incr
from pysat.formula import WCNF

from hermax.core.ipamir_native_incremental_base import NativeIncrementalSolverBase
from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible


class EvalMaxSATIncrSolver(NativeIncrementalSolverBase):
    """True-native incremental wrapper for EvalMaxSAT-Incr (IPAMIR backend)."""

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        self.solver = evalmaxsat_incr.EvalMaxSATIncr()
        self._soft_by_lit: dict[int, int] = {}
        self._pending_soft_updates: dict[int, int] = {}
        super().__init__(formula=formula, *args, **kwargs)

    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        cl = self._normalize_clause(clause)
        self.solver.addClause([int(x) for x in cl], None)
        self._invalidate_solution()

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        ilit = self._normalize_lit(lit)
        w = self._normalize_nonnegative_weight(weight)
        self._ensure_var(abs(ilit))
        # Keep Python-side last-write semantics and flush to native at solve().
        # This avoids duplicate pre-solve accumulation in the native backend.
        if w == 0:
            self._soft_by_lit.pop(int(ilit), None)
        else:
            self._soft_by_lit[int(ilit)] = int(w)
        self._pending_soft_updates[int(ilit)] = int(w)
        self._invalidate_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        w = self._normalize_positive_weight(weight)
        self.set_soft(int(lit), int(w))

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._require_open()
        self._invalidate_solution()
        assumps = self._normalize_assumptions(assumptions)
        for lit, w in self._pending_soft_updates.items():
            # IPAMIR add_soft_lit(L, W): assigning L=True incurs W.
            # set_soft(lit, w): penalize lit=False -> add_soft_lit(-lit, w).
            self.solver.addSoftLit(-int(lit), int(w))
        self._pending_soft_updates.clear()
        if assumps:
            self.solver.assume([int(x) for x in assumps])

        code = int(self.solver.solve())
        if code == int(SolveStatus.OPTIMUM):
            model = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                model.append(i if v is True else -i)
            self._set_feasible_result(model, int(self.solver.getCost()), status=SolveStatus.OPTIMUM)
        elif code == int(SolveStatus.INTERRUPTED_SAT):
            model = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                model.append(i if v is True else -i)
            self._set_feasible_result(model, int(self.solver.getCost()), status=SolveStatus.INTERRUPTED_SAT)
        elif code == int(SolveStatus.UNSAT):
            self._set_infeasible_result(status=SolveStatus.UNSAT)
        elif code == int(SolveStatus.INTERRUPTED):
            self._set_infeasible_result(status=SolveStatus.INTERRUPTED)
        else:
            self._set_infeasible_result(status=SolveStatus.ERROR)

        self._maybe_raise_on_abnormal(raise_on_abnormal)
        return is_feasible(self._status)

    def signature(self) -> str:
        return self.solver.signature()

    def close(self) -> None:
        self.solver = None
        self._soft_by_lit.clear()
        self._pending_soft_updates.clear()
        super().close()
