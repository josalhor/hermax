from __future__ import annotations

import sys
from typing import List, Optional

from pysat.formula import WCNF

import hermax.core.urmaxsat_comp_py as _urmaxsat
from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus


class UWrMaxSATCompReentrant(ReplayFormulaSolverBase):
    """Replay wrapper around UWrMaxSAT competition backend."""

    nonunit_soft_policy = "store"

    def _normalize_nonnegative_weight(self, weight: int) -> int:
        w = ReplayFormulaSolverBase._normalize_nonnegative_weight(weight)
        if sys.platform in {"win32", "darwin"} and w >= (1 << 63) - 1:
            raise ValueError("Weight exceeds platform-safe range for UWrMaxSATComp backend.")
        return w

    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        solver = _urmaxsat.UWrMaxSAT()

        current_max = self._num_vars
        for a in assumptions:
            current_max = max(current_max, abs(int(a)))

        for _ in range(current_max):
            solver.newVar()

        for cl in self._hard_clauses:
            solver.addClause([int(x) for x in cl], None)

        for a in assumptions:
            solver.addClause([int(a)], None)

        if not self._soft_unit_by_lit and not self._soft_nonunit:
            guard_var = current_max + 1
            while current_max < guard_var:
                solver.newVar()
                current_max += 1
            solver.addClause([guard_var], 1)

        for lit, w in self._soft_unit_by_lit.items():
            solver.addClause([int(lit)], int(w))

        for cl, w in self._soft_nonunit:
            solver.addClause([int(x) for x in cl], int(w))

        try:
            r = int(solver.solve())
            if r == int(SolveStatus.OPTIMUM):
                model = []
                for i in range(1, current_max + 1):
                    v = solver.getValue(i)
                    if v is True:
                        model.append(i)
                    elif v is False:
                        model.append(-i)
                    else:
                        model.append(-i)
                cost = 0 if (not self._soft_unit_by_lit and not self._soft_nonunit) else int(solver.getCost())
                return ReplaySolveResult(status=SolveStatus.OPTIMUM, model=model, cost=cost)

            if r == int(SolveStatus.UNSAT):
                return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)

            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)
        except Exception:
            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)

    def signature(self) -> str:
        return "urmaxsat-comp-reentrant-ipamir"
