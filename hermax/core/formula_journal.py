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

    @staticmethod
    def _normalize_literal(lit: int) -> int:
        if isinstance(lit, bool) or not isinstance(lit, int):
            raise TypeError("DIMACS literals must be integers.")
        if lit == 0:
            raise ValueError("DIMACS literal zero is invalid.")
        return int(lit)

    def add_hard(self, clause: List[int]) -> None:
        copied = [self._normalize_literal(lit) for lit in clause]
        self._ensure_clause_vars(copied)
        self.hard_clauses.append(copied)

    def set_soft(self, lit: int, weight: int) -> None:
        normalized_lit = self._normalize_literal(lit)
        self.ensure_var(abs(normalized_lit))
        if int(weight) == 0:
            self.soft_units.pop(normalized_lit, None)
        else:
            self.soft_units[normalized_lit] = int(weight)

    def add_soft_nonunit(self, clause: List[int], weight: int) -> None:
        copied = [self._normalize_literal(lit) for lit in clause]
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

    @classmethod
    def from_snapshot(cls, snapshot: Dict[str, object]) -> "FormulaJournal":
        journal = cls()
        journal.num_vars = int(snapshot["num_vars"])
        journal.hard_clauses = [list(clause) for clause in snapshot["hard_clauses"]]  # type: ignore[index]
        journal.soft_units = {int(lit): int(weight) for lit, weight in snapshot["soft_units"]}  # type: ignore[index]
        journal.soft_nonunit = [(list(clause), int(weight)) for clause, weight in snapshot["soft_nonunit"]]  # type: ignore[index]
        return journal

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
