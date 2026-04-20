from __future__ import annotations

import importlib
import importlib.util
import os
from typing import Dict, List, Optional, Set, Tuple

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula

_MAX_I64 = (1 << 63) - 1


def _import_backend():
    if os.environ.get("FORCE_MAXHS_NOT_COMPILED", "").strip() == "1":
        raise ImportError("FORCE_MAXHS_NOT_COMPILED=1")
    return importlib.import_module("hermax.core.maxhs_py")


class MaxHSSolver(IPAMIRSolver):
    """
    Re-encoding wrapper around MaxHS:
      - Stores all clauses internally.
      - On solve(), rebuilds a fresh solver instance and replays the problem.
      - Assumptions are added as temporary hard unit clauses for that specific solve query.
    """

    @classmethod
    def is_available(cls) -> bool:
        if os.environ.get("FORCE_MAXHS_NOT_COMPILED", "").strip() == "1":
            return False
        spec = importlib.util.find_spec("hermax.core.maxhs_py")
        return spec is not None

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        if not self.is_available():
            raise RuntimeError(
                "MaxHS native module is not available in this build "
                "(likely built without CPLEX)."
            )
        backend = _import_backend()
        self._backend_ctor = backend.MaxHS

        self._closed: bool = False
        self._terminate_cb = None
        # Compatibility hook used by generic IPAMIR tests that monkeypatch an
        # underlying backend object.
        self.solver = None

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

    def add_clause(self, clause: List[int]) -> None:
        self._require_open()
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        cl = [int(x) for x in clause]
        for lit in cl:
            if lit == 0:
                raise ValueError("Clause literals cannot be 0.")
        self._hard_clauses.append(cl)
        for l in cl:
            self._max_var = max(self._max_var, abs(l))
        self._invalidate_last_solution()

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        lit = int(lit)
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        if not isinstance(weight, int):
            raise ValueError("Weight must be an integer.")
        if int(weight) < 0:
            raise ValueError("Weight must be a non-negative integer.")
        if int(weight) > _MAX_I64:
            raise OverflowError(f"Weight exceeds int64 max: {weight}")
        if int(weight) == 0:
            self._soft_unit_by_lit.pop(lit, None)
            self._invalidate_last_solution()
            return
        self._soft_unit_by_lit[lit] = int(weight)
        self._max_var = max(self._max_var, abs(lit))
        self._invalidate_last_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        if int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        self.set_soft(int(lit), int(weight))

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._require_open()
        self._invalidate_last_solution()

        if self._terminate_cb is not None and int(self._terminate_cb()) != 0:
            self._last_status = SolveStatus.INTERRUPTED
            raise RuntimeError("Solver terminated by callback")

        solver = self.solver if self.solver is not None else self._backend_ctor()

        current_max = self._max_var
        if assumptions:
            for a in assumptions:
                if int(a) == 0:
                    raise ValueError("Assumptions must be non-zero integers.")
                current_max = max(current_max, abs(int(a)))
        self._max_var = max(self._max_var, current_max)

        if hasattr(solver, "setNInputVars"):
            solver.setNInputVars(current_max)

        for cl in self._hard_clauses:
            solver.addClause(cl, None)

        if assumptions:
            for a in assumptions:
                solver.addClause([int(a)], None)

        # Normalize opposite-polarity unit softs on the same variable into
        # a single unit soft + constant offset in the objective. This keeps
        # the argmin model unchanged while avoiding backend instability on
        # contradictory unit-soft pairs.
        resolved_softs: Dict[int, int] = {}
        for lit, w in self._soft_unit_by_lit.items():
            opp = -lit
            if opp in resolved_softs:
                w_opp = resolved_softs[opp]
                if w > w_opp:
                    resolved_softs[lit] = w - w_opp
                    del resolved_softs[opp]
                elif w < w_opp:
                    resolved_softs[opp] = w_opp - w
                else:
                    del resolved_softs[opp]
            else:
                resolved_softs[lit] = w

        for lit, w in resolved_softs.items():
            solver.addClause([lit], w)

        for cl, w in self._soft_nonunit:
            solver.addClause(cl, w)

        res = solver.solve()
        raw_status: Optional[int] = None
        if hasattr(solver, "solve_status"):
            raw_status = int(solver.solve_status())
        elif isinstance(res, int) and res in {
            int(SolveStatus.INTERRUPTED),
            int(SolveStatus.INTERRUPTED_SAT),
            int(SolveStatus.UNSAT),
            int(SolveStatus.OPTIMUM),
            int(SolveStatus.ERROR),
        }:
            raw_status = int(res)

        is_optimum = raw_status == int(SolveStatus.OPTIMUM) or (raw_status is None and bool(res))
        if is_optimum:
            self._last_status = SolveStatus.OPTIMUM
            self._last_model = [int(x) for x in solver.getModel()] if hasattr(solver, "getModel") else []
            if len(self._last_model) < current_max:
                for i in range(len(self._last_model) + 1, current_max + 1):
                    self._last_model.append(-i)
            if assumptions:
                for a in assumptions:
                    v = abs(int(a))
                    if 1 <= v <= current_max:
                        self._last_model[v - 1] = v if int(a) > 0 else -v
            self._last_model_set = set(self._last_model)
            self._last_cost = self._compute_cost_from_model(self._last_model)
            return True

        if raw_status == int(SolveStatus.INTERRUPTED_SAT):
            self._last_status = SolveStatus.INTERRUPTED_SAT
            self._last_model = [int(x) for x in solver.getModel()] if hasattr(solver, "getModel") else []
            self._last_model_set = set(self._last_model)
            self._last_cost = self._compute_cost_from_model(self._last_model)
            return True

        if raw_status == int(SolveStatus.UNSAT):
            self._last_status = SolveStatus.UNSAT
            self._last_model = None
            self._last_cost = None
            self._last_model_set.clear()
            return False

        if raw_status == int(SolveStatus.INTERRUPTED):
            self._last_status = SolveStatus.INTERRUPTED
            self._last_model = None
            self._last_cost = None
            self._last_model_set.clear()
            if self._terminate_cb is not None or raise_on_abnormal:
                raise RuntimeError("Solver terminated by callback")
            return False

        if raw_status == int(SolveStatus.ERROR):
            self._last_status = SolveStatus.ERROR
            self._last_model = None
            self._last_cost = None
            self._last_model_set.clear()
            if raise_on_abnormal:
                raise RuntimeError("Solver terminated with abnormal status: ERROR")
            return False

        self._last_status = SolveStatus.UNKNOWN
        self._last_model = None
        self._last_cost = None
        self._last_model_set.clear()
        if raise_on_abnormal:
            raise RuntimeError("Solver terminated with abnormal status: UNKNOWN")
        return False

    def get_status(self) -> SolveStatus:
        return self._last_status

    def get_cost(self) -> int:
        self._require_open()
        if not is_feasible(self._last_status):
            raise RuntimeError("Objective not available; last status is not SAT/OPTIMUM")
        return int(self._last_cost)

    def val(self, lit: int) -> int:
        self._require_open()
        if not is_feasible(self._last_status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        lit = int(lit)
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        if abs(lit) > self._max_var:
            raise ValueError("Invalid literal for val().")
        v = abs(lit)
        if v in self._last_model_set and -v not in self._last_model_set:
            return 1 if lit > 0 else -1
        if -v in self._last_model_set and v not in self._last_model_set:
            return -1 if lit > 0 else 1
        return 0

    def get_model(self) -> Optional[List[int]]:
        self._require_open()
        if not is_feasible(self._last_status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        return list(self._last_model)

    def signature(self) -> str:
        return "maxhs-reentrant-ipamir"

    def set_terminate(self, callback) -> None:
        self._terminate_cb = callback
        if callback is not None:
            int(callback())

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

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Solver is closed")

    def _invalidate_last_solution(self) -> None:
        self._last_status = SolveStatus.UNKNOWN
        self._last_model = None
        self._last_model_set.clear()
        self._last_cost = None

    def _load_initial_formula(self, formula: WCNF) -> None:
        self._hard_clauses = []
        self._soft_unit_by_lit = {}
        self._soft_nonunit = []
        for cl in getattr(formula, "hard", []):
            self.add_clause([int(x) for x in cl])

        soft_attr = getattr(formula, "soft", [])
        wghts = getattr(formula, "wght", None)
        if wghts is not None and len(wghts) == len(soft_attr) and (not soft_attr or not isinstance(soft_attr[0], tuple)):
            for cl, w in zip(soft_attr, wghts):
                if len(cl) == 1:
                    self.add_soft_unit(int(cl[0]), int(w))
                else:
                    self._soft_nonunit.append((list(cl), int(w)))
                    for l in cl:
                        self._max_var = max(self._max_var, abs(l))
        else:
            for item in soft_attr:
                if isinstance(item, tuple) and len(item) >= 2:
                    cl, w = item[0], int(item[1])
                else:
                    cl, w = item, 1
                if len(cl) == 1:
                    self.add_soft_unit(int(cl[0]), int(w))
                else:
                    self._soft_nonunit.append((list(cl), int(w)))
                    for l in cl:
                        self._max_var = max(self._max_var, abs(l))

    def _compute_cost_from_model(self, model: List[int]) -> int:
        s = set(int(x) for x in model)
        total = 0
        for lit, w in self._soft_unit_by_lit.items():
            if int(lit) not in s:
                total += int(w)
        for cl, w in self._soft_nonunit:
            if not any(int(l) in s for l in cl):
                total += int(w)
        return int(total)
