from __future__ import annotations

import importlib
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import extract_wcnf_data, normalize_wcnf_formula


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
            data = extract_wcnf_data(formula)
            max_var = data.num_vars
            all_clauses = [*data.hard, *(c for c, _w in data.soft)]
            for cl in all_clauses:
                for lit in cl:
                    max_var = max(max_var, abs(int(lit)))
            while self.num_vars < max_var:
                self.new_var()
            for clause in data.hard:
                self.add_clause(list(map(int, clause)))
            for clause, weight in data.soft:
                self.add_clause(list(map(int, clause)), int(weight))

    def add_clause(self, clause: List[int], weight: Optional[int] = None) -> None:
        if not isinstance(clause, list):
            raise TypeError("Clause must be a list of integer literals.")
        if any(isinstance(lit, bool) or not isinstance(lit, int) or lit == 0 for lit in clause):
            raise ValueError("Clause literals must be non-zero integers.")
        if weight is not None and (isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0):
            raise ValueError("Weight must be a positive integer.")
        for lit in clause:
            var = abs(lit)
            while var > self.num_vars:
                self.new_var()
        self.solver.addClause(list(clause), weight)

    def set_soft(self, lit: int, weight: int) -> None:
        if isinstance(lit, bool) or not isinstance(lit, int) or lit == 0:
            raise ValueError("Soft literal must be a non-zero integer.")
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ValueError("Weight must be an integer.")
        if weight < 0:
            raise ValueError("Weight must be a non-negative integer.")
        if weight == 0:
            raise NotImplementedError(
                "set_soft(lit, 0) is not supported by this native incremental backend."
            )
        self.add_clause([lit], weight)

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(lit, weight)

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False,
        time_limit: Optional[float] = None,
    ) -> bool:
        self._reject_time_limit(time_limit)
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
        if isinstance(lit, bool) or not isinstance(lit, int):
            raise TypeError("Literal must be an integer.")
        var = abs(lit)
        if var == 0 or var > self.num_vars:
            raise ValueError("Invalid literal for val().")
        var_val_is_true = bool(self.solver.getValue(var))
        return 1 if ((lit > 0 and var_val_is_true) or (lit < 0 and not var_val_is_true)) else -1

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._status):
            raise RuntimeError("Model is only available for SAT or OPTIMUM status.")
        return list(self._model) if self._model is not None else None

    def signature(self) -> str:
        return "Loandra (OLL path)"

    def close(self) -> None:
        self.solver = None

    def new_var(self) -> int:
        self.num_vars = int(self.solver.newVar())
        return self.num_vars
