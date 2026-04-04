from __future__ import annotations

import os
from typing import List, Optional, Callable, Dict, Tuple, Iterable, Set

from pysat.formula import WCNF
from hermax.core.ipamir_solver_interface import IPAMIRSolver, is_feasible, SolveStatus
from hermax.core.utils import normalize_wcnf_formula
import hermax.core.urmaxsat_comp_py as _urmaxsat

class UWrMaxSATCompReentrant(IPAMIRSolver):
    """
    UWrMaxSAT: A re-encoding wrapper around the competition version of UWrMaxSAT.
    This solver is NOT natively incremental; it mimics the IPAMIR interface 
    by rebuilding a fresh solver instance and replaying the problem for each solve call.

    This is useful for environments where native incrementality is not required 
    or as a baseline for comparison with truly incremental solvers.
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
        self._last_cost: Optional[int] = None

        if formula is not None:
            self._load_initial_formula(formula)

    # -------------- IPAMIR-like API --------------

    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        cl = list(clause)
        self._hard_clauses.append(cl)
        for l in cl:
            self._max_var = max(self._max_var, abs(l))
        self._invalidate_last_solution()

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        self._soft_unit_by_lit[int(lit)] = int(weight)
        self._max_var = max(self._max_var, abs(int(lit)))
        self._invalidate_last_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(lit, weight)

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._require_open()
        self._invalidate_last_solution()

        # Instantiate fresh backend
        solver = _urmaxsat.UWrMaxSAT()
        
        # Determine max var needed
        current_max = self._max_var
        if assumptions:
            for a in assumptions:
                current_max = max(current_max, abs(a))
        
        # Pre-size variables (if needed by backend, though UWr usually handles it)
        # Assuming backend behaves like other IPAMIR wrappers here
        for _ in range(current_max):
            solver.newVar()

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
            r = solver.solve()
            if r == 30: # OPTIMUM
                self._last_status = SolveStatus.OPTIMUM
                model = []
                for i in range(1, current_max + 1):
                    v = solver.getValue(i)
                    if v is True:
                        model.append(i)
                    elif v is False:
                        model.append(-i)
                    else:
                        model.append(-i)
                self._last_model = model
                self._last_cost = int(solver.getCost())
                return True
            elif r == 20: # UNSAT
                self._last_status = SolveStatus.UNSAT
                self._last_model = None
                self._last_cost = None
                return False
            else:
                self._last_status = SolveStatus.ERROR
                self._last_model = None
                self._last_cost = None
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
        v = abs(lit)
        if self._last_model is None or v > len(self._last_model):
             return 0
        m = self._last_model[v - 1]
        if lit > 0:
            return 1 if m == v else -1
        else:
            return 1 if m == -v else -1

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._last_status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        return list(self._last_model)

    def signature(self) -> str:
        return "urmaxsat-comp-reentrant-ipamir"

    def close(self) -> None:
        self._closed = True
        self._hard_clauses.clear()
        self._soft_unit_by_lit.clear()
        self._soft_nonunit.clear()
        self._last_model = None
        self._last_cost = None
        self._last_status = SolveStatus.UNKNOWN

    def new_var(self) -> int:
        self._require_open()
        self._max_var += 1
        return self._max_var

    # -------------- Internal helpers --------------

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Solver is closed")

    def _invalidate_last_solution(self) -> None:
        self._last_status = SolveStatus.UNKNOWN
        self._last_model = None
        self._last_cost = None

    def _load_initial_formula(self, formula: WCNF) -> None:
        self._hard_clauses = []
        self._soft_unit_by_lit = {}
        self._soft_nonunit = []
        for cl in getattr(formula, "hard", []):
            self.add_clause(cl)
        
        soft_attr = getattr(formula, "soft", [])
        wghts = getattr(formula, "wght", None)
        if wghts is not None and len(wghts) == len(soft_attr) and (not soft_attr or not isinstance(soft_attr[0], tuple)):
            for cl, w in zip(soft_attr, wghts):
                if len(cl) == 1:
                    self.add_soft_unit(cl[0], w)
                else:
                    self._soft_nonunit.append((list(cl), int(w)))
                    for l in cl: self._max_var = max(self._max_var, abs(l))
        else:
            for item in soft_attr:
                if isinstance(item, tuple) and len(item) >= 2:
                    cl, w = item[0], int(item[1])
                else:
                    cl, w = item, 1
                if len(cl) == 1:
                    self.add_soft_unit(cl[0], w)
                else:
                    self._soft_nonunit.append((list(cl), int(w)))
                    for l in cl: self._max_var = max(self._max_var, abs(l))
