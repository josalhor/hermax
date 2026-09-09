from __future__ import annotations

import abc
from typing import List, Optional

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, is_feasible
from hermax.core.ipamir_state_mixin import IPAMIRStateMixin
from hermax.core.formula_journal import FormulaJournal
from hermax.core.interrupt_recovery import InterruptRecovery
from hermax.core.time_limits import validate_time_limit
from hermax.core.utils import extract_wcnf_data, normalize_wcnf_formula


class NativeIncrementalSolverBase(IPAMIRStateMixin, IPAMIRSolver, InterruptRecovery, abc.ABC):

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self._init_ipamir_state()
        self._journal = FormulaJournal()
        # Backend variables allocated only to submit an operation are kept
        # provisional until that operation is recorded in the journal.
        self._provisional_num_vars = 0
        self._rebuild_on_interrupt = False
        self._replaying_journal = False
        if formula is not None:
            self._load_initial_formula(formula)

    def _ensure_var(self, var: int) -> None:
        target = int(var)
        provisional = self._provisional_num_vars
        while target > max(self.num_vars, provisional):
            next_var = max(self.num_vars, provisional) + 1
            self._backend_new_var(next_var)
            provisional = next_var
            self._provisional_num_vars = provisional

    @property
    def num_vars(self) -> int:
        return self._journal.num_vars

    def _normalize_lit(self, lit: int) -> int:
        if isinstance(lit, bool) or not isinstance(lit, int):
            raise TypeError("Literal must be an integer.")
        ilit = lit
        if ilit == 0:
            raise ValueError("Literal 0 is invalid.")
        return ilit

    def _normalize_assumptions(self, assumptions: Optional[List[int]]) -> List[int]:
        return [self._normalize_lit(x) for x in assumptions] if assumptions else []

    def _normalize_clause(self, clause: List[int]) -> List[int]:
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        normalized = [self._normalize_lit(x) for x in clause]
        for lit in normalized:
            self._ensure_var(abs(lit))
        return normalized

    @staticmethod
    def _normalize_positive_weight(weight: int) -> int:
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ValueError("Weight must be an integer.")
        if int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        return int(weight)

    @staticmethod
    def _normalize_nonnegative_weight(weight: int) -> int:
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ValueError("Weight must be an integer.")
        if int(weight) < 0:
            raise ValueError("Weight must be a non-negative integer.")
        return int(weight)

    def _set_feasible_result(self, model: List[int], cost: int, *, status) -> None:
        self._set_result(status=status, model=model, cost=int(cost), num_vars=self.num_vars)

    def _set_infeasible_result(self, *, status) -> None:
        self._set_result(status=status, model=None, cost=None)

    def set_rebuild_on_interrupt(self, enabled: bool = True) -> None:
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool.")
        if enabled and not self._can_interrupt():
            raise NotImplementedError(
                f"{self.signature()} cannot be interrupted during a live solve."
            )
        self._rebuild_on_interrupt = enabled

    def _can_interrupt(self) -> bool:
        """Whether this backend can be stopped while it is solving."""
        return False

    def _can_reuse_after_interrupt(self) -> bool:
        """Whether this backend remains usable after it has been stopped."""
        return False

    def _rebuild_from_journal(self) -> None:
        """Create a fresh backend and replay the canonical formula journal."""
        self._reset_backend_for_rebuild()
        self._replaying_journal = True
        try:
            self._journal.replay(
                new_var=self._backend_new_var,
                add_hard=self.add_clause,
                set_soft=self.set_soft,
                add_soft_nonunit=self._replay_nonunit_soft,
            )
        finally:
            self._replaying_journal = False

    def _reset_backend_for_rebuild(self) -> None:
        """Replace native state and clear any backend-specific derived state."""
        raise NotImplementedError

    def _replay_nonunit_soft(self, clause: List[int], weight: int) -> None:
        """Replay stored non-unit soft clauses when a native wrapper supports them."""
        raise NotImplementedError(
            "This native solver cannot replay stored non-unit soft clauses."
        )

    def _record_hard_clause(self, clause: List[int]) -> None:
        if not self._replaying_journal:
            self._journal.ensure_var(max((abs(int(lit)) for lit in clause), default=0))
            self._journal.add_hard(clause)

    def _record_soft_unit(self, lit: int, weight: int) -> None:
        if not self._replaying_journal:
            self._journal.ensure_var(abs(int(lit)))
            self._journal.set_soft(lit, weight)

    def _validate_live_time_limit(self, time_limit: Optional[float]) -> None:
        self._reject_time_limit(time_limit)

    def _prepare_live_time_limit(self, time_limit: Optional[float]) -> None:
        """Validate a live deadline before a backend starts solving.

        Concrete wrappers call this only after they have implemented a tested
        interruption path.  The base intentionally does not infer support from
        ``set_terminate``.
        """
        if validate_time_limit(time_limit) is None:
            return
        if not self._can_interrupt():
            raise NotImplementedError(
                f"{self.signature()} cannot be interrupted during a live solve."
            )
        if not self._can_reuse_after_interrupt() and not self._rebuild_on_interrupt:
            raise RuntimeError(
                f"{self.signature()} may not be reused after interruption. "
                "Call set_rebuild_on_interrupt(True) before solving with time_limit."
            )

    def _finish_live_time_limit(self, *, interrupted: bool) -> None:
        """Restore a safely reusable backend after a time-limited solve."""
        if interrupted and not self._can_reuse_after_interrupt():
            self._rebuild_from_journal()

    def new_var(self) -> int:
        self._require_open()
        var = max(self.num_vars, self._provisional_num_vars) + 1
        self._backend_new_var(var)
        self._journal.ensure_var(var)
        self._provisional_num_vars = var
        self._invalidate_solution()
        return var

    def close(self) -> None:
        self._journal.clear()
        super().close()

    def _backend_new_var(self, var_id: int) -> None:
        """Optional native hook for backends that require explicit var allocation."""
        _ = var_id

    def _load_initial_formula(self, formula: WCNF) -> None:
        data = extract_wcnf_data(formula)
        max_var = data.num_vars
        for cl in [*data.hard, *(clause for clause, _weight in data.soft)]:
            for lit in cl:
                ilit = int(lit)
                if ilit == 0:
                    raise ValueError("CNF contains literal 0.")
                max_var = max(max_var, abs(ilit))
        while self.num_vars < max_var:
            self.new_var()

        for clause in data.hard:
            self.add_clause([int(x) for x in clause])

        for cl, w in data.soft:
            if not cl:
                raise ValueError("Invalid soft in WCNF.")
            if len(cl) == 1:
                self.add_soft_unit(int(cl[0]), int(w))
            else:
                b = self.new_var()
                self.add_soft_relaxed([int(x) for x in cl], int(w), relax_var=b)

    def get_cost(self) -> int:
        self._require_open()
        if not is_feasible(self._status):
            raise RuntimeError("Cost is only available for SAT or OPTIMUM status.")
        if self._last_cost is None:
            raise RuntimeError("Cost is only available for SAT or OPTIMUM status.")
        return int(self._last_cost)

    @abc.abstractmethod
    def signature(self) -> str:  # pragma: no cover - interface method
        raise NotImplementedError
