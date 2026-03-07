from __future__ import annotations

import importlib
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula


class LoandraSolver(IPAMIRSolver):
    @classmethod
    def is_available(cls) -> bool:
        try:
            mod = importlib.import_module("hermax.core.loandra")
            return hasattr(mod, "Loandra")
        except Exception:
            return False

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        try:
            native = importlib.import_module("hermax.core.loandra")
            self.solver = native.Loandra()
        except Exception as exc:
            raise RuntimeError("Loandra native module is not available in this build.") from exc
        self._model: Optional[List[int]] = None
        self.num_vars = 0

        if formula is not None:
            max_var = 0
            soft_attr = getattr(formula, "soft", [])
            soft_pairs = []
            wghts = getattr(formula, "wght", None)
            if wghts is not None and len(wghts) == len(soft_attr) and (
                not soft_attr or not isinstance(soft_attr[0], tuple)
            ):
                soft_pairs = list(zip(soft_attr, wghts))
            else:
                for item in soft_attr:
                    if isinstance(item, tuple) and len(item) >= 2:
                        soft_pairs.append((item[0], item[1]))
                    else:
                        soft_pairs.append((item, 1))
            all_clauses = list(getattr(formula, "hard", [])) + [c for c, _w in soft_pairs]
            for cl in all_clauses:
                for lit in cl:
                    max_var = max(max_var, abs(int(lit)))
            while self.num_vars < max_var:
                self.new_var()
            for clause in getattr(formula, "hard", []):
                self.add_clause(list(map(int, clause)))
            for clause, weight in soft_pairs:
                self.add_clause(list(map(int, clause)), int(weight))

    def add_clause(self, clause: List[int], weight: Optional[int] = None) -> None:
        if weight is not None and weight <= 0:
            raise ValueError("Weight must be a positive integer.")
        for lit in clause:
            if int(lit) == 0:
                raise ValueError("Clause literals cannot be 0.")
            var = abs(int(lit))
            while var > self.num_vars:
                self.new_var()
        self.solver.addClause([int(x) for x in clause], weight)

    def set_soft(self, lit: int, weight: int) -> None:
        if not isinstance(lit, int) or lit == 0:
            raise ValueError("Soft literal must be a non-zero integer.")
        if not isinstance(weight, int) or weight <= 0:
            raise ValueError("Weight must be a positive integer.")
        self.add_clause([lit], weight)

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), int(weight))

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        if assumptions:
            raise NotImplementedError("Loandra native wrapper does not support assumptions.")
        solve_result = bool(self.solver.solve())
        if solve_result:
            self._status = SolveStatus.OPTIMUM
            self._model = [i if self.solver.getValue(i) else -i for i in range(1, self.num_vars + 1)]
        else:
            self._status = SolveStatus.UNSAT
            self._model = None

        if raise_on_abnormal and self._status in [SolveStatus.INTERRUPTED, SolveStatus.UNKNOWN, SolveStatus.ERROR]:
            raise RuntimeError(f"Solver terminated with abnormal status: {self._status.name}")
        return is_feasible(self._status)

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("Cost is only available for SAT or OPTIMUM status.")
        return int(self.solver.getCost())

    def val(self, lit: int) -> int:
        if self._model is None:
            raise RuntimeError("Model is not available.")
        var = abs(int(lit))
        if var == 0 or var > self.num_vars:
            raise ValueError("Invalid literal for val().")
        var_val_is_true = bool(self.solver.getValue(var))
        return 1 if ((lit > 0 and var_val_is_true) or (lit < 0 and not var_val_is_true)) else -1

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._status):
            raise RuntimeError("Model is only available for SAT or OPTIMUM status.")
        return self._model

    def signature(self) -> str:
        return "Loandra (OLL path)"

    def close(self) -> None:
        self.solver = None

    def new_var(self) -> int:
        self.num_vars = int(self.solver.newVar())
        return self.num_vars
