import sys
import os
from typing import List, Optional, Callable, Dict, Tuple
from pysat.formula import WCNF
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula
import hermax.core.openwbo as openwbo


class _OpenWBOSolverBase(IPAMIRSolver):
    """
    Base class for Open-WBO solvers to share common logic.

    Design:
      - Hard clauses and unit softs are cached in Python.
      - On solve(), we instantiate a fresh backend and replay:
          * newVar() up to num_vars
          * all cached hard clauses
          * all cached unit softs (deduped by literal, last-wins)
      - Non-unit softs are expressed as (C ∨ b) hard + unit soft [-b] via add_soft_relaxed,
        which the abstract base implements using add_clause + set_soft.
    """
    def __init__(self, formula: Optional[WCNF] = None, solver_backend=None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        if solver_backend is None:
            raise ValueError("solver_backend must be provided.")
        self._backend_ctor = solver_backend
        self.solver = self._backend_ctor()

        self._model: Optional[List[int]] = None
        self._status: SolveStatus = SolveStatus.UNKNOWN
        self._last_cost: Optional[int] = None

        # Problem state cached in Python
        self._hard_clauses: List[List[int]] = []        # include empty [] for UNSAT
        self._soft_by_lit: Dict[int, int] = {}          # unit softs (literal -> weight), last-wins
        self.num_vars = 0

        if formula is not None:
            # Pre-size variable space
            max_var = 0
            all_hard = getattr(formula, "hard", [])
            soft_attr = getattr(formula, "soft", [])
            # Account for PySAT WCNF variants
            if soft_attr and isinstance(soft_attr[0], tuple):
                all_soft_cls = [c for c, _w in soft_attr]
            else:
                all_soft_cls = soft_attr
            for cl in all_hard + all_soft_cls:
                for lit in cl:
                    if lit == 0:
                        raise ValueError("CNF contains literal 0.")
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
                    w = int(w)
                    if w <= 0 or not cl:
                        raise ValueError("Invalid soft in WCNF.")
                    cl = list(map(int, cl))
                    if len(cl) == 1:
                        self.add_soft_unit(cl[0], w)
                    else:
                        b = self.new_var()
                        self.add_soft_relaxed(cl, w, relax_var=b)
            else:
                # Tuple pairs (clause, weight)
                for item in soft_attr:
                    if isinstance(item, tuple) and len(item) >= 2:
                        cl, w = list(map(int, item[0])), int(item[1])
                    else:
                        cl, w = list(map(int, item)), 1
                    if w <= 0 or not cl:
                        raise ValueError("Invalid soft in WCNF.")
                    if len(cl) == 1:
                        self.add_soft_unit(cl[0], w)
                    else:
                        b = self.new_var()
                        self.add_soft_relaxed(cl, w, relax_var=b)

    # ---------------- API ----------------

    def add_clause(self, clause: List[int], weight: Optional[int] = None) -> None:
        # Back-compat signature. Hard-only if weight is None. Empty [] allowed.
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        for lit in clause:
            if lit == 0:
                raise ValueError("Clause literals cannot be 0.")
            v = abs(lit)
            while v > self.num_vars:
                self.new_var()

        if weight is None:
            # Record hard clause (empty allowed)
            self._hard_clauses.append(list(map(int, clause)))
            return

        # Soft branch (back-compat)
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
            # Delegate to base add_soft_relaxed (adds (cl ∨ b) hard, and unit soft [-b])
            self.add_soft_relaxed(list(map(int, clause)), int(weight), relax_var=b)

    def set_soft(self, lit: int, weight: int) -> None:
        # Last-wins cache by literal
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
        # Thin wrapper
        if not isinstance(weight, int) or int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        self.set_soft(lit, weight)

    # ---------------- Solve & helpers ----------------

    def _rebuild_backend(self) -> None:
        # Build a fresh Open-WBO backend and replay current state
        self.solver = self._backend_ctor()
        # Pre-size variables
        for _ in range(self.num_vars):
            self.solver.newVar()
        # Hard clauses
        for cl in self._hard_clauses:
            # [] allowed, signals UNSAT to the backend
            self.solver.addClause(list(cl), None)
        # Unit softs (deduped by literal)
        for lit, w in self._soft_by_lit.items():
            self.solver.addClause([int(lit)], int(w))

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False
    ) -> bool:
        # Rebuild a clean backend every solve to guarantee dedup semantics
        self._rebuild_backend()

        assumps = list(assumptions) if assumptions else []
        if assumps:
            for a in assumps:
                if a == 0:
                    raise ValueError("Assumptions cannot contain 0.")

        sat = self.solver.solve(assumps if assumps else None)

        if sat:
            self._status = SolveStatus.OPTIMUM
            # Build model
            model: List[int] = []
            for i in range(1, self.num_vars + 1):
                v = self.solver.getValue(i)  # bool
                model.append(i if v else -i)

            # Enforce assumptions in the exposed model
            for a in assumps:
                vi = abs(a)
                if 1 <= vi <= self.num_vars:
                    model[vi - 1] = vi if a > 0 else -vi

            self._model = model
            # Recompute cost from the exposed model to keep cost consistent with enforced assumptions
            self._last_cost = self._compute_cost_from_model(model)
        else:
            self._status = SolveStatus.UNSAT
            self._model = None
            self._last_cost = None

        if raise_on_abnormal and self._status in {SolveStatus.INTERRUPTED, SolveStatus.UNKNOWN, SolveStatus.ERROR}:
            raise RuntimeError(f"Solver terminated with abnormal status: {self._status.name}")

        return is_feasible(self._status)

    def _compute_cost_from_model(self, model: List[int]) -> int:
        def lit_true(l: int) -> bool:
            v = abs(l)
            m = model[v - 1]
            return (l > 0 and m == v) or (l < 0 and m == -v)

        cost = 0
        for l, w in self._soft_by_lit.items():
            if not lit_true(l):
                cost += int(w)
        return cost

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("Cost is only available for SAT or OPTIMUM status.")
        # Prefer recomputed cost to keep parity with enforced assumptions
        if self._last_cost is not None:
            return int(self._last_cost)
        # Fallback (should match anyway)
        return int(self.solver.getCost())

    def val(self, lit: int) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("val() is only available for SAT or OPTIMUM status.")
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
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

    def close(self) -> None:
        if getattr(self, "solver", None) is not None:
            s = self.solver
            self.solver = None
            del s

    def new_var(self) -> int:
        # External variable id space; backend is rebuilt on solve
        self.num_vars += 1
        return self.num_vars


class OLLSolver(_OpenWBOSolverBase):
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        super().__init__(formula, solver_backend=openwbo.OLL, *args, **kwargs)

    def signature(self) -> str:
        return "Open-WBO (OLL)"


class PartMSU3Solver(_OpenWBOSolverBase):
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        super().__init__(formula, solver_backend=openwbo.PartMSU3, *args, **kwargs)

    # Enforce weight == 1 for any soft (unit or relaxed), as the underlying algorithm expects.
    def set_soft(self, lit: int, weight: int) -> None:
        if int(weight) == 0:
            super().set_soft(lit, 0)
            return
        if weight != 1:
            raise ValueError("PartMSU3 only supports soft weight 1.")
        super().set_soft(lit, weight)

    def signature(self) -> str:
        return "Open-WBO (PartMSU3)"


class AutoOpenWBOSolver(_OpenWBOSolverBase):
    """Automatic Open-WBO solver that selects OLL, PartMSU3, or MSU3 as appropriate."""
    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        super().__init__(formula, solver_backend=openwbo.Auto, *args, **kwargs)

    def signature(self) -> str:
        return "Open-WBO (Auto)"
