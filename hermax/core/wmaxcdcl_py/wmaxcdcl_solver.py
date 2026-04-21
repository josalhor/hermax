from __future__ import annotations

import importlib
import importlib.util
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus


class WMaxCDCLSolver(ReplayFormulaSolverBase):
    """
    WMaxCDCL fake-incremental wrapper (rebuild-on-solve).

    This wrapper caches hard clauses and unit soft literals in Python and creates
    a fresh WMaxCDCL backend instance on every `solve()` call.
    """

    nonunit_soft_policy = "relax"

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("hermax.core.wmaxcdcl") is not None

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        if not self.is_available():
            raise RuntimeError("WMaxCDCL native module is not available in this build.")
        wmaxcdcl_native = importlib.import_module("hermax.core.wmaxcdcl")
        self._backend_ctor = wmaxcdcl_native.WMaxCDCL
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

        res = bool(self.solver.solve(None))
        if res:
            model = [int(x) for x in self.solver.getModel()]
            return ReplaySolveResult(status=SolveStatus.OPTIMUM, model=model, cost=None)

        return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)

    def signature(self) -> str:
        return "WMaxCDCL (plain, rebuild-per-solve)"

    def close(self) -> None:
        self.solver = None
        super().close()
