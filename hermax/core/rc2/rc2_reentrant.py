from __future__ import annotations

from typing import List, Optional

from pysat.formula import WCNF

from .rc2 import RC2Stratified
from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible
from hermax.core.time_limits import validate_time_limit

_INT32_MAX = 2_147_483_647
_INT32_MIN_PLUS1 = -2_147_483_648 + 1
_UINT64_MAX = (1 << 64) - 1


class RC2Reentrant(ReplayFormulaSolverBase):
    """RC2 replay baseline wrapper (rebuild per solve)."""

    nonunit_soft_policy = "store"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._incumbent_callback = None

    def _set_incumbent_callback(self, callback) -> None:
        self._incumbent_callback = callback

    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None) -> bool:
        if time_limit is None:
            return super().solve(assumptions, raise_on_abnormal, time_limit)

        self._require_open()
        limit = validate_time_limit(time_limit)
        assumps = self._normalize_assumptions(assumptions)
        from hermax.portfolio.solver import PortfolioSolver

        portfolio = PortfolioSolver(
            [type(self)], per_solver_time_limit_s=limit,
            overall_time_limit_s=limit, max_workers=1,
        )
        try:
            # Reserve original IDs before introducing relaxation variables.
            for _ in range(self._num_vars):
                portfolio.new_var()
            for clause in self._hard_clauses:
                portfolio.add_clause(list(clause))
            for lit, weight in self._soft_unit_by_lit.items():
                if weight > 0:
                    portfolio.add_soft_unit(lit, weight)
            for clause, weight in self._soft_nonunit:
                relax = portfolio.new_var()
                portfolio.add_soft_relaxed(list(clause), weight, relax)
            self._invalidate_solution()
            portfolio.solve(assumptions=assumps, time_limit=limit)
            status = portfolio.get_status()
            model = None
            cost = None
            if is_feasible(status):
                model = [lit for lit in portfolio.get_model() if abs(lit) <= self._num_vars]
                cost = self._compute_wrapper_cost(model)
            self._set_result(status=status, model=model, cost=cost, num_vars=self._num_vars)
        finally:
            portfolio.close()
        self._maybe_raise_on_abnormal(raise_on_abnormal)
        return is_feasible(self._status)

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

        wcnf.nv = max(int(wcnf.nv), int(max_var))

        try:
            def report(model):
                if self._incumbent_callback is None:
                    return
                present = {abs(lit) for lit in model}
                complete = sorted([*model, *(-v for v in range(1, self._num_vars + 1)
                                             if v not in present)], key=abs)
                self._incumbent_callback(complete, self._compute_wrapper_cost(complete))

            with RC2Stratified(wcnf, on_model=report if self._incumbent_callback else None) as rc2:
                # A single weight level has no intermediate stages. Obtain a
                # feasible fallback before optimization when reporting is enabled.
                if self._incumbent_callback and rc2.oracle.solve():
                    rc2._report_model()
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
