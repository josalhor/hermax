from typing import List, Optional, Callable

import hermax.core.urmaxsat_py as _urmaxsat
from pysat.formula import WCNF

from hermax.core.ipamir_native_incremental_base import NativeIncrementalSolverBase
from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible


class UWrMaxSATSolver(NativeIncrementalSolverBase):
    """
    UWrMaxSAT: an efficient MaxSAT solver based on the UWrMaxSAT 1.8 solver.
    This solver provides native incremental support through the IPAMIR interface.

    UWrMaxSAT is known for its efficiency in handling various MaxSAT instances, 
    combining modern SAT solving techniques with effective MaxSAT algorithms.
    """
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        self.solver = _urmaxsat.UWrMaxSAT()
        self._last_solve_result: Optional[int] = None
        # Track softs so we can compute cost from the exposed model
        self._anon_soft_by_lit: dict[int, int] = {}   # literal -> weight (last-wins)
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
        if w == 0:
            raise NotImplementedError(
                "set_soft(lit, 0) is not supported by this native incremental backend."
            )

        self.solver.addClause([int(ilit)], int(w))
        self._anon_soft_by_lit[int(ilit)] = int(w)
        self._invalidate_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), self._normalize_positive_weight(weight))

    # ---------- Solve ----------

    def solve(self, assumptions=None, raise_on_abnormal=False) -> bool:
        self._require_open()
        self._invalidate_solution()
        assumps = self._normalize_assumptions(assumptions)
        if assumps:
            self.solver.assume([int(x) for x in assumps])

        r = int(self.solver.solve())
        self._last_solve_result = r

        if r == int(SolveStatus.OPTIMUM):
            model = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                if v is True:
                    model.append(i)
                elif v is False:
                    model.append(-i)
                else:
                    # check if assumptions
                    if i in assumps:
                        model.append(i)
                    elif -i in assumps:
                        model.append(-i)
                    else:
                        model.append(-i)

            # Force assumptions in exposed model; some backends may return
            # partial/relaxed values even when assumptions were used for solve.
            for a in assumps:
                vi = abs(int(a))
                if 1 <= vi <= self.num_vars:
                    model[vi - 1] = vi if a > 0 else -vi

            self._set_feasible_result(
                model=model,
                cost=self._compute_cost_from_model(model),
                status=SolveStatus.OPTIMUM,
            )
        elif r == int(SolveStatus.UNSAT):
            self._set_infeasible_result(status=SolveStatus.UNSAT)
        elif r == int(SolveStatus.INTERRUPTED_SAT):
            self._set_infeasible_result(status=SolveStatus.INTERRUPTED_SAT)
        elif r == int(SolveStatus.INTERRUPTED):
            self._set_infeasible_result(status=SolveStatus.INTERRUPTED)
        else:
            self._set_infeasible_result(status=SolveStatus.ERROR)

        self._maybe_raise_on_abnormal(raise_on_abnormal)
        return is_feasible(self._status)


    # ---------- Accessors ----------

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
        self.solver.set_terminate(callback)
