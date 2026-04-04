# evalmaxsat_reentrant.py
# A re-encoding EvalMaxSAT wrapper that mimics an IPAMIR-like interface.
# It is NOT incrementally reentrant; it rebuilds the EvalMaxSAT problem each solve().

from __future__ import annotations

import abc
from typing import List, Optional, Callable, Dict, Tuple, Iterable, Set

from pysat.formula import WCNF
from hermax.core.ipamir_solver_interface import IPAMIRSolver, is_feasible, is_final, SolveStatus
from hermax.core.utils import normalize_wcnf_formula
import hermax.core.evalmaxsat_latest as evalmaxsat_latest

# -------------------- EvalMaxSAT re-encoding wrapper --------------------

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
    return cl


def _check_weight(w: int) -> int:
    if not isinstance(w, int):
        raise TypeError(f"Weight must be int, got {type(w)}")
    if w <= 0:
        raise ValueError("Weight must be positive")
    if w > _UINT64_MAX:
        raise OverflowError(f"Weight {w} exceeds uint64")
    return w


class EvalMaxSATLatestReentrant(IPAMIRSolver):
    """
    EvalMaxSAT: A re-encoding wrapper around the latest version of EvalMaxSAT.
    This solver is NOT natively incremental; it mimics the IPAMIR interface 
    by rebuilding a fresh solver instance and replaying the problem for each solve call.

    EvalMaxSAT is a modern MaxSAT solver that has shown excellent performance 
    in recent MaxSAT Evaluations.
    """

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self._closed: bool = False

        # Stored problem state
        self._hard_clauses: List[List[int]] = []
        self._soft_unit_by_lit: Dict[int, int] = {}
        self._soft_nonunit: List[Tuple[List[int], int]] = []

        self._max_var: int = 0

        # Last solution
        self._last_status: SolveStatus = SolveStatus.UNKNOWN
        self._last_model: Optional[List[int]] = None
        self._last_model_set: Set[int] = set()
        self._last_cost: Optional[int] = None

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
        self._require_open()
        _check_literal(lit)
        w = _check_weight(weight)
        self._soft_unit_by_lit[int(lit)] = int(w)
        self._max_var = max(self._max_var, abs(int(lit)))
        self._invalidate_last_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(lit, weight)

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._require_open()
        self._invalidate_last_solution()

        # Instantiate fresh backend
        solver = evalmaxsat_latest.EvalMaxSAT()
        
        # Determine max var needed
        current_max = self._max_var
        if assumptions:
            for a in assumptions:
                _check_literal(a)
                current_max = max(current_max, abs(a))
        
        # Pre-size variables
        for _ in range(current_max):
            solver.newVar()
        solver.setNInputVars(current_max)

        # Replay hard clauses
        for cl in self._hard_clauses:
            solver.addClause(cl, None)

        # Replay assumptions as temporary hard unit clauses
        if assumptions:
            for a in assumptions:
                solver.addClause([a], None)

        # Replay unit softs
        for lit, w in self._soft_unit_by_lit.items():
            solver.addClause([lit], w)

        # Replay non-unit softs
        for cl, w in self._soft_nonunit:
            solver.addClause(cl, w)

        try:
            res = solver.solve()
            if res:
                self._last_status = SolveStatus.OPTIMUM
                self._last_model = solver.getModel()
                # Ensure model covers all variables up to current_max
                if len(self._last_model) < current_max:
                    for i in range(len(self._last_model) + 1, current_max + 1):
                        self._last_model.append(-i)
                self._last_model_set = set(self._last_model)
                self._last_cost = int(solver.getCost())
                return True
            else:
                self._last_status = SolveStatus.UNSAT
                self._last_model = None
                self._last_cost = None
                self._last_model_set.clear()
                return False
        except Exception:
            self._last_status = SolveStatus.ERROR
            if raise_on_abnormal:
                raise
            return False

    def get_status(self) -> SolveStatus:
        return self._last_status

    def get_cost(self) -> int:
        if not is_feasible(self._last_status):
            raise RuntimeError("Objective not available; last status is not SAT/OPTIMUM")
        return int(self._last_cost)

    def val(self, lit: int) -> int:
        if not is_feasible(self._last_status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        _check_literal(lit)
        if lit in self._last_model_set:
            return 1 if lit > 0 else -1
        if -lit in self._last_model_set:
            return -1 if lit > 0 else 1
        return 0

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._last_status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        return list(self._last_model)

    def signature(self) -> str:
        return "evalmaxsat-latest-reentrant-ipamir (rebuild per solve)"

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

    def set_terminate(self, callback: Optional[Callable[[], int]]) -> None:
        raise NotImplementedError("set_terminate is not supported by evalmaxsat-latest-reentrant")

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
        for cl in getattr(formula, "hard", []):
            cl = _check_clause(cl)
            self._hard_clauses.append(cl)
            self._bump_max_var_from_clause(cl)
        
        soft_attr = getattr(formula, "soft", [])
        wghts = getattr(formula, "wght", None)
        if wghts is not None and len(wghts) == len(soft_attr) and (not soft_attr or not isinstance(soft_attr[0], tuple)):
            for cl, w in zip(soft_attr, wghts):
                cl = _check_clause(cl)
                w = _check_weight(int(w))
                if len(cl) == 1:
                    self._soft_unit_by_lit[cl[0]] = w
                    self._max_var = max(self._max_var, abs(cl[0]))
                else:
                    self._soft_nonunit.append((cl, w))
                    self._bump_max_var_from_clause(cl)
        else:
            for item in soft_attr:
                if isinstance(item, tuple) and len(item) >= 2:
                    cl = _check_clause(item[0])
                    w = _check_weight(int(item[1]))
                else:
                    cl = _check_clause(item)
                    w = 1
                if len(cl) == 1:
                    self._soft_unit_by_lit[cl[0]] = w
                    self._max_var = max(self._max_var, abs(cl[0]))
                else:
                    self._soft_nonunit.append((cl, w))
                    self._bump_max_var_from_clause(cl)
