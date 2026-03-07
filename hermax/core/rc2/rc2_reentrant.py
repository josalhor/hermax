# rc2_reentrant.py
# A re-encoding RC2 wrapper that mimics an IPAMIR-like interface.
# It is NOT incrementally reentrant; it rebuilds the RC2 problem each solve().
# Useful as a correctness baseline for truly incremental solvers.

from __future__ import annotations

import abc
from enum import IntEnum
from typing import List, Optional, Callable, Dict, Tuple, Iterable, Set

from .rc2 import RC2

from pysat.formula import WCNF
from hermax.core.ipamir_solver_interface import IPAMIRSolver, is_feasible, is_final, SolveStatus
from hermax.core.utils import normalize_wcnf_formula

# -------------------- RC2 re-encoding wrapper --------------------

_INT32_MAX = 2_147_483_647
_INT32_MIN_PLUS1 = -2_147_483_648 + 1  # avoid negation overflow per IPAMIR

_UINT64_MAX = (1 << 64) - 1


def _check_literal(l: int) -> None:
    if not isinstance(l, int):
        raise TypeError(f"Literal must be int, got {type(l)}")
    if l == 0:
        raise ValueError("Literal 0 is invalid")
    if l > _INT32_MAX or l < _INT32_MIN_PLUS1:
        raise ValueError(f"Literal {l} out of 32-bit IPAMIR range")


def _check_clause(cl: Iterable[int]) -> List[int]:
    cl = list(cl)
    for l in cl:
        _check_literal(l)
    # Reject tautology? We accept tautologies; they won't affect RC2. No need to filter.
    return cl


def _check_weight(w: int) -> int:
    if not isinstance(w, int):
        raise TypeError(f"Weight must be int, got {type(w)}")
    if w <= 0:
        raise ValueError("Weight must be positive")
    if w > _UINT64_MAX:
        raise OverflowError(f"Weight {w} exceeds uint64")
    return w


def _check_weight_nonnegative(w: int) -> int:
    if not isinstance(w, int):
        raise TypeError(f"Weight must be int, got {type(w)}")
    if w < 0:
        raise ValueError("Weight must be non-negative")
    if w > _UINT64_MAX:
        raise OverflowError(f"Weight {w} exceeds uint64")
    return w


class RC2Reentrant(IPAMIRSolver):
    """
    RC2-A: A re-encoding wrapper around the RC2 MaxSAT solver.
    This solver is NOT natively incremental; it mimics the IPAMIR interface 
    by rebuilding the WCNF problem and re-solving it with RC2 for each solve call.

    RC2 is a widely used MaxSAT solver from the PySAT toolkit, and this 
    wrapper allows it to be used within the unified IPAMIR interface.
    """

    def __init__(self, formula=None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self._closed: bool = False

        # Stored problem state
        self._hard_clauses: List[List[int]] = []
        self._soft_unit_by_lit: Dict[int, int] = {}
        self._soft_unit_with_id: Dict[str, Tuple[int, int]] = {}
        self._soft_nonunit: List[Tuple[List[int], int]] = []

        self._max_var: int = 0

        # Last solution
        self._last_status: SolveStatus = SolveStatus.UNKNOWN
        self._last_model: Optional[List[int]] = None
        self._last_model_set: Set[int] = set()
        self._last_cost: Optional[int] = None

        # Load initial formula if provided (best-effort, supports WCNF variants)
        if formula is not None:
            self._load_initial_formula(formula)

    # -------------- IPAMIR-like API --------------

    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        cl = _check_clause(clause)
        self._hard_clauses.append(cl)
        self._bump_max_var_from_clause(cl)
        self._invalidate_last_solution()

        
    def set_soft(self, lit: int, weight: int) -> None:
        """Declare or update a unit soft [lit] with overwrite-by-literal semantics.
        Last call wins: the weight for this literal becomes `weight`.

        Special case:
            ``weight == 0`` removes this literal from the objective.
        """
        self._require_open()
        _check_literal(lit)
        w = _check_weight_nonnegative(weight)
        lit = int(lit)
        if w == 0:
            self._soft_unit_by_lit.pop(lit, None)
        else:
            self._soft_unit_by_lit[lit] = int(w)
        self._max_var = max(self._max_var, abs(int(lit)))
        self._invalidate_last_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        _check_literal(lit)
        w = _check_weight(weight)
        # idempotent by literal; last-wins
        self._soft_unit_by_lit[int(lit)] = int(w)
        self._max_var = max(self._max_var, abs(int(lit)))
        self._invalidate_last_solution()


    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        # print('pre-solving!')
        self._require_open()
        self._invalidate_last_solution()

        # Build WCNF
        wcnf = self._build_wcnf(assumptions)

        # Run RC2 to completion; RC2 is a complete MaxSAT solver, so only OPTIMUM/UNSAT expected
        try:
            # print('solving 1')
            with RC2(wcnf) as rc2:
                model = rc2.compute()
                # print('solved')
                if model is None:
                    self._last_status = SolveStatus.UNSAT
                    self._last_model = None
                    self._last_cost = None
                    self._last_model_set.clear()
                    return False
                # OPTIMUM found
                self._last_status = SolveStatus.OPTIMUM
                self._last_model = list(model)
                self._last_model_set = set(self._last_model)
                self._last_cost = int(rc2.cost)
                return True
        except Exception as e:
            # Enter ERROR state
            self._last_status = SolveStatus.ERROR
            self._status = SolveStatus.ERROR
            self._last_model = None
            self._last_cost = None
            self._last_model_set.clear()
            if raise_on_abnormal:
                raise
            return False

    def get_status(self) -> SolveStatus:
        return self._last_status

    def get_cost(self) -> int:
        self._require_open()
        if not is_feasible(self._last_status):
            raise RuntimeError("Objective not available; last status is not SAT/OPTIMUM")
        assert self._last_cost is not None
        return int(self._last_cost)

    def val(self, lit: int) -> int:
        self._require_open()
        if not is_feasible(self._last_status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        _check_literal(lit)
        if lit in self._last_model_set:
            return 1
        if -lit in self._last_model_set:
            return -1
        return 0

    def get_model(self) -> Optional[List[int]]:
        self._require_open()
        if not is_feasible(self._last_status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        assert self._last_model is not None
        return list(self._last_model)

    def signature(self) -> str:
        # Simple static signature
        return "rc2-reentrant-ipamir (RC2 baseline, rebuild per solve)"

    def close(self) -> None:
        # Nothing persistent to free, but mark closed and drop state
        self._closed = True
        self._hard_clauses.clear()
        self._soft_nonunit.clear()
        self._soft_unit_by_lit.clear()
        self._soft_unit_with_id.clear()
        self._soft_nonunit.clear()
        self._last_model = None
        self._last_model_set.clear()
        self._last_cost = None
        self._last_status = SolveStatus.UNKNOWN

    # Optional features

    def new_var(self) -> int:
        """Return a fresh variable id safe to be used by the caller in future clauses."""
        self._require_open()
        self._max_var += 1
        return self._max_var

    def set_terminate(self, callback: Optional[Callable[[], int]]) -> None:
        """
        Termination not supported in this baseline wrapper.
        We can't preempt RC2's internal SAT calls, so this is intentionally unimplemented.
        """
        raise NotImplementedError("set_terminate is not supported by rc2-reentrant baseline")

    # -------------- Internal helpers --------------

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Solver is closed")

    def _invalidate_last_solution(self) -> None:
        self._last_status = SolveStatus.UNKNOWN
        self._last_model = None
        self._last_model_set.clear()
        self._last_cost = None

    def _bump_max_var_from_clause(self, cl: Iterable[int]) -> None:
        for l in cl:
            self._max_var = max(self._max_var, abs(l))

    def _load_initial_formula(self, formula) -> None:
        # Best-effort load for WCNF-like objects.
        # Hard
        for cl in getattr(formula, "hard", []):
            cl = _check_clause(cl)
            if len(cl) == 0:
                self._hard_unsat = True
            else:
                self._hard_clauses.append(cl)
                self._bump_max_var_from_clause(cl)
        # Soft
        soft_attr = getattr(formula, "soft", [])
        if soft_attr:
            # PySAT variants:
            #  - new: soft is list of clauses, weights in formula.wght
            #  - sometimes: soft is list of (clause, weight) tuples
            wghts = getattr(formula, "wght", None)
            if wghts is not None and len(wghts) == len(soft_attr) and (not soft_attr or not isinstance(soft_attr[0], tuple)):
                for cl, w in zip(soft_attr, wghts):
                    cl = _check_clause(cl)
                    w = _check_weight(int(w))
                    if len(cl) == 1:
                        lit = cl[0]
                        self._soft_unit_by_lit[lit] = w
                        self._max_var = max(self._max_var, abs(lit))
                    else:
                        self._soft_nonunit.append((cl, w))
                        self._bump_max_var_from_clause(cl)

            else:
                # Expect (clause, weight) pairs
                for item in soft_attr:
                    if isinstance(item, tuple) and len(item) >= 2:
                        cl = _check_clause(item[0])
                        w = _check_weight(int(item[1]))
                    else:
                        # Fallback: treat as unweighted soft with weight=1
                        cl = _check_clause(item)
                        w = 1
                    if len(cl) == 1:
                        lit = cl[0]
                        self._soft_unit_by_lit[lit] = w
                        self._max_var = max(self._max_var, abs(lit))
                    else:
                        self._soft_nonunit.append((cl, w))
                        self._bump_max_var_from_clause(cl)


    def _build_wcnf(self, assumptions: Optional[List[int]]) -> WCNF:
        wcnf = WCNF()
        # Ensure nv large enough
        wcnf.nv = max(
            self._max_var,
            max((abs(a) for a in assumptions or []), default=0)
        )

        # Hard clauses
        for cl in self._hard_clauses:
            wcnf.append(cl)

        # Assumptions modeled as hard unit clauses for this solve
        if assumptions:
            for a in assumptions:
                _check_literal(a)
            for a in assumptions:
                wcnf.append([a])

        # id-based unit softs (independent)
        for lit, w in self._soft_unit_with_id.values():
            if abs(lit) > wcnf.nv: wcnf.nv = abs(lit)
            wcnf.append([int(lit)], weight=int(w))

        # anonymous unit softs (deduped by literal)
        for lit, w in self._soft_unit_by_lit.items():
            if abs(lit) > wcnf.nv: wcnf.nv = abs(lit)
            wcnf.append([int(lit)], weight=int(w))

        # legacy non-unit softs from loader only
        for cl, w in self._soft_nonunit:
            for l in cl:
                if abs(l) > wcnf.nv: wcnf.nv = abs(l)
            wcnf.append(list(cl), weight=int(w))

        return wcnf
