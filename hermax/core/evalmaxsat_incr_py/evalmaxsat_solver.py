import sys
import os
from typing import List, Optional
from pysat.formula import WCNF
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula
import hermax.core.evalmaxsat_incr as evalmaxsat_incr

class EvalMaxSATIncrSolver(IPAMIRSolver):
    """
    Incr EvalMaxSAT: An incremental version of EvalMaxSAT.
    Although this solver implements the IPAMIR interface, it is often 
    categorized with non-native incremental solvers due to its internal 
    handling of incremental queries.

    It provides a balance between the modern techniques of EvalMaxSAT and 
    the flexibility of incremental solving.
    """
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self._backend_ctor = evalmaxsat_incr.EvalMaxSATIncr
        self.solver = self._backend_ctor()
        self._model: Optional[List[int]] = None
        self.num_vars = 0
        self._status = SolveStatus.UNKNOWN
        self._last_cost: Optional[int] = None
        self._hard_clauses: List[List[int]] = []
        self._soft_by_lit: dict[int, int] = {}  # last-wins by literal

        if formula is not None:
            max_var = 0
            all_cls = list(getattr(formula, "hard", []))
            soft_attr = getattr(formula, "soft", [])
            for item in soft_attr:
                if isinstance(item, tuple) and len(item) >= 2:
                    cl = item[0]
                else:
                    cl = item
                if isinstance(cl, list):
                    all_cls.append(cl)
            for cl in all_cls:
                for lit in cl:
                    max_var = max(max_var, abs(lit))
            
            while self.num_vars < max_var:
                self.new_var()

            for clause in getattr(formula, "hard", []):
                self.add_clause(clause)

            softs = getattr(formula, "soft", [])
            wghts = getattr(formula, "wght", None)
            if wghts is not None and len(wghts) == len(softs) and (not softs or not isinstance(softs[0], tuple)):
                for cl, w in zip(softs, wghts):
                    if len(cl) == 1:
                        self.add_soft_unit(int(cl[0]), int(w))
                    else:
                        b = self.new_var()
                        self.add_soft_relaxed([int(x) for x in cl], int(w), relax_var=b)
            else:
                for item in softs:
                    if isinstance(item, tuple) and len(item) >= 2:
                        cl, w = item[0], int(item[1])
                    else:
                        cl, w = item, 1
                    if len(cl) == 1:
                        self.add_soft_unit(int(cl[0]), int(w))
                    else:
                        b = self.new_var()
                        self.add_soft_relaxed([int(x) for x in cl], int(w), relax_var=b)

    def add_clause(self, clause: List[int]) -> None:
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        for lit in clause:
            if lit == 0:
                raise ValueError("Clause literals cannot be 0.")
            var = abs(lit)
            while var > self.num_vars:
                self.new_var()
        self._hard_clauses.append(list(map(int, clause)))

    def set_soft(self, lit: int, weight: int) -> None:
        if not isinstance(lit, int) or lit == 0:
            raise ValueError("Literal must be a non-zero integer.")
        if not isinstance(weight, int) or weight != int(weight):
            raise ValueError("Weight must be an integer.")
        if weight < 0:
            raise ValueError("Weight must be a non-negative integer.")
        var = abs(lit)
        while var > self.num_vars:
            self.new_var()
        if int(weight) == 0:
            self._soft_by_lit.pop(int(lit), None)
            return
        self._soft_by_lit[int(lit)] = int(weight)

    def add_soft_unit(self, lit: int, weight: int) -> None:
        if not isinstance(weight, int) or int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        self.set_soft(int(lit), int(weight))

    def _rebuild_backend(self) -> None:
        self.solver = self._backend_ctor()
        for cl in self._hard_clauses:
            self.solver.addClause(cl, None)
        # IPAMIR add_soft_lit(L, W): assigning L=True incurs cost W
        # set_soft(lit, weight): penalize lit being False -> add_soft_lit(-lit, weight)
        for lit, w in self._soft_by_lit.items():
            self.solver.addSoftLit(-int(lit), int(w))

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
            self.solver.assume([int(x) for x in assumptions])

        code = self.solver.solve()

        if code == 30:
            self._status = SolveStatus.OPTIMUM
        elif code == 20:
            self._status = SolveStatus.UNSAT
        elif code == 10:
            self._status = SolveStatus.INTERRUPTED_SAT
        elif code == 0:
            self._status = SolveStatus.INTERRUPTED
        else:
            self._status = SolveStatus.ERROR

        if is_feasible(self._status):
            self._model = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                if v is True:
                    self._model.append(i)
                else:
                    self._model.append(-i)
            self._last_cost = int(self.solver.getCost())
        else:
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
        if self._model is None:
            raise RuntimeError("Model is not available.")
        var = abs(lit)
        if var == 0 or var > self.num_vars:
            raise ValueError("Invalid literal for val().")
        m = self._model[var - 1]
        if lit > 0:
            return 1 if m == var else -1
        else:
            return 1 if m == -var else -1

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._status):
            raise RuntimeError("Model is only available for SAT or OPTIMUM status.")
        return self._model

    def signature(self) -> str:
        return self.solver.signature()

    def close(self) -> None:
        self.solver = None

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars
