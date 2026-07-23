"""Random generator for small, type-correct model-semantics cases."""

from __future__ import annotations

import random

from .ast import BoolAtom, Case, Comparison, IntAtom, Linear, ScaledInt, Value, WeightedBool


class Grammar:
    def __init__(self, rng: random.Random, max_depth: int):
        self.rng = rng
        self.max_depth = max(1, max_depth)

    def generate(self) -> Case:
        bool_count = self.rng.randint(1, 3)
        int_count = self.rng.randint(1, 2)
        domains = tuple(self._domain() for _ in range(int_count))
        constraints = tuple(self._comparison(bool_count, int_count) for _ in range(self.rng.randint(1, 3)))
        return Case(bool_count, domains, constraints)

    def _domain(self) -> tuple[int, int]:
        lb = self.rng.choice([-2, -1, 0, 1])
        return lb, lb + self.rng.randint(1, 3)

    def _atom(self, bool_count: int, int_count: int) -> BoolAtom | IntAtom | ScaledInt | WeightedBool:
        kind = self.rng.choice(["bool", "int", "scaled", "weighted_bool"])
        if kind == "bool":
            return BoolAtom(self.rng.randrange(bool_count), self.rng.choice([False, True]))
        if kind == "int":
            return IntAtom(self.rng.randrange(int_count))
        if kind == "scaled":
            return ScaledInt(self.rng.randrange(int_count), self.rng.choice([1, 2, 3]))
        return WeightedBool(self.rng.choice([-2, -1, 1, 2, 3]), BoolAtom(self.rng.randrange(bool_count), self.rng.choice([False, True])))

    def _value(self, bool_count: int, int_count: int) -> Value:
        if self.rng.randrange(self.max_depth + 1) == 0:
            return self._atom(bool_count, int_count)
        terms = tuple(self._atom(bool_count, int_count) for _ in range(self.rng.randint(1, self.max_depth + 1)))
        return Linear(self.rng.randint(-3, 3), terms)

    def _comparison(self, bool_count: int, int_count: int) -> Comparison:
        lhs = self._value(bool_count, int_count)
        rhs = self._value(bool_count, int_count)
        # Literal/literal inequality intentionally retains Python identity semantics.
        while isinstance(lhs, BoolAtom) and isinstance(rhs, BoolAtom):
            rhs = self._value(bool_count, int_count)
        gate = None
        if self.rng.random() < 0.45:
            gate = BoolAtom(self.rng.randrange(bool_count), self.rng.choice([False, True]))
        return Comparison(self.rng.choice(["==", "!=", "<", "<=", ">", ">="]), lhs, rhs, gate)
