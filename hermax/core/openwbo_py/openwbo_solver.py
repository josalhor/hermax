from typing import List, Optional

import hermax.core.openwbo as openwbo
from pysat.formula import WCNF

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus


class _OpenWBOSolverBase(ReplayFormulaSolverBase):
    """Replay base for OpenWBO solver variants."""

    nonunit_soft_policy = "relax"

    def __init__(self, formula: Optional[WCNF] = None, solver_backend=None, *args, **kwargs):
        if solver_backend is None:
            raise ValueError("solver_backend must be provided.")
        self._backend_ctor = solver_backend
        self.solver = None
        super().__init__(formula=formula, *args, **kwargs)
        self.solver = self._backend_ctor()

    def _rebuild_backend(self) -> None:
        self.solver = self._backend_ctor()
        for _ in range(self._num_vars):
            self.solver.newVar()
        for cl in self._hard_clauses:
            self.solver.addClause([int(x) for x in cl], None)
        for lit, w in self._soft_unit_by_lit.items():
            self.solver.addClause([int(lit)], int(w))

    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        self._rebuild_backend()
        sat = bool(self.solver.solve(assumptions if assumptions else None))

        if not sat:
            return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)

        model: List[int] = []
        for i in range(1, self._num_vars + 1):
            model.append(i if self.solver.getValue(i) else -i)

        for a in assumptions:
            vi = abs(int(a))
            if 1 <= vi <= self._num_vars:
                model[vi - 1] = vi if int(a) > 0 else -vi

        return ReplaySolveResult(status=SolveStatus.OPTIMUM, model=model, cost=None)

    def signature(self) -> str:
        return "Open-WBO (base)"

    def close(self) -> None:
        self.solver = None
        super().close()


class OLLSolver(_OpenWBOSolverBase):
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        super().__init__(formula, solver_backend=openwbo.OLL, *args, **kwargs)

    def signature(self) -> str:
        return "Open-WBO (OLL)"


class PartMSU3Solver(_OpenWBOSolverBase):
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        super().__init__(formula, solver_backend=openwbo.PartMSU3, *args, **kwargs)

    def set_soft(self, lit: int, weight: int) -> None:
        if int(weight) == 0:
            super().set_soft(lit, 0)
            return
        if int(weight) != 1:
            raise ValueError("PartMSU3 only supports soft weight 1.")
        super().set_soft(lit, int(weight))

    def signature(self) -> str:
        return "Open-WBO (PartMSU3)"


class AutoOpenWBOSolver(_OpenWBOSolverBase):
    """Automatic Open-WBO solver that selects OLL, PartMSU3, or MSU3."""

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        super().__init__(formula, solver_backend=openwbo.Auto, *args, **kwargs)

    def signature(self) -> str:
        return "Open-WBO (Auto)"
