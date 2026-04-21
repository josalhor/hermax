import sys
from typing import List, Optional, Callable

import hermax.core.urmaxsat_comp_py as _urmaxsat
from pysat.formula import WCNF

from hermax.core.ipamir_native_incremental_base import NativeIncrementalSolverBase
from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible


class UWrMaxSATCompSolver(NativeIncrementalSolverBase):
    """
    UWrMaxSAT (Competition version): A highly efficient MaxSAT solver, 
    specifically the version 1.4 used in competitions.
    This solver provides native incremental support through the IPAMIR interface.

    It is particularly optimized for competition-style benchmarks and 
    provides robust performance across a wide range of MaxSAT problems.
    """
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        self.solver = _urmaxsat.UWrMaxSAT()
        self._last_solve_result: Optional[int] = None
        # Track softs so we can compute cost from the exposed model
        self._anon_soft_by_lit: dict[int, int] = {}   # literal -> weight (last-wins)
        self._id_soft_b_weight: dict[int, int] = {}   # relax var b -> weight (for id-based softs)
        self._soft_ids: dict[str, int] = {}           # id -> relax var b
        self._hard_only_guard_installed: bool = False
        self._hard_clauses: List[List[int]] = []
        super().__init__(formula=formula, *args, **kwargs)

    
    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        cl = self._normalize_clause(clause)
        self.solver.addClause([int(x) for x in cl], None)
        self._hard_clauses.append([int(x) for x in cl])
        self._invalidate_solution()


    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        ilit = self._normalize_lit(lit)
        w = self._normalize_nonnegative_weight(weight)
        # On Windows/macOS, this backend overflows at the INT64_MAX edge.
        if sys.platform in {"win32", "darwin"} and int(w) >= (1 << 63) - 1:
            raise ValueError(
                "Weight exceeds platform-safe range for UWrMaxSATComp backend."
            )
        self._ensure_var(abs(ilit))

        if w == 0:
            self._anon_soft_by_lit.pop(int(ilit), None)
            self._rebuild_backend()
            self._invalidate_solution()
            return

        # Anonymous soft literal, last-wins by literal
        self.solver.addClause([int(ilit)], int(w))
        self._anon_soft_by_lit[int(ilit)] = int(w)
        self._invalidate_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), self._normalize_positive_weight(weight))

    # ---------- Solve ----------

    def solve(self, assumptions=None, raise_on_abnormal=False) -> bool:
        self._require_open()
        self._invalidate_solution()
        # Work around a backend crash path in UWrMaxSATComp on hard-only instances.
        # Inject a single neutral soft unit [b] with weight 1.
        # The backend can satisfy it by setting b=true, so the objective remains 0.
        if (
            not self._hard_only_guard_installed
            and not self._anon_soft_by_lit
            and not self._id_soft_b_weight
        ):
            b = self.num_vars + 1  # internal-only variable; do not expose in Python model length
            self.solver.addClause([b], 1)
            self._hard_only_guard_installed = True

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

            # Native getCost() appears unstable on hard-only traces on some platforms.
            # For formulas without user softs, objective is always 0 by definition.
            if not self._anon_soft_by_lit and not self._id_soft_b_weight:
                cost = 0
            else:
                cost = int(self.solver.getCost())
            self._set_feasible_result(model=model, cost=cost, status=SolveStatus.OPTIMUM)
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

    def _rebuild_backend(self) -> None:
        self.solver = _urmaxsat.UWrMaxSAT()
        self._hard_only_guard_installed = False
        for _ in range(self.num_vars):
            self.solver.newVar()
        for cl in self._hard_clauses:
            self.solver.addClause(cl, None)
        for lit, w in self._anon_soft_by_lit.items():
            self.solver.addClause([int(lit)], int(w))


    def signature(self) -> str:
        return str(self.solver.signature())

    def close(self) -> None:
        if getattr(self, "solver", None) is not None:
            s = self.solver
            self.solver = None
            del s
        super().close()

    def set_terminate(self, callback: Optional[Callable[[], int]]) -> None:
        if callback is None:
            # Some backend versions keep an interrupted internal state after a
            # termination callback has fired. Rebuild to clear native state.
            self._rebuild_backend()
            self.solver.set_terminate(lambda: 0)
        else:
            self.solver.set_terminate(callback)
