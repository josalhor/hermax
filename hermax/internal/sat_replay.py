"""Journal-backed one-shot SAT execution used by the model convenience API."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from pysat.solvers import Solver as PySATSolver

from hermax.core.formula_journal import FormulaJournal
from hermax.core.time_limits import validate_time_limit


SATStatus = Literal["sat", "unsat", "interrupted"]


@dataclass(frozen=True)
class SATReplayResult:
    status: SATStatus
    model: Optional[list[int]]


def solve_pysat_with_time_limit(
    solver: PySATSolver,
    *,
    assumptions: Sequence[int],
    time_limit: Optional[float],
) -> Optional[bool]:
    """Run one PySAT call and clear any deadline-induced interruption."""
    limit = validate_time_limit(time_limit)
    if limit is None:
        return solver.solve(assumptions=list(assumptions))

    finished = threading.Event()

    def interrupt_when_due() -> None:
        if not finished.is_set():
            solver.interrupt()

    timer = threading.Timer(limit, interrupt_when_due)
    timer.start()
    try:
        return solver.solve_limited(
            assumptions=list(assumptions),
            expect_interrupt=True,
        )
    finally:
        finished.set()
        timer.cancel()
        timer.join()
        solver.clear_interrupt()


class PySATReplaySolver:
    """Hard-clause-only SAT solver rebuilt from a :class:`FormulaJournal`."""

    def __init__(self, solver_name: str) -> None:
        self._solver_name = str(solver_name)
        self._journal = FormulaJournal()

    def new_var(self) -> int:
        return self._journal.new_var()

    def ensure_var(self, var: int) -> None:
        self._journal.ensure_var(int(var))

    def add_clause(self, clause: Sequence[int]) -> None:
        if not isinstance(clause, (list, tuple)):
            raise TypeError("Clause must be a sequence of non-zero literals.")
        normalized = [int(lit) for lit in clause]
        if any(lit == 0 for lit in normalized):
            raise ValueError("Literal 0 is invalid.")
        self._journal.add_hard(normalized)

    def solve(
        self,
        *,
        assumptions: Optional[Sequence[int]] = None,
        time_limit: Optional[float] = None,
    ) -> SATReplayResult:
        normalized_assumptions = [int(lit) for lit in assumptions or []]
        if any(lit == 0 for lit in normalized_assumptions):
            raise ValueError("Literal 0 is invalid.")
        for lit in normalized_assumptions:
            self._journal.ensure_var(abs(lit))

        snapshot = self._journal.snapshot()
        with PySATSolver(name=self._solver_name) as solver:
            solver.append_formula(snapshot["hard_clauses"])
            sat = solve_pysat_with_time_limit(
                solver,
                assumptions=normalized_assumptions,
                time_limit=time_limit,
            )
            if sat is None:
                return SATReplayResult(status="interrupted", model=None)
            if not sat:
                return SATReplayResult(status="unsat", model=None)
            model = [int(lit) for lit in solver.get_model() or []]
            assigned = {abs(lit) for lit in model}
            model.extend(-var for var in range(1, self._journal.num_vars + 1) if var not in assigned)
            return SATReplayResult(status="sat", model=model)
