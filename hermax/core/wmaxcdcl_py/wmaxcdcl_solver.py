from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import importlib

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula


class WMaxCDCLSolver(IPAMIRSolver):
    """
    WMaxCDCL fake-incremental wrapper (rebuild-on-solve).

    This wrapper caches hard clauses and unit soft literals in Python and creates
    a fresh WMaxCDCL backend instance on every `solve()` call.
    """

    @classmethod
    def is_available(cls) -> bool:
        try:
            mod = importlib.import_module("hermax.core.wmaxcdcl")
            return hasattr(mod, "WMaxCDCL")
        except Exception:
            return False

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        try:
            wmaxcdcl_native = importlib.import_module("hermax.core.wmaxcdcl")
            self._backend_ctor = wmaxcdcl_native.WMaxCDCL
        except Exception as exc:
            raise RuntimeError("WMaxCDCL native module is not available in this build.") from exc
        self.solver = self._backend_ctor()

        self._model: Optional[List[int]] = None
        self._status: SolveStatus = SolveStatus.UNKNOWN
        self._last_cost: Optional[int] = None

        self._hard_clauses: List[List[int]] = []
        self._soft_by_lit: Dict[int, int] = {}
        self.num_vars = 0

        if formula is not None:
            all_hard = list(getattr(formula, "hard", []))
            soft_attr = getattr(formula, "soft", [])
            if soft_attr and isinstance(soft_attr[0], tuple):
                all_soft_cls = [c for c, _w in soft_attr]
            else:
                all_soft_cls = soft_attr

            max_var = 0
            for cl in all_hard + all_soft_cls:
                for lit in cl:
                    max_var = max(max_var, abs(int(lit)))
            while self.num_vars < max_var:
                self.new_var()

            for clause in all_hard:
                self.add_clause(list(map(int, clause)))

            wghts = getattr(formula, "wght", None)
            if wghts is not None and len(wghts) == len(all_soft_cls) and (
                not all_soft_cls or not isinstance(all_soft_cls[0], tuple)
            ):
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
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        for lit in clause:
            if lit == 0:
                raise ValueError("Clause literals cannot be 0.")
            v = abs(int(lit))
            while v > self.num_vars:
                self.new_var()

        if weight is None:
            self._hard_clauses.append([int(x) for x in clause])
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
        v = abs(int(lit))
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
        for _ in range(self.num_vars):
            self.solver.newVar()
        self.solver.setNInputVars(self.num_vars)
        for cl in self._hard_clauses:
            self.solver.addClause(cl, None)
        for lit, w in self._soft_by_lit.items():
            self.solver.addClause([lit], int(w))

    def _compute_wrapper_cost(self, model: List[int]) -> int:
        # IPAMIR semantics in Hermax are defined by wrapper-managed soft unit literals.
        asg = {abs(int(m)): int(m) > 0 for m in model}
        total = 0
        for lit, w in self._soft_by_lit.items():
            v = abs(int(lit))
            val = asg.get(v, False)
            lit_true = val if lit > 0 else (not val)
            if not lit_true:
                total += int(w)
        return total

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False,
    ) -> bool:
        assumps = None
        temp_hard_assumptions: List[int] = []
        if assumptions:
            assumps = [int(l) for l in assumptions]
            for lit in assumps:
                if lit == 0:
                    raise ValueError("Assumptions must be non-zero integers.")
                v = abs(lit)
                while v > self.num_vars:
                    self.new_var()
                temp_hard_assumptions.append(lit)

        self._rebuild_backend()
        for lit in temp_hard_assumptions:
            self.solver.addClause([int(lit)], None)

        try:
            # Native WMaxCDCL binding does not provide IPAMIR-compliant assumptions.
            # We emulate them by rebuilding and adding temporary hard units above.
            res = self.solver.solve(None)
        except Exception:
            self._status = SolveStatus.ERROR
            self._model = None
            self._last_cost = None
            if raise_on_abnormal:
                raise
            return False

        if res:
            self._status = SolveStatus.OPTIMUM
            model = self.solver.getModel()
            if len(model) < self.num_vars:
                for i in range(len(model) + 1, self.num_vars + 1):
                    model.append(-i)
            self._model = model[: self.num_vars]
            self._last_cost = self._compute_wrapper_cost(self._model)
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
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        v = abs(lit)
        if self._model is None or v > self.num_vars:
            raise ValueError("Invalid literal for val().")
        m = self._model[v - 1]
        if lit > 0:
            return 1 if m == v else -1
        return 1 if m == -v else -1

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._status):
            raise RuntimeError("Model is only available for SAT or OPTIMUM status.")
        return self._model

    def signature(self) -> str:
        return "WMaxCDCL (plain, rebuild-per-solve)"

    def close(self) -> None:
        self.solver = None

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars
