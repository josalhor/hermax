"""Canonical incremental state, using the shared native formula representation."""
from __future__ import annotations

import math

from typing import Callable, Dict, List, Optional

from hermax.formula import WCNF
from hermax.core.utils import _SoftTerms


class FormulaJournal:
    """Retain clauses plus IPAMIR's replaceable unit preferences for replay.

    Hard and nonunit soft clauses live in a native formula. Unit preferences use
    a literal map because replacing/removing their weights is an IPAMIR operation,
    distinct from appending an ordered formula term.
    """

    def __init__(self) -> None:
        self._formula = WCNF()
        self._num_vars = 0
        self.soft_units: Dict[int, int | float] = {}

    @property
    def num_vars(self):
        return self._num_vars

    @num_vars.setter
    def num_vars(self, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError('Variable count must be an integer.')
        self._formula.nv = value
        self._num_vars = value

    @property
    def hard_clauses(self):
        return self._formula.hard

    @property
    def soft_nonunit(self):
        return _SoftTerms(self._formula)

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars

    def ensure_var(self, var: int) -> None:
        if isinstance(var, bool) or not isinstance(var, int) or var < 0:
            raise ValueError('Variable count must be a non-negative integer.')
        self.num_vars = max(self.num_vars, var)

    @staticmethod
    def _normalize_literal(lit: int) -> int:
        if isinstance(lit, bool) or not isinstance(lit, int):
            raise TypeError('DIMACS literals must be integers.')
        if lit == 0:
            raise ValueError('DIMACS literal zero is invalid.')
        return lit

    @staticmethod
    def _normalize_weight(weight, *, allow_zero=False):
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise TypeError('Soft weight must be numeric.')
        if isinstance(weight, float) and not math.isfinite(weight):
            raise ValueError('Soft weight must be finite.')
        if weight < 0 or (not allow_zero and weight == 0):
            raise ValueError('Soft weight must be positive (or zero for removal).')
        return weight

    def add_hard(self, clause: List[int]) -> None:
        copied = [self._normalize_literal(lit) for lit in clause]
        self._append_hard(copied)

    def _append_hard(self, normalized: List[int]) -> None:
        self._formula.append(normalized)
        self.ensure_var(max(map(abs, normalized), default=0))

    def set_soft(self, lit: int, weight: int | float) -> None:
        lit = self._normalize_literal(lit)
        weight = self._normalize_weight(weight, allow_zero=True)
        self.ensure_var(abs(lit))
        if weight == 0:
            self.soft_units.pop(lit, None)
        else:
            self.soft_units[lit] = weight

    def add_soft_nonunit(self, clause: List[int], weight: int | float) -> None:
        copied = [self._normalize_literal(lit) for lit in clause]
        weight = self._normalize_weight(weight)
        if len(copied) < 2:
            raise ValueError("Stored nonunit soft clauses need at least two literals.")
        self._formula.append(copied, weight=weight)
        self.ensure_var(max(map(abs, copied), default=0))

    def to_formula(self, assumptions=()) -> WCNF:
        """Return an independent native formula; assumptions become hard units."""
        result = WCNF()
        result.hard = self.hard_clauses
        result.nv = self.num_vars
        for lit in assumptions:
            result.append([self._normalize_literal(lit)])
        for lit, weight in self.soft_units.items():
            result.append([lit], weight=weight)
        result.soft.extend(self._formula.soft)
        result.wght.extend(self._formula.wght)
        return result

    def snapshot(self, assumptions_as_hard_units: Optional[List[int]] = None) -> Dict[str, object]:
        """Materialize independent Python values only for the process boundary."""
        assumptions = [self._normalize_literal(lit) for lit in assumptions_as_hard_units or ()]
        hard = self.hard_clauses.to_lists()
        hard.extend([[lit] for lit in assumptions])
        return {
            'num_vars': max(self.num_vars, max(map(abs, assumptions), default=0)),
            'hard_clauses': hard,
            'soft_units': list(self.soft_units.items()),
            'soft_nonunit': [(list(clause), weight) for clause, weight in self.soft_nonunit],
        }

    @classmethod
    def from_snapshot(cls, snapshot: Dict[str, object]) -> 'FormulaJournal':
        journal = cls()
        journal.num_vars = snapshot['num_vars']
        for clause in snapshot['hard_clauses']:
            journal.add_hard(clause)
        for lit, weight in snapshot['soft_units']:
            journal.set_soft(lit, weight)
        for clause, weight in snapshot['soft_nonunit']:
            journal.add_soft_nonunit(clause, weight)
        return journal

    def replay(
        self,
        *,
        new_var: Callable[[int], None],
        add_hard: Callable[[List[int]], None],
        set_soft: Callable[[int, int], None],
        add_soft_nonunit: Callable[[List[int], int], None],
        add_hards=None,
    ) -> None:
        for var in range(1, self.num_vars + 1):
            new_var(var)
        if add_hards is not None:
            add_hards(self.hard_clauses)
        else:
            for clause in self.hard_clauses:
                add_hard(list(clause))
        for lit, weight in self.soft_units.items():
            set_soft(lit, weight)
        for clause, weight in self.soft_nonunit:
            add_soft_nonunit(list(clause), weight)

    def clear(self) -> None:
        self._formula = WCNF()
        self._num_vars = 0
        self.soft_units.clear()
