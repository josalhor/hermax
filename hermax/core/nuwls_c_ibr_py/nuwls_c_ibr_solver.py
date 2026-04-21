from __future__ import annotations

import importlib
import importlib.util
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus


class NuWLSCIBRSolver(ReplayFormulaSolverBase):
    """
    NuWLS-c-IBR fake-incremental wrapper (rebuild-on-solve).

    This is an incomplete solver. Feasible solves are reported as
    ``INTERRUPTED_SAT`` (a valid model was found, but optimality is not proven).
    """

    nonunit_soft_policy = "relax"

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("hermax.core.nuwls_c_ibr") is not None

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        if not self.is_available():
            raise RuntimeError("NuWLS-c-IBR native module is not available in this build.")
        nuwls_native = importlib.import_module("hermax.core.nuwls_c_ibr")
        self._backend_ctor = nuwls_native.NuWLSCIBR
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
            return ReplaySolveResult(
                status=SolveStatus.INTERRUPTED_SAT,
                model=model,
                cost=None,
            )

        return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)

    def signature(self) -> str:
        return "NuWLS-c-IBR (NuWLS-c / BLS, native rebuild wrapper)"

    def close(self) -> None:
        self.solver = None
        super().close()

    def set_terminate(self, callback):
        raise NotImplementedError("set_terminate is not supported by NuWLS-c-IBR wrapper")
