from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.ipamir_state_mixin import IPAMIRStateMixin
from hermax.core.utils import normalize_wcnf_formula


@dataclass(frozen=True)
class ReplaySolveResult:
    status: SolveStatus
    model: Optional[List[int]]
    cost: Optional[int]


class ReplayFormulaSolverBase(IPAMIRStateMixin, IPAMIRSolver, abc.ABC):

    # Non-unit soft policy:
    # - "store": keep as weighted non-unit in _soft_nonunit
    # - "relax": rewrite via add_soft_relaxed with a fresh relax var
    nonunit_soft_policy: str = "store"

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self._init_ipamir_state()

        self._num_vars: int = 0
        self._hard_clauses: List[List[int]] = []
        self._soft_unit_by_lit: Dict[int, int] = {}
        self._soft_nonunit: List[Tuple[List[int], int]] = []

        if formula is not None:
            self._load_initial_formula(formula)

    def new_var(self) -> int:
        self._require_open()
        self._num_vars += 1
        self._invalidate_solution()
        return self._num_vars

    def add_clause(self, clause: List[int], weight: Optional[int] = None) -> None:
        self._require_open()
        cl = self._normalize_clause(clause)

        if weight is None:
            self._hard_clauses.append(cl)
            self._invalidate_solution()
            return

        w = self._normalize_positive_weight(weight)
        if len(cl) == 0:
            raise ValueError("Empty soft clause is not allowed.")
        if len(cl) == 1:
            self.set_soft(cl[0], w)
            return

        if self.nonunit_soft_policy == "store":
            self._soft_nonunit.append((cl, w))
            self._invalidate_solution()
            return
        if self.nonunit_soft_policy == "relax":
            b = self.new_var()
            self.add_soft_relaxed(cl, w, relax_var=b)
            return

        raise ValueError(f"Unknown nonunit_soft_policy: {self.nonunit_soft_policy}")

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        ilit = self._normalize_lit(lit)
        w = self._normalize_nonnegative_weight(weight)
        self._ensure_var(abs(ilit))

        if w == 0:
            self._soft_unit_by_lit.pop(ilit, None)
        else:
            self._soft_unit_by_lit[ilit] = w
        self._invalidate_solution()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        w = self._normalize_positive_weight(weight)
        self.set_soft(int(lit), w)

    def _normalize_lit(self, lit: int) -> int:
        ilit = int(lit)
        if ilit == 0:
            raise ValueError("Literal 0 is invalid.")
        return ilit

    def _normalize_clause(self, clause: List[int]) -> List[int]:
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        cl = [self._normalize_lit(x) for x in clause]
        for lit in cl:
            self._ensure_var(abs(lit))
        return cl

    @staticmethod
    def _normalize_positive_weight(weight: int) -> int:
        if not isinstance(weight, int):
            raise TypeError("Weight must be an integer.")
        if int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        return int(weight)

    @staticmethod
    def _normalize_nonnegative_weight(weight: int) -> int:
        if not isinstance(weight, int):
            raise TypeError("Weight must be an integer.")
        if int(weight) < 0:
            raise ValueError("Weight must be a non-negative integer.")
        return int(weight)

    def _ensure_var(self, var: int) -> None:
        while var > self._num_vars:
            self._num_vars += 1

    def _normalize_assumptions(self, assumptions: Optional[List[int]]) -> List[int]:
        assumps = [self._normalize_lit(a) for a in assumptions] if assumptions else []
        for lit in assumps:
            self._ensure_var(abs(lit))
        return assumps

    def _compute_wrapper_cost(self, model: List[int]) -> int:
        asg = {abs(int(m)): int(m) > 0 for m in model}
        total = 0

        for lit, w in self._soft_unit_by_lit.items():
            v = abs(int(lit))
            val = asg.get(v, False)
            lit_true = val if lit > 0 else (not val)
            if not lit_true:
                total += int(w)

        for cl, w in self._soft_nonunit:
            sat = False
            for l in cl:
                lv = abs(int(l))
                val = asg.get(lv, False)
                if (int(l) > 0 and val) or (int(l) < 0 and not val):
                    sat = True
                    break
            if not sat:
                total += int(w)

        return total

    def _snapshot(self, assumptions_as_hard_units: Optional[List[int]] = None) -> Dict[str, object]:
        hard = [list(cl) for cl in self._hard_clauses]
        if assumptions_as_hard_units:
            hard.extend([[int(a)] for a in assumptions_as_hard_units])
        return {
            "num_vars": int(self._num_vars),
            "hard_clauses": hard,
            "soft_units": [(int(l), int(w)) for l, w in self._soft_unit_by_lit.items()],
            "soft_nonunit": [(list(cl), int(w)) for cl, w in self._soft_nonunit],
        }

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._require_open()
        self._invalidate_solution()
        assumps = self._normalize_assumptions(assumptions)

        result = self._run_replay_solve(assumps)
        self._set_result(
            status=result.status,
            model=result.model,
            cost=result.cost,
            num_vars=self._num_vars,
        )
        if self._model is not None and is_feasible(self._status):
            self._last_cost = self._compute_wrapper_cost(self._model)

        self._maybe_raise_on_abnormal(raise_on_abnormal)
        return is_feasible(self._status)

    @abc.abstractmethod
    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        """Replay current cached formula to backend and solve once."""

    def _load_initial_formula(self, formula: WCNF) -> None:
        for cl in getattr(formula, "hard", []):
            self.add_clause(list(map(int, cl)))

        soft_attr = getattr(formula, "soft", [])
        wghts = getattr(formula, "wght", None)
        if wghts is not None and len(wghts) == len(soft_attr) and (
            not soft_attr or not isinstance(soft_attr[0], tuple)
        ):
            for cl, w in zip(soft_attr, wghts):
                self.add_clause(list(map(int, cl)), int(w))
            return

        for item in soft_attr:
            if isinstance(item, tuple) and len(item) >= 2:
                cl, w = item[0], item[1]
            else:
                cl, w = item, 1
            self.add_clause(list(map(int, cl)), int(w))

    def close(self) -> None:
        self._closed = True
        self._hard_clauses.clear()
        self._soft_unit_by_lit.clear()
        self._soft_nonunit.clear()
        self._invalidate_solution()
