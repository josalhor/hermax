from __future__ import annotations

from typing import List, Optional

from pysat.formula import WCNF

import hermax.core.evalmaxsat_latest as evalmaxsat_latest
from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus

_INT32_MAX = 2_147_483_647
_INT32_MIN_PLUS1 = -2_147_483_648 + 1
_UINT64_MAX = (1 << 64) - 1


class EvalMaxSATLatestReentrant(ReplayFormulaSolverBase):
    """Re-encoding replay wrapper for EvalMaxSAT latest backend."""

    nonunit_soft_policy = "store"

    def _normalize_lit(self, lit: int) -> int:
        ilit = super()._normalize_lit(lit)
        if ilit > _INT32_MAX or ilit < _INT32_MIN_PLUS1:
            raise ValueError(f"Literal {ilit} out of 32-bit IPAMIR range")
        return ilit

    @staticmethod
    def _normalize_positive_weight(weight: int) -> int:
        w = ReplayFormulaSolverBase._normalize_positive_weight(weight)
        if w > _UINT64_MAX:
            raise OverflowError(f"Weight {w} exceeds uint64")
        return w

    @staticmethod
    def _normalize_nonnegative_weight(weight: int) -> int:
        w = ReplayFormulaSolverBase._normalize_nonnegative_weight(weight)
        if w > _UINT64_MAX:
            raise OverflowError(f"Weight {w} exceeds uint64")
        return w

    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        solver = evalmaxsat_latest.EvalMaxSAT()

        current_max = self._num_vars
        for a in assumptions:
            current_max = max(current_max, abs(int(a)))

        for _ in range(current_max):
            solver.newVar()
        solver.setNInputVars(current_max)

        for cl in self._hard_clauses:
            solver.addClause([int(x) for x in cl], None)
        for a in assumptions:
            solver.addClause([int(a)], None)
        for lit, w in self._soft_unit_by_lit.items():
            solver.addClause([int(lit)], int(w))
        for cl, w in self._soft_nonunit:
            solver.addClause([int(x) for x in cl], int(w))

        try:
            res = solver.solve()
            if not res:
                return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)
            return ReplaySolveResult(
                status=SolveStatus.OPTIMUM,
                model=[int(x) for x in solver.getModel()],
                cost=int(solver.getCost()),
            )
        except Exception:
            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)

    def signature(self) -> str:
        return "evalmaxsat-latest-reentrant-ipamir (rebuild per solve)"

    def set_terminate(self, callback) -> None:
        raise NotImplementedError("set_terminate is not supported by evalmaxsat-latest-reentrant")
