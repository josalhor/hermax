from __future__ import annotations

from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus


def _load_cgss_backend():
    from .vendor.rc2_wce import RC2WCE

    return RC2WCE


class _CGSSBaseSolver(ReplayFormulaSolverBase):
    """Re-encoding wrapper around vendored certified-cgss RC2WCE."""

    _pmres_default = False
    _signature = "CGSS (RC2WCE+SS)"
    nonunit_soft_policy = "store"

    @classmethod
    def is_available(cls) -> bool:
        try:
            _ = _load_cgss_backend()
            return True
        except Exception:
            return False

    @staticmethod
    def _normalize_positive_weight(weight: int) -> int:
        if isinstance(weight, bool):
            raise TypeError("Weight must be an int")
        return ReplayFormulaSolverBase._normalize_positive_weight(weight)

    @staticmethod
    def _normalize_nonnegative_weight(weight: int) -> int:
        if isinstance(weight, bool):
            raise TypeError("Weight must be an int")
        return ReplayFormulaSolverBase._normalize_nonnegative_weight(weight)

    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        wcnf = WCNF()
        for cl in self._hard_clauses:
            wcnf.append([int(x) for x in cl])
        for lit, w in self._soft_unit_by_lit.items():
            wcnf.append([int(lit)], weight=int(w))
        for cl, w in self._soft_nonunit:
            wcnf.append([int(x) for x in cl], weight=int(w))
        for a in assumptions:
            wcnf.append([int(a)])
        wcnf.nv = max(int(getattr(wcnf, "nv", 0)), int(self._num_vars))

        try:
            backend_cls = _load_cgss_backend()
            backend = backend_cls(
                wcnf,
                adapt=True,
                exhaust=True,
                minz=True,
                structure_sharing_opts=None,
                no_wce=False,
                pmres=bool(self._pmres_default),
                verbose=0,
            )
            model = backend.compute()
            if model is None:
                return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)
            return ReplaySolveResult(
                status=SolveStatus.OPTIMUM,
                model=[int(x) for x in model],
                cost=int(getattr(backend, "cost", 0)),
            )
        except SystemExit:
            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)
        except Exception:
            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)

    def signature(self) -> str:
        return self._signature


class CGSSSolver(_CGSSBaseSolver):
    _pmres_default = False
    _signature = "CGSS (RC2WCE vendored)"


class CGSSPMRESSolver(_CGSSBaseSolver):
    _pmres_default = True
    _signature = "CGSS-PMRES (RC2WCE vendored)"
