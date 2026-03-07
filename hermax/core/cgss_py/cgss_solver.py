from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula

def _load_cgss_backend():
    # Vendored implementation (copied from certified-cgss and patched to keep
    # imports local to this package).
    from .vendor.rc2_wce import RC2WCE

    return RC2WCE


class _CGSSBaseSolver(IPAMIRSolver):
    """
    Re-encoding wrapper around vendored certified-cgss RC2WCE.

    This is fake-incremental: every solve() rebuilds a WCNF and runs a fresh
    backend instance.
    """

    _pmres_default = False
    _signature = "CGSS (RC2WCE+SS)"

    @classmethod
    def is_available(cls) -> bool:
        try:
            _ = _load_cgss_backend()
            return True
        except Exception:
            return False

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)

        if not self.is_available():
            raise RuntimeError("CGSS backend is not available in this build.")

        self._closed: bool = False
        self._hard_clauses: List[List[int]] = []
        self._soft_unit_by_lit: Dict[int, int] = {}
        self._soft_nonunit: List[Tuple[List[int], int]] = []
        self._max_var: int = 0

        self._last_status: SolveStatus = SolveStatus.UNKNOWN
        self._last_model: Optional[List[int]] = None
        self._last_model_set: Set[int] = set()
        self._last_cost: Optional[int] = None

        if formula is not None:
            self._load_initial_formula(formula)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Solver is closed")

    def _invalidate_last_solution(self) -> None:
        self._last_status = SolveStatus.UNKNOWN
        self._last_model = None
        self._last_model_set.clear()
        self._last_cost = None

    def _bump_max_var_from_clause(self, cl: Iterable[int]) -> None:
        for lit in cl:
            self._max_var = max(self._max_var, abs(int(lit)))

    def _validate_clause_literals(self, cl: Iterable[int]) -> None:
        for lit in cl:
            if int(lit) == 0:
                raise ValueError("Literal 0 is invalid in clauses")

    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        cl = [int(x) for x in clause]
        self._validate_clause_literals(cl)
        self._hard_clauses.append(cl)
        self._bump_max_var_from_clause(cl)
        self._invalidate_last_solution()

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        lit = int(lit)
        if not isinstance(weight, int) or isinstance(weight, bool):
            raise TypeError("Weight must be an int")
        w = int(weight)
        if lit == 0:
            raise ValueError("Literal 0 is invalid")
        if w < 0:
            raise ValueError("Weight must be non-negative")
        if w == 0:
            self._soft_unit_by_lit.pop(lit, None)
        else:
            self._soft_unit_by_lit[lit] = w
        self._max_var = max(self._max_var, abs(lit))
        self._invalidate_last_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        if not isinstance(weight, int) or int(weight) <= 0:
            raise ValueError("Weight must be positive")
        self.set_soft(lit, weight)

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._require_open()
        self._invalidate_last_solution()

        assumps = [int(a) for a in assumptions] if assumptions else []
        for a in assumps:
            if a == 0:
                raise ValueError("Assumptions must be non-zero literals")
            self._max_var = max(self._max_var, abs(a))

        # Build replayed formula
        wcnf = WCNF()
        for cl in self._hard_clauses:
            wcnf.append(list(cl))
        for lit, w in self._soft_unit_by_lit.items():
            wcnf.append([int(lit)], weight=int(w))
        for cl, w in self._soft_nonunit:
            wcnf.append(list(cl), weight=int(w))
        for a in assumps:
            wcnf.append([int(a)])

        # Keep variable count explicit for external-model completion.
        wcnf.nv = max(int(wcnf.nv), int(self._max_var))

        try:
            backend_cls = _load_cgss_backend()
            backend = backend_cls(
                wcnf,
                adapt=True,
                exhaust=True,
                minz=True,
                # Keep CGSS isolated from custom cardenc native requirements:
                # vendored RC2WCE defaults are patched so None disables SS path.
                structure_sharing_opts=None,
                no_wce=False,
                pmres=bool(self._pmres_default),
                verbose=0,
            )
            model = backend.compute()
            if model is None:
                self._last_status = SolveStatus.UNSAT
                return False

            self._last_status = SolveStatus.OPTIMUM
            self._last_model = [int(x) for x in model]
            if len(self._last_model) < self._max_var:
                for i in range(len(self._last_model) + 1, self._max_var + 1):
                    self._last_model.append(-i)
            self._last_model_set = set(self._last_model)
            self._last_cost = int(getattr(backend, "cost", 0))
            return True
        except SystemExit as e:
            self._last_status = SolveStatus.ERROR
            if raise_on_abnormal:
                raise RuntimeError(f"CGSS backend exited unexpectedly: {e}") from e
            return False
        except Exception:
            self._last_status = SolveStatus.ERROR
            if raise_on_abnormal:
                raise
            return False

    def get_status(self) -> SolveStatus:
        return self._last_status

    def get_cost(self) -> int:
        self._require_open()
        if not is_feasible(self._last_status):
            raise RuntimeError("Objective not available; last status is not SAT/OPTIMUM")
        if self._last_cost is None:
            raise RuntimeError("Objective value unavailable")
        return int(self._last_cost)

    def val(self, lit: int) -> int:
        self._require_open()
        if not is_feasible(self._last_status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        lit = int(lit)
        if lit == 0:
            raise ValueError("Literal 0 is invalid")
        if lit in self._last_model_set:
            return 1
        if -lit in self._last_model_set:
            return -1
        return 0

    def get_model(self) -> Optional[List[int]]:
        self._require_open()
        if not is_feasible(self._last_status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        return list(self._last_model) if self._last_model is not None else None

    def signature(self) -> str:
        return self._signature

    def close(self) -> None:
        self._closed = True
        self._hard_clauses.clear()
        self._soft_unit_by_lit.clear()
        self._soft_nonunit.clear()
        self._last_model = None
        self._last_model_set.clear()
        self._last_cost = None
        self._last_status = SolveStatus.UNKNOWN

    def new_var(self) -> int:
        self._require_open()
        self._max_var += 1
        return self._max_var

    def _load_initial_formula(self, formula: WCNF) -> None:
        for cl in getattr(formula, "hard", []):
            self.add_clause(list(map(int, cl)))

        soft_attr = getattr(formula, "soft", [])
        wghts = getattr(formula, "wght", None)
        if wghts is not None and len(wghts) == len(soft_attr) and (not soft_attr or not isinstance(soft_attr[0], tuple)):
            for cl, w in zip(soft_attr, wghts):
                cl = list(map(int, cl))
                if len(cl) == 1:
                    self.add_soft_unit(cl[0], int(w))
                else:
                    self._soft_nonunit.append((cl, int(w)))
                    self._bump_max_var_from_clause(cl)
        else:
            for item in soft_attr:
                if isinstance(item, tuple) and len(item) >= 2:
                    cl, w = item[0], int(item[1])
                else:
                    cl, w = item, 1
                cl = list(map(int, cl))
                if len(cl) == 1:
                    self.add_soft_unit(cl[0], int(w))
                else:
                    self._soft_nonunit.append((cl, int(w)))
                    self._bump_max_var_from_clause(cl)


class CGSSSolver(_CGSSBaseSolver):
    """
    CGSS wrapper (vendored RC2WCE core-guided variant).
    """

    _pmres_default = False
    _signature = "CGSS (RC2WCE vendored)"


class CGSSPMRESSolver(_CGSSBaseSolver):
    """
    CGSS wrapper using PMRES relaxation in vendored RC2WCE.
    """

    _pmres_default = True
    _signature = "CGSS-PMRES (RC2WCE vendored)"
