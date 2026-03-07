import sys
import os
from typing import List, Optional, Callable, Dict, Tuple
from pysat.formula import WCNF
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula
import hermax.core.cashwmaxsat as cashwmaxsat


class CASHWMaxSATSolver(IPAMIRSolver):
    """
    CASHWMaxSAT: A hybrid MaxSAT solver that combines UWrMaxSat with SCIP.
    This solver is NOT natively incremental; it mimics the IPAMIR interface 
    by rebuilding a fresh solver instance and replaying the problem for each solve call.

    CASHWMaxSAT is particularly effective for problems where SAT-based MaxSAT 
    approaches can be complemented by MILP (Mixed Integer Linear Programming) 
    techniques provided by SCIP.
    """
    def __init__(self, formula: Optional[WCNF] = None, disable_scip: bool = True, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self._backend_ctor = cashwmaxsat.CASHWMaxSAT
        self.solver = self._backend_ctor()

        self._model: Optional[List[int]] = None
        self._status: SolveStatus = SolveStatus.UNKNOWN
        self._last_cost: Optional[int] = None

        # Problem state cached in Python
        self._hard_clauses: List[List[int]] = []
        self._soft_by_lit: Dict[int, int] = {}          # unit softs (literal -> weight), last-wins
        self.num_vars = 0
        self._scip_disabled = disable_scip
        self._terminate_callback: Optional[Callable[[], int]] = None

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

        if not isinstance(weight, int):
            raise TypeError("Weight must be an integer.")
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
        if not isinstance(weight, int):
            raise TypeError("Weight must be an integer.")
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

    def disable_scip(self) -> None:
        """Disables the integrated SCIP solver."""
        self._scip_disabled = True

    def _rebuild_backend(self) -> None:
        self.solver = self._backend_ctor()
        if self._scip_disabled:
            self.solver.setNoScip()
        if self._terminate_callback is not None:
            self.solver.set_terminate(self._terminate_callback)
        # Pre-size variables
        for _ in range(self.num_vars):
            self.solver.newVar()
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
        if assumptions:
            # Although the backend supports assumptions, we are following 
            # the non-incremental pattern as requested.
            # Rebuilding the backend makes assumptions less useful but they can still be passed.
            pass

        # Preserve testability: if the backend has been replaced externally
        # (e.g., with a mock), do not rebuild over it.
        if isinstance(self.solver, self._backend_ctor):
            self._rebuild_backend()
        
        if assumptions:
            self.solver.assume(list(map(int, assumptions)))

        res = self.solver.solve()

        if res == 30: # OPTIMUM
            self._status = SolveStatus.OPTIMUM
        elif res == 10: # SAT
            self._status = SolveStatus.INTERRUPTED_SAT
        elif res == 20: # UNSAT
            self._status = SolveStatus.UNSAT
        elif res == 0: # INTERRUPTED
            self._status = SolveStatus.INTERRUPTED
        else:
            self._status = SolveStatus.ERROR

        if is_feasible(self._status):
            model: List[int] = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                if v is True:
                    model.append(i)
                elif v is False:
                    model.append(-i)
                else:
                    model.append(i) # Default to true for don't cares
            self._model = model
            self._last_cost = self.solver.getCost()
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
        if not is_feasible(self._status):
            raise RuntimeError("val() is only available for SAT or OPTIMUM status.")
        v = abs(lit)
        if self._model is None or v > self.num_vars:
            raise ValueError("Invalid literal for val().")
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
        return self.solver.signature()

    def close(self) -> None:
        self.solver = None

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars

    def set_terminate(self, callback: Optional[Callable[[], int]]) -> None:
        self._terminate_callback = callback
        if getattr(self, "solver", None) is not None and hasattr(self.solver, "set_terminate"):
            self.solver.set_terminate(callback)
