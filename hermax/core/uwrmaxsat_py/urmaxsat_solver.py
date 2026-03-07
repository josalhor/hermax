import sys
import os
from pysat.formula import WCNF
from typing import List, Optional, Callable
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula
import hermax.core.urmaxsat_py as _urmaxsat


class UWrMaxSATSolver(IPAMIRSolver):
    """
    UWrMaxSAT: an efficient MaxSAT solver based on the UWrMaxSAT 1.8 solver.
    This solver provides native incremental support through the IPAMIR interface.

    UWrMaxSAT is known for its efficiency in handling various MaxSAT instances, 
    combining modern SAT solving techniques with effective MaxSAT algorithms.
    """
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self.solver = _urmaxsat.UWrMaxSAT()
        self._model: Optional[List[int]] = None
        self._status: SolveStatus = SolveStatus.UNKNOWN
        self._last_solve_result: Optional[int] = None
        self.num_vars = 0
        # Track softs so we can compute cost from the exposed model
        self._anon_soft_by_lit: dict[int, int] = {}   # literal -> weight (last-wins)
        self._id_soft_b_weight: dict[int, int] = {}   # relax var b -> weight (for id-based softs)
        self._soft_ids: dict[str, int] = {}           # id -> relax var b

        # Preload clauses if formula is provided
        if formula is not None:
            # Track the maximum variable id first to provision new_var
            max_var = 0
            all_cls = list(getattr(formula, "hard", []))
            soft_attr = getattr(formula, "soft", [])
            for item in soft_attr:
                # PySAT WCNF uses list-of-clauses + wght, but other sources may provide (clause, weight)
                if isinstance(item, tuple) and len(item) >= 2:
                    cl = item[0]
                else:
                    cl = item
                if isinstance(cl, list):
                    all_cls.append(cl)
            for cl in all_cls:
                for lit in cl:
                    if lit == 0:
                        raise ValueError("CNF contains literal 0.")
                    max_var = max(max_var, abs(lit))
            while self.num_vars < max_var:
                self.new_var()

            # Load hards
            for clause in getattr(formula, "hard", []):
                self.add_clause(clause)

            # Load softs
            softs = getattr(formula, "soft", [])
            wghts = getattr(formula, "wght", None)
            if wghts is not None and len(wghts) == len(softs) and (not softs or not isinstance(softs[0], tuple)):
                # PySAT style: softs is list of clauses, weights in wght
                for cl, w in zip(softs, wghts):
                    if not cl or int(w) <= 0:
                        raise ValueError("Invalid soft in WCNF.")
                    if len(cl) == 1:
                        self.add_soft_unit(int(cl[0]), int(w))
                    else:
                        b = self.new_var()
                        self.add_soft_relaxed([int(x) for x in cl], int(w), relax_var=b)
            else:
                # Tuple/list pairs
                for item in softs:
                    if isinstance(item, tuple) and len(item) >= 2:
                        cl, w = item[0], int(item[1])
                    else:
                        cl, w = item, 1
                    if not isinstance(cl, list) or not cl or w <= 0:
                        raise ValueError("Invalid soft in WCNF.")
                    if len(cl) == 1:
                        self.add_soft_unit(int(cl[0]), int(w))
                    else:
                        b = self.new_var()
                        self.add_soft_relaxed([int(x) for x in cl], int(w), relax_var=b)

    
    def add_clause(self, clause: List[int]) -> None:
        # Back-compat signature; allow empty hard [].
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        for lit in clause:
            if lit == 0:
                raise ValueError("Clause literals cannot be 0.")
            v = abs(lit)
            while v > self.num_vars:
                self.new_var()

        # hard; [] allowed (forces UNSAT)
        self.solver.addClause(clause, None)


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

        if weight == 0:
            self._anon_soft_by_lit.pop(int(lit), None)
            return

        # Anonymous soft literal, last-wins by literal
        self.solver.addClause([int(lit)], int(weight))
        self._anon_soft_by_lit[int(lit)] = int(weight)

    def add_soft_unit(self, lit: int, weight: int) -> None:
        if not isinstance(weight, int) or int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        self.set_soft(lit, weight)

    # ---------- Solve ----------

    def solve(self, assumptions=None, raise_on_abnormal=False) -> bool:
        assumps = list(assumptions) if assumptions else []
        if assumps:
            self.solver.assume(assumps)

        r = self.solver.solve()
        self._last_solve_result = r

        if r == 30:
            self._status = SolveStatus.OPTIMUM

            model = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)
                if v is True:
                    model.append(i)
                elif v is False:
                    model.append(-i)
                else:
                    # check if assumptions
                    if i in assumps:
                        model.append(i)
                    elif -i in assumps:
                        model.append(-i)
                    else:
                        model.append(-i)

            # Force assumptions in exposed model; some backends may return
            # partial/relaxed values even when assumptions were used for solve.
            for a in assumps:
                vi = abs(a)
                if 1 <= vi <= self.num_vars:
                    model[vi - 1] = vi if a > 0 else -vi

            self._model = model
            # Compute objective from exposed model + Python soft map.
            # Some backend versions return cost values that do not account for
            # assumption-forced violations of unit soft clauses.
            self._last_cost = self._compute_cost_from_model(model)
            return True
        elif self._last_solve_result == 20:
            self._status = SolveStatus.UNSAT
            self._model = None
            self._last_cost = None
        elif self._last_solve_result == 10:
            self._status = SolveStatus.INTERRUPTED_SAT
            self._model = None
            self._last_cost = None
        elif self._last_solve_result == 0:
            self._status = SolveStatus.INTERRUPTED
            self._model = None
            self._last_cost = None
        else:
            self._status = SolveStatus.ERROR
            self._model = None
            self._last_cost = None

        if raise_on_abnormal and self._status in {SolveStatus.INTERRUPTED, SolveStatus.UNKNOWN, SolveStatus.ERROR}:
            raise RuntimeError(f"Solver terminated with abnormal status: {self._status.name}")

        return is_feasible(self._status)


    # ---------- Accessors ----------

    def get_cost(self) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("Cost is only available for SAT or OPTIMUM status.")
        return int(self._last_cost)  # or int(self.solver.getCost()) if you prefer

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
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        v = abs(lit)
        if self._model is None or v > self.num_vars:
            raise ValueError("Invalid literal for val().")
        m = self._model[v - 1]  # signed assignment for var v
        if lit > 0:
            return 1 if m == v else -1
        else:
            return 1 if m == -v else -1


    # Optional helpers

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars

    def set_terminate(self, callback: Optional[Callable[[], int]]) -> None:
        self.solver.set_terminate(callback)
