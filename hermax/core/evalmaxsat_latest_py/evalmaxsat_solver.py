import hermax.core.evalmaxsat_latest as evalmaxsat_latest
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus


class EvalMaxSATLatestSolver(ReplayFormulaSolverBase):
    """Replay wrapper for the latest EvalMaxSAT backend."""

    nonunit_soft_policy = "relax"

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        self._backend_ctor = evalmaxsat_latest.EvalMaxSAT
        self.solver = None
        super().__init__(formula=formula, *args, **kwargs)

    def _rebuild_backend(self) -> None:
        self.solver = self._backend_ctor()
        for _ in range(self._num_vars):
            self.solver.newVar()
        self.solver.setNInputVars(self._num_vars)
        for cl in self._hard_clauses:
            self.solver.addClause([int(x) for x in cl], None)
        for lit, w in self._soft_unit_by_lit.items():
            self.solver.addClause([int(lit)], int(w))

    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        self._rebuild_backend()
        for lit in assumptions:
            self.solver.addClause([int(lit)], None)

        res = bool(self.solver.solve())
        if res:
            model = []
            for i in range(1, self._num_vars + 1):
                model.append(i if self.solver.getValue(i) else -i)
            return ReplaySolveResult(status=SolveStatus.OPTIMUM, model=model, cost=int(self.solver.getCost()))

        return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)

    def signature(self) -> str:
        return "EvalMaxSAT (Latest)"

    def close(self) -> None:
        self.solver = None
        super().close()
