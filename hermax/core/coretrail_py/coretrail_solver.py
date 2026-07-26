from __future__ import annotations

import importlib
import importlib.util
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.ipamir_state_mixin import IPAMIRStateMixin
from hermax.core.time_limits import validate_time_limit
from hermax.core.utils import normalize_wcnf_formula

_MAX_I32 = (1 << 31) - 1
_MAX_I64 = (1 << 63) - 1


class CoreTrailSolver(IPAMIRStateMixin, IPAMIRSolver):
    """Thin IPAMIR adapter for the native resumable CoreTrail backend."""

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("hermax.core.coretrail_native") is not None

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        del args, kwargs
        IPAMIRSolver.__init__(self)
        self._init_ipamir_state()
        self._num_vars = 0
        self.solver = self._create_backend()
        formula = normalize_wcnf_formula(formula)
        if formula is not None:
            self._load_initial_formula(formula)

    @staticmethod
    def _create_backend():
        backend = importlib.import_module("hermax.core.coretrail_native")
        return backend.CoreTrail(WCNF())

    @property
    def num_vars(self) -> int:
        return self._num_vars

    def _ensure_var(self, var: int) -> None:
        while int(var) > self._num_vars:
            self.new_var()

    def _normalize_lit(self, lit: int) -> int:
        if isinstance(lit, bool) or not isinstance(lit, int):
            raise ValueError("Literal must be an integer.")
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        if abs(lit) > _MAX_I32:
            raise OverflowError(f"Literal exceeds CoreTrail's int32 range: {lit}")
        return int(lit)

    @staticmethod
    def _normalize_positive_weight(weight: int) -> int:
        if isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0:
            raise ValueError("Weight must be a positive integer.")
        if weight > _MAX_I64:
            raise OverflowError(f"Weight exceeds CoreTrail's int64 range: {weight}")
        return int(weight)

    @staticmethod
    def _normalize_nonnegative_weight(weight: int) -> int:
        if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
            raise ValueError("Weight must be a non-negative integer.")
        if weight > _MAX_I64:
            raise OverflowError(f"Weight exceeds CoreTrail's int64 range: {weight}")
        return int(weight)

    def _normalize_clause(self, clause: List[int]) -> List[int]:
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        out = [self._normalize_lit(lit) for lit in clause]
        for lit in out:
            self._ensure_var(abs(lit))
        return out

    def _normalize_assumptions(self, assumptions: Optional[List[int]]) -> List[int]:
        out = [self._normalize_lit(lit) for lit in assumptions] if assumptions else []
        for lit in out:
            self._ensure_var(abs(lit))
        return out

    def _load_initial_formula(self, formula: WCNF) -> None:
        hard = list(getattr(formula, "hard", []))
        soft = list(getattr(formula, "soft", []))
        weights = list(getattr(formula, "wght", []))
        max_var = int(getattr(formula, "nv", 0))
        for clause in [*hard, *soft]:
            for lit in clause:
                max_var = max(max_var, abs(self._normalize_lit(int(lit))))
        self._ensure_var(max_var)

        for clause in hard:
            self.add_clause([int(lit) for lit in clause])
        if len(soft) != len(weights):
            raise ValueError("WCNF soft clauses and weights must have the same length.")
        for clause, weight in zip(soft, weights):
            if not clause:
                raise ValueError("Invalid empty soft clause in WCNF.")
            if len(clause) == 1:
                self.add_soft_unit(int(clause[0]), int(weight))
            else:
                self.add_soft_relaxed([int(lit) for lit in clause], int(weight), self.new_var())

    def new_var(self) -> int:
        self._require_open()
        self._num_vars += 1
        self._invalidate_solution()
        return self._num_vars

    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        self.solver.add_clause(self._normalize_clause(clause))
        self._invalidate_solution()

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        ilit = self._normalize_lit(lit)
        w = self._normalize_nonnegative_weight(weight)
        self._ensure_var(abs(ilit))
        self.solver.set_soft(ilit, w)
        self._invalidate_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(lit, self._normalize_positive_weight(weight))

    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None) -> bool:
        self._require_open()
        limit = validate_time_limit(time_limit)
        assumps = self._normalize_assumptions(assumptions)
        self._invalidate_solution()
        self.solver.solve(assumptions=assumps, time_limit=limit)
        status = SolveStatus(int(self.solver.get_status()))

        if is_feasible(status):
            self._set_result(
                status=status,
                model=self.solver.get_model(),
                cost=int(self.solver.get_cost()),
                num_vars=self.num_vars,
            )
        elif status in {SolveStatus.UNSAT, SolveStatus.INTERRUPTED}:
            self._set_result(status=status)
        else:
            self._set_result(status=SolveStatus.ERROR)

        self._maybe_raise_on_abnormal(bool(raise_on_abnormal))
        return is_feasible(self._status)

    def signature(self) -> str:
        self._require_open()
        return str(self.solver.signature())

    def close(self) -> None:
        if getattr(self, "solver", None) is not None:
            self.solver.close()
            self.solver = None
        super().close()
