"""Canonical incremental formula state shared by replayable solvers."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple


class FormulaJournal:
    """Store the logical operations needed to rebuild a solver backend."""

    def __init__(self) -> None:
        self.num_vars = 0
        self.hard_clauses: List[List[int]] = []
        self.soft_units: Dict[int, int] = {}
        self.soft_nonunit: List[Tuple[List[int], int]] = []

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars

    def ensure_var(self, var: int) -> None:
        while self.num_vars < int(var):
            self.new_var()

    def add_hard(self, clause: List[int]) -> None:
        copied = [int(lit) for lit in clause]
        self._ensure_clause_vars(copied)
        self.hard_clauses.append(copied)

    def set_soft(self, lit: int, weight: int) -> None:
        self.ensure_var(abs(int(lit)))
        if int(weight) == 0:
            self.soft_units.pop(int(lit), None)
        else:
            self.soft_units[int(lit)] = int(weight)

    def add_soft_nonunit(self, clause: List[int], weight: int) -> None:
        copied = [int(lit) for lit in clause]
        self._ensure_clause_vars(copied)
        self.soft_nonunit.append((copied, int(weight)))

    def _ensure_clause_vars(self, clause: List[int]) -> None:
        for lit in clause:
            self.ensure_var(abs(int(lit)))

    def snapshot(self, assumptions_as_hard_units: Optional[List[int]] = None) -> Dict[str, object]:
        hard = [list(clause) for clause in self.hard_clauses]
        if assumptions_as_hard_units:
            hard.extend([[int(lit)] for lit in assumptions_as_hard_units])
        return {
            "num_vars": int(self.num_vars),
            "hard_clauses": hard,
            "soft_units": [(int(lit), int(weight)) for lit, weight in self.soft_units.items()],
            "soft_nonunit": [(list(clause), int(weight)) for clause, weight in self.soft_nonunit],
        }

    def replay(
        self,
        *,
        new_var: Callable[[int], None],
        add_hard: Callable[[List[int]], None],
        set_soft: Callable[[int, int], None],
        add_soft_nonunit: Callable[[List[int], int], None],
    ) -> None:
        for var in range(1, self.num_vars + 1):
            new_var(var)
        for clause in self.hard_clauses:
            add_hard(list(clause))
        for lit, weight in self.soft_units.items():
            set_soft(int(lit), int(weight))
        for clause, weight in self.soft_nonunit:
            add_soft_nonunit(list(clause), int(weight))

    def clear(self) -> None:
        self.num_vars = 0
        self.hard_clauses.clear()
        self.soft_units.clear()
        self.soft_nonunit.clear()
