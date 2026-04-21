from typing import Callable, List, Optional

import hermax.core.cashwmaxsat as cashwmaxsat
from pysat.formula import WCNF

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus


class CASHWMaxSATSolver(ReplayFormulaSolverBase):
    """Replay wrapper for CASHWMaxSAT backend."""

    nonunit_soft_policy = "relax"

    def __init__(
        self,
        formula: Optional[WCNF] = None,
        disable_scip: bool = True,
        *args,
        **kwargs,
    ):
        self._backend_ctor = cashwmaxsat.CASHWMaxSAT
        self._scip_disabled = bool(disable_scip)
        self._terminate_callback: Optional[Callable[[], int]] = None
        self.solver = None
        super().__init__(formula=formula, *args, **kwargs)
        self.solver = self._backend_ctor()

    def disable_scip(self) -> None:
        self._scip_disabled = True

    def _rebuild_backend(self) -> None:
        self.solver = self._backend_ctor()
        if self._scip_disabled:
            self.solver.setNoScip()
        if self._terminate_callback is not None:
            self.solver.set_terminate(self._terminate_callback)

        for _ in range(self._num_vars):
            self.solver.newVar()
        for cl in self._hard_clauses:
            self.solver.addClause([int(x) for x in cl], None)
        for lit, w in self._soft_unit_by_lit.items():
            self.solver.addClause([int(lit)], int(w))

    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        if self.solver is None or isinstance(self.solver, self._backend_ctor):
            self._rebuild_backend()
        if assumptions:
            self.solver.assume([int(x) for x in assumptions])

        code = int(self.solver.solve())
        if code == int(SolveStatus.OPTIMUM):
            st = SolveStatus.OPTIMUM
        elif code == int(SolveStatus.INTERRUPTED_SAT):
            st = SolveStatus.INTERRUPTED_SAT
        elif code == int(SolveStatus.UNSAT):
            st = SolveStatus.UNSAT
        elif code == int(SolveStatus.INTERRUPTED):
            st = SolveStatus.INTERRUPTED
        else:
            st = SolveStatus.ERROR

        if st in {SolveStatus.OPTIMUM, SolveStatus.INTERRUPTED_SAT}:
            model: List[int] = []
            for i in range(1, self._num_vars + 1):
                v = self.solver.getValue(i)
                if v is True:
                    model.append(i)
                elif v is False:
                    model.append(-i)
                else:
                    model.append(i)
            return ReplaySolveResult(status=st, model=model, cost=int(self.solver.getCost()))

        return ReplaySolveResult(status=st, model=None, cost=None)

    def signature(self) -> str:
        if self.solver is None:
            return "CASHWMaxSAT"
        return self.solver.signature()

    def close(self) -> None:
        self.solver = None
        super().close()

    def set_terminate(self, callback: Optional[Callable[[], int]]) -> None:
        self._terminate_callback = callback
        if getattr(self, "solver", None) is not None and hasattr(self.solver, "set_terminate"):
            self.solver.set_terminate(callback)
