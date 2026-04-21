from __future__ import annotations

import abc
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, is_feasible
from hermax.core.ipamir_state_mixin import IPAMIRStateMixin
from hermax.core.utils import normalize_wcnf_formula


class NativeIncrementalSolverBase(IPAMIRStateMixin, IPAMIRSolver, abc.ABC):

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self._init_ipamir_state()
        self.num_vars: int = 0
        if formula is not None:
            self._load_initial_formula(formula)

    def _ensure_var(self, var: int) -> None:
        while int(var) > self.num_vars:
            self.new_var()

    def _normalize_lit(self, lit: int) -> int:
        ilit = int(lit)
        if ilit == 0:
            raise ValueError("Literal 0 is invalid.")
        return ilit

    def _normalize_assumptions(self, assumptions: Optional[List[int]]) -> List[int]:
        assumps = [self._normalize_lit(x) for x in assumptions] if assumptions else []
        for lit in assumps:
            self._ensure_var(abs(lit))
        return assumps

    def _normalize_clause(self, clause: List[int]) -> List[int]:
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        out = [self._normalize_lit(x) for x in clause]
        for lit in out:
            self._ensure_var(abs(lit))
        return out

    @staticmethod
    def _normalize_positive_weight(weight: int) -> int:
        if not isinstance(weight, int):
            raise ValueError("Weight must be an integer.")
        if int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        return int(weight)

    @staticmethod
    def _normalize_nonnegative_weight(weight: int) -> int:
        if not isinstance(weight, int):
            raise ValueError("Weight must be an integer.")
        if int(weight) < 0:
            raise ValueError("Weight must be a non-negative integer.")
        return int(weight)

    def _set_feasible_result(self, model: List[int], cost: int, *, status) -> None:
        self._set_result(status=status, model=model, cost=int(cost), num_vars=self.num_vars)

    def _set_infeasible_result(self, *, status) -> None:
        self._set_result(status=status, model=None, cost=None)

    def new_var(self) -> int:
        self._require_open()
        self.num_vars += 1
        self._backend_new_var(self.num_vars)
        self._invalidate_solution()
        return self.num_vars

    def _backend_new_var(self, var_id: int) -> None:
        """Optional native hook for backends that require explicit var allocation."""
        _ = var_id

    def _load_initial_formula(self, formula: WCNF) -> None:
        max_var = 0
        all_cls = list(getattr(formula, "hard", []))
        soft_attr = getattr(formula, "soft", [])
        for item in soft_attr:
            cl = item[0] if isinstance(item, tuple) and len(item) >= 2 else item
            if isinstance(cl, list):
                all_cls.append(cl)
        for cl in all_cls:
            for lit in cl:
                ilit = int(lit)
                if ilit == 0:
                    raise ValueError("CNF contains literal 0.")
                max_var = max(max_var, abs(ilit))
        while self.num_vars < max_var:
            self.new_var()

        for clause in getattr(formula, "hard", []):
            self.add_clause([int(x) for x in clause])

        softs = getattr(formula, "soft", [])
        wghts = getattr(formula, "wght", None)
        if wghts is not None and len(wghts) == len(softs) and (not softs or not isinstance(softs[0], tuple)):
            pairs = list(zip(softs, wghts))
        else:
            pairs = []
            for item in softs:
                if isinstance(item, tuple) and len(item) >= 2:
                    pairs.append((item[0], int(item[1])))
                else:
                    pairs.append((item, 1))

        for cl, w in pairs:
            if not cl:
                raise ValueError("Invalid soft in WCNF.")
            if len(cl) == 1:
                self.add_soft_unit(int(cl[0]), int(w))
            else:
                b = self.new_var()
                self.add_soft_relaxed([int(x) for x in cl], int(w), relax_var=b)

    def get_cost(self) -> int:
        self._require_open()
        if not is_feasible(self._status):
            raise RuntimeError("Cost is only available for SAT or OPTIMUM status.")
        if self._last_cost is None:
            raise RuntimeError("Cost is only available for SAT or OPTIMUM status.")
        return int(self._last_cost)

    @abc.abstractmethod
    def signature(self) -> str:  # pragma: no cover - interface method
        raise NotImplementedError
