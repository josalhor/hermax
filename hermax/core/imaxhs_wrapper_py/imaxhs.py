from __future__ import annotations

import importlib
import importlib.util
import os
from typing import Callable, List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula

_MAX_I64 = (1 << 63) - 1


def _import_backend():
    if os.environ.get("FORCE_IMAXHS_NOT_COMPILED", "").strip() == "1":
        raise ImportError("FORCE_IMAXHS_NOT_COMPILED=1")
    return importlib.import_module("hermax.core.imaxhs_py")


class IMaxHSSolver(IPAMIRSolver):
    @classmethod
    def is_available(cls) -> bool:
        if os.environ.get("FORCE_IMAXHS_NOT_COMPILED", "").strip() == "1":
            return False
        spec = importlib.util.find_spec("hermax.core.imaxhs_py")
        return spec is not None

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        if not self.is_available():
            raise RuntimeError(
                "IMaxHS native module is not available in this build "
                "(likely built without CPLEX)."
            )
        backend = _import_backend()
        self.solver = backend.IMaxHS()

        self._model: Optional[List[int]] = None
        self._status: SolveStatus = SolveStatus.UNKNOWN
        self._last_solve_result: Optional[int] = None
        self.num_vars = 0
        self._last_cost: Optional[int] = None
        self._anon_soft_by_lit: dict[int, int] = {}
        self._terminate_cb: Optional[Callable[[], int]] = None

        if formula is not None:
            self._load_initial_formula(formula)

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
                if lit == 0:
                    raise ValueError("CNF contains literal 0.")
                max_var = max(max_var, abs(int(lit)))
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
            weight = int(w)
            if weight <= 0:
                raise ValueError("Invalid soft in WCNF.")
            if len(cl) == 1:
                self.add_soft_unit(int(cl[0]), weight)
            else:
                b = self.new_var()
                self.add_soft_relaxed([int(x) for x in cl], weight, relax_var=b)

    def add_clause(self, clause: List[int]) -> None:
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        for lit in clause:
            if int(lit) == 0:
                raise ValueError("Clause literals cannot be 0.")
            v = abs(int(lit))
            while v > self.num_vars:
                self.new_var()
        self.solver.addClause([int(x) for x in clause], None)

    def set_soft(self, lit: int, weight: int) -> None:
        lit = int(lit)
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        if not isinstance(weight, int):
            raise ValueError("Weight must be an integer.")
        if weight < 0:
            raise ValueError("Weight must be a non-negative integer.")
        if int(weight) > _MAX_I64:
            raise OverflowError(f"Weight exceeds int64 max: {weight}")
        v = abs(lit)
        while v > self.num_vars:
            self.new_var()
        if weight == 0:
            self._anon_soft_by_lit.pop(lit, None)
            return

        self.solver.addClause([lit], int(weight))
        self._anon_soft_by_lit[lit] = int(weight)

    def add_soft_unit(self, lit: int, weight: int) -> None:
        if int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        self.set_soft(int(lit), int(weight))

    def solve(self, assumptions=None, raise_on_abnormal=False) -> bool:
        if self._terminate_cb is not None and int(self._terminate_cb()) != 0:
            self._status = SolveStatus.INTERRUPTED
            self._model = None
            self._last_cost = None
            self._last_solve_result = int(SolveStatus.INTERRUPTED)
            if raise_on_abnormal:
                raise RuntimeError(
                    f"Solver terminated with abnormal status: {self._status.name}"
                )
            return False

        assumps = list(assumptions) if assumptions else []
        if assumps:
            for lit in assumps:
                if int(lit) == 0:
                    raise ValueError("Assumptions must be non-zero integers.")
                while abs(int(lit)) > self.num_vars:
                    self.new_var()
            self.solver.assume([int(x) for x in assumps])

        r = int(self.solver.solve())
        self._last_solve_result = r

        if r == int(SolveStatus.OPTIMUM):
            self._status = SolveStatus.OPTIMUM
            model: list[int] = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                if v is True:
                    model.append(i)
                elif v is False:
                    model.append(-i)
                elif i in assumps:
                    model.append(i)
                elif -i in assumps:
                    model.append(-i)
                else:
                    model.append(-i)
            for a in assumps:
                vi = abs(int(a))
                if 1 <= vi <= self.num_vars:
                    model[vi - 1] = vi if a > 0 else -vi
            self._model = model
            self._last_cost = self._compute_cost_from_model(model)
            return True

        if r == int(SolveStatus.INTERRUPTED_SAT):
            self._status = SolveStatus.INTERRUPTED_SAT
            model = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                if v is True:
                    model.append(i)
                elif v is False:
                    model.append(-i)
                elif i in assumps:
                    model.append(i)
                elif -i in assumps:
                    model.append(-i)
                else:
                    model.append(-i)
            self._model = model
            self._last_cost = self._compute_cost_from_model(model)
            return True

        if r == int(SolveStatus.UNSAT):
            self._status = SolveStatus.UNSAT
        elif r == int(SolveStatus.INTERRUPTED):
            self._status = SolveStatus.INTERRUPTED
        else:
            self._status = SolveStatus.ERROR
        self._model = None
        self._last_cost = None

        if raise_on_abnormal and self._status in {SolveStatus.INTERRUPTED, SolveStatus.UNKNOWN, SolveStatus.ERROR}:
            raise RuntimeError(f"Solver terminated with abnormal status: {self._status.name}")
        return is_feasible(self._status)

    def _compute_cost_from_model(self, model: List[int]) -> int:
        assign_true = {lit for lit in model if lit > 0}
        cost = 0
        for lit, w in self._anon_soft_by_lit.items():
            v = abs(lit)
            is_true = v in assign_true
            sat = is_true if lit > 0 else (not is_true)
            if not sat:
                cost += int(w)
        return int(cost)

    def get_cost(self) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("Cost is only available for SAT or OPTIMUM status.")
        return int(self._last_cost)

    def signature(self) -> str:
        return str(self.solver.signature())

    def close(self) -> None:
        if getattr(self, "solver", None) is not None:
            s = self.solver
            self.solver = None
            del s

    def get_status(self) -> SolveStatus:
        return self._status

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._status):
            raise RuntimeError("Model is only available for SAT or OPTIMUM status.")
        return self._model

    def val(self, lit: int) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("val() is only available for SAT or OPTIMUM status.")
        lit = int(lit)
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        v = abs(lit)
        if self._model is None or v > self.num_vars:
            raise ValueError("Invalid literal for val().")
        m = self._model[v - 1]
        if lit > 0:
            return 1 if m == v else -1
        return 1 if m == -v else -1

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars

    def set_terminate(self, callback: Optional[Callable[[], int]]) -> None:
        self._terminate_cb = callback
        self.solver.set_terminate(callback)
