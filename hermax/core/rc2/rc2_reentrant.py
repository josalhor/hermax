from __future__ import annotations

from typing import List, Optional

from pysat.formula import WCNF

from .rc2 import RC2
from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus

_INT32_MAX = 2_147_483_647
_INT32_MIN_PLUS1 = -2_147_483_648 + 1
_UINT64_MAX = (1 << 64) - 1


class RC2Reentrant(ReplayFormulaSolverBase):
    """RC2 replay baseline wrapper (rebuild per solve)."""

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
        wcnf = WCNF()

        max_var = self._num_vars
        for cl in self._hard_clauses:
            wcnf.append([int(x) for x in cl])
            for lit in cl:
                max_var = max(max_var, abs(int(lit)))

        for a in assumptions:
            wcnf.append([int(a)])
            max_var = max(max_var, abs(int(a)))

        for lit, w in self._soft_unit_by_lit.items():
            wcnf.append([int(lit)], weight=int(w))
            max_var = max(max_var, abs(int(lit)))

        for cl, w in self._soft_nonunit:
            wcnf.append([int(x) for x in cl], weight=int(w))
            for lit in cl:
                max_var = max(max_var, abs(int(lit)))

        wcnf.nv = max(int(getattr(wcnf, "nv", 0)), int(max_var))

        try:
            with RC2(wcnf) as rc2:
                model = rc2.compute()
                if model is None:
                    return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)
                return ReplaySolveResult(
                    status=SolveStatus.OPTIMUM,
                    model=[int(x) for x in model],
                    cost=int(rc2.cost),
                )
        except Exception:
            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)

    def signature(self) -> str:
        return "rc2-reentrant-ipamir (RC2 baseline, rebuild per solve)"

    def set_terminate(self, callback) -> None:
        raise NotImplementedError("set_terminate is not supported by rc2-reentrant baseline")
