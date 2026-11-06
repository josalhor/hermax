from __future__ import annotations

import importlib
import importlib.util
import math
from typing import List, Optional
from itertools import chain

from hermax.internal._clause_storage import ClauseStorage

from hermax.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.ipamir_state_mixin import IPAMIRStateMixin
from hermax.core.time_limits import validate_time_limit
from hermax.core.utils import extract_wcnf_data, normalize_wcnf_formula

_MAX_I32 = (1 << 31) - 1
_MAX_I64 = (1 << 63) - 1


class CoreTrailSolver(IPAMIRStateMixin, IPAMIRSolver):
    """Thin IPAMIR adapter for the native resumable CoreTrail backend."""

    supports_float_weights = True

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
        return backend.CoreTrail(
            WCNF(), solver="g4", adapt=True, exhaust=True, minz=False,
            blo="div", trim=0, full_stratified=True, nohard=True,
        )

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
    def _normalize_positive_weight(weight):
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            raise ValueError("Weight must be a positive integer or finite float.")
        if isinstance(weight, float) and not math.isfinite(weight):
            raise ValueError("Weight must be finite.")
        if isinstance(weight, int) and weight > _MAX_I64:
            raise OverflowError(f"Weight exceeds CoreTrail's int64 range: {weight}")
        return weight

    @staticmethod
    def _normalize_nonnegative_weight(weight):
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0:
            raise ValueError("Weight must be a non-negative integer or finite float.")
        if isinstance(weight, float) and not math.isfinite(weight):
            raise ValueError("Weight must be finite.")
        if isinstance(weight, int) and weight > _MAX_I64:
            raise OverflowError(f"Weight exceeds CoreTrail's int64 range: {weight}")
        return weight

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
        data = extract_wcnf_data(formula)
        bulk_hards = getattr(self.solver, '_add_hard_packed', None)
        native_hards = isinstance(data.hard, ClauseStorage) and callable(bulk_hards)
        max_var = max(data.num_vars, data.hard.max_var if native_hards else 0)
        hards_to_validate = () if native_hards else data.hard
        for clause in chain(hards_to_validate, (cl for cl, _ in data.soft)):
            for lit in clause:
                max_var = max(max_var, abs(self._normalize_lit(lit)))
        if max_var > _MAX_I32:
            raise OverflowError("Variable count exceeds CoreTrail's int32 range.")
        self._ensure_var(max_var)
        self.add_clauses(data.hard)
        for clause, weight in data.soft:
            if not clause:
                raise ValueError("Invalid empty soft clause in WCNF.")
            if len(clause) == 1:
                self.add_soft_unit(clause[0], weight)
            else:
                self.add_soft_relaxed(list(clause), weight, self.new_var())

    def new_var(self) -> int:
        self._require_open()
        self._num_vars += 1
        self._invalidate_solution()
        return self._num_vars

    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        self.solver.add_clause(self._normalize_clause(clause))
        self._invalidate_solution()

    def add_clauses(self, clauses) -> None:
        self._require_open()
        bulk = getattr(self.solver, '_add_hard_packed', None)
        if isinstance(clauses, ClauseStorage) and callable(bulk):
            max_var = clauses.max_var
            if max_var > _MAX_I32:
                raise OverflowError("Literal exceeds CoreTrail's int32 range.")
            self._ensure_var(max_var)
            bulk(clauses._storage)
            self._invalidate_solution()
        else:
            super().add_clauses(clauses)

    def set_soft(self, lit: int, weight: int | float) -> None:
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
            native_cost = self.solver.get_cost()
            self._set_result(
                status=status,
                model=self.solver.get_model(),
                cost=native_cost,
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
        if self.solver is not None:
            self.solver.close()
            self.solver = None
        super().close()
