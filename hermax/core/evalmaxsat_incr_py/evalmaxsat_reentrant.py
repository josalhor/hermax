from __future__ import annotations

from typing import List, Optional

import hermax.core.evalmaxsat_incr as evalmaxsat_incr
from pysat.formula import WCNF

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus


class EvalMaxSATIncrReentrant(ReplayFormulaSolverBase):
    """Rebuild-on-solve wrapper for EvalMaxSAT-Incr backend."""

    nonunit_soft_policy = "relax"

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        self._backend_ctor = evalmaxsat_incr.EvalMaxSATIncr
        self.solver = None
        super().__init__(formula=formula, *args, **kwargs)
        self.solver = self._backend_ctor()

    def _rebuild_backend(self) -> None:
        self.solver = self._backend_ctor()
        for cl in self._hard_clauses:
            self.solver.addClause([int(x) for x in cl], None)
        for lit, w in self._soft_unit_by_lit.items():
            self.solver.addSoftLit(-int(lit), int(w))

    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        self._rebuild_backend()
        if assumptions:
            self.solver.assume([int(x) for x in assumptions])

        code = int(self.solver.solve())
        if code == int(SolveStatus.OPTIMUM):
            model = []
            for i in range(1, self._num_vars + 1):
                v = self.solver.getValue(i)
                model.append(i if v is True else -i)
            return ReplaySolveResult(
                status=SolveStatus.OPTIMUM,
                model=model,
                cost=int(self.solver.getCost()),
            )

        if code == int(SolveStatus.INTERRUPTED_SAT):
            model = []
            for i in range(1, self._num_vars + 1):
                v = self.solver.getValue(i)
                model.append(i if v is True else -i)
            return ReplaySolveResult(
                status=SolveStatus.INTERRUPTED_SAT,
                model=model,
                cost=int(self.solver.getCost()),
            )

        if code == int(SolveStatus.UNSAT):
            return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)
        if code == int(SolveStatus.INTERRUPTED):
            return ReplaySolveResult(status=SolveStatus.INTERRUPTED, model=None, cost=None)
        return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)

    def signature(self) -> str:
        if self.solver is None:
            return "EvalMaxSATIncr"
        return self.solver.signature()

    def close(self) -> None:
        self.solver = None
        super().close()
