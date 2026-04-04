import sys
import os
from typing import List, Optional, Dict, Tuple
from pysat.formula import WCNF
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula
import hermax.core.evalmaxsat_latest as evalmaxsat_latest


class EvalMaxSATLatestSolver(IPAMIRSolver):
    """
    Python wrapper for the latest EvalMaxSAT.
    
    Design:
      - Hard clauses and unit softs are cached in Python.
      - On solve(), we instantiate a fresh backend and replay the problem.
    """
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self._backend_ctor = evalmaxsat_latest.EvalMaxSAT
        self.solver = self._backend_ctor()

        self._model: Optional[List[int]] = None
        self._status: SolveStatus = SolveStatus.UNKNOWN
        self._last_cost: Optional[int] = None

        # Problem state cached in Python
        self._hard_clauses: List[List[int]] = []
        self._soft_by_lit: Dict[int, int] = {}          # unit softs (literal -> weight), last-wins
        self.num_vars = 0

        if formula is not None:
            # Pre-size variable space
            max_var = 0
            all_hard = getattr(formula, "hard", [])
            soft_attr = getattr(formula, "soft", [])
            if soft_attr and isinstance(soft_attr[0], tuple):
                all_soft_cls = [c for c, _w in soft_attr]
            else:
                all_soft_cls = soft_attr
            
            for cl in all_hard + all_soft_cls:
                for lit in cl:
                    max_var = max(max_var, abs(lit))
            while self.num_vars < max_var:
                self.new_var()

            # Load hard clauses
            for clause in all_hard:
                self.add_clause(list(map(int, clause)))

            # Load softs
            wghts = getattr(formula, "wght", None)
            if wghts is not None and len(wghts) == len(all_soft_cls) and (not all_soft_cls or not isinstance(all_soft_cls[0], tuple)):
                for cl, w in zip(all_soft_cls, wghts):
                    self.add_clause(list(map(int, cl)), int(w))
            else:
                for item in soft_attr:
                    if isinstance(item, tuple) and len(item) >= 2:
                        cl, w = list(map(int, item[0])), int(item[1])
                    else:
                        cl, w = list(map(int, item)), 1
                    self.add_clause(cl, w)

    def add_clause(self, clause: List[int], weight: Optional[int] = None) -> None:
        for lit in clause:
            if lit == 0:
                raise ValueError("Clause literals cannot be 0.")
            v = abs(lit)
            while v > self.num_vars:
                self.new_var()

        if weight is None:
            self._hard_clauses.append(list(map(int, clause)))
            return

        if not isinstance(weight, int) or weight != int(weight):
            raise ValueError("Weight must be an integer.")
        if weight <= 0:
            raise ValueError("Weight must be a positive integer.")
        if len(clause) == 0:
            raise ValueError("Empty soft clause is not allowed.")
        
        if len(clause) == 1:
            self.add_soft_unit(int(clause[0]), int(weight))
        else:
            b = self.new_var()
            self.add_soft_relaxed(list(map(int, clause)), int(weight), relax_var=b)

    def set_soft(self, lit: int, weight: int) -> None:
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        if not isinstance(weight, int) or weight != int(weight):
            raise ValueError("Weight must be an integer.")
        if weight < 0:
            raise ValueError("Weight must be a non-negative integer.")
        v = abs(lit)
        while v > self.num_vars:
            self.new_var()
        if int(weight) == 0:
            self._soft_by_lit.pop(int(lit), None)
            return
        self._soft_by_lit[int(lit)] = int(weight)

    def add_soft_unit(self, lit: int, weight: int) -> None:
        if not isinstance(weight, int) or int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        self.set_soft(lit, weight)

    def _rebuild_backend(self) -> None:
        self.solver = self._backend_ctor()
        # Pre-size variables
        for _ in range(self.num_vars):
            self.solver.newVar()
        
        self.solver.setNInputVars(self.num_vars)

        # Hard clauses
        for cl in self._hard_clauses:
            self.solver.addClause(cl, None)
        # Unit softs
        for lit, w in self._soft_by_lit.items():
            self.solver.addClause([lit], w)

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False
    ) -> bool:
        self._rebuild_backend()
        if assumptions:
            for lit in assumptions:
                if not isinstance(lit, int) or lit == 0:
                    raise ValueError("Assumptions must be non-zero integers.")
                # Rebuild-on-solve wrapper: emulate assumptions via temporary hard units.
                self.solver.addClause([int(lit)], None)
        
        res = self.solver.solve()

        if res:
            self._status = SolveStatus.OPTIMUM
            # Keep only the model over declared input vars; backend may allocate auxiliaries.
            model = []
            for i in range(1, self.num_vars + 1):
                model.append(i if self.solver.getValue(i) else -i)
            self._model = model
            self._last_cost = self.solver.getCost()
        else:
            self._status = SolveStatus.UNSAT
            self._model = None
            self._last_cost = None

        if raise_on_abnormal and self._status in {SolveStatus.INTERRUPTED, SolveStatus.UNKNOWN, SolveStatus.ERROR}:
            raise RuntimeError(f"Solver terminated with abnormal status: {self._status.name}")

        return is_feasible(self._status)

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("Cost is only available for SAT or OPTIMUM status.")
        return int(self._last_cost)

    def val(self, lit: int) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("val() is only available for SAT or OPTIMUM status.")
        v = abs(lit)
        if self._model is None or v > self.num_vars:
            raise ValueError("Invalid literal for val().")
        
        # model is 1-indexed in our getModel implementation
        # model[v-1] contains signed literal
        m = self._model[v - 1]
        if lit > 0:
            return 1 if m == v else -1
        else:
            return 1 if m == -v else -1

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._status):
            raise RuntimeError("Model is only available for SAT or OPTIMUM status.")
        return self._model

    def signature(self) -> str:
        return "EvalMaxSAT (Latest)"

    def close(self) -> None:
        self.solver = None

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars
