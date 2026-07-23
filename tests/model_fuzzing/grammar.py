"""Random generator for small, type-correct model-semantics cases."""

from __future__ import annotations

import random

from .ast import (
    AggregateComparison,
    BoolAtom,
    BoolClauseConstraint,
    Case,
    Comparison,
    Const,
    EnumComparison,
    IntAtom,
    NativeIntComparison,
    ReifiedIntRelation,
    ScaledInt,
    SequenceExpr,
    Value,
    WeightedBool,
)


class Grammar:
    def __init__(self, rng: random.Random, max_width: int):
        self.rng = rng
        self.max_width = max(1, max_width)

    def generate(self) -> Case:
        bool_count = self.rng.randint(1, 3)
        int_count = self.rng.randint(1, 3)
        domains = tuple(self._domain() for _ in range(int_count))
        enum_choices = () if self.rng.random() < 0.55 else (tuple(self.rng.sample(["red", "green", "blue"], self.rng.randint(2, 3))),)
        constraints = tuple(self._constraint(bool_count, domains, enum_choices) for _ in range(self.rng.randint(1, 3)))
        return Case(bool_count, domains, constraints, enum_choices)

    def _domain(self) -> tuple[int, int]:
        lb = self.rng.choice([-2, -1, 0, 1])
        return lb, lb + self.rng.randint(1, 3)

    def _atom(self, bool_count: int, int_count: int) -> Const | BoolAtom | IntAtom | ScaledInt | WeightedBool:
        kind = self.rng.choice(["const", "bool", "int", "scaled", "weighted_bool"])
        if kind == "const":
            return Const(self.rng.randint(-3, 3))
        if kind == "bool":
            return BoolAtom(self.rng.randrange(bool_count), self.rng.choice([False, True]))
        if kind == "int":
            return IntAtom(self.rng.randrange(int_count))
        if kind == "scaled":
            return ScaledInt(self.rng.randrange(int_count), self.rng.choice([1, 2, 3]))
        return WeightedBool(self.rng.choice([-2, -1, 1, 2, 3]), BoolAtom(self.rng.randrange(bool_count), self.rng.choice([False, True])))

    def _value(self, bool_count: int, int_count: int) -> Value:
        width = self.rng.randint(1, self.max_width)
        if width == 1:
            return self._atom(bool_count, int_count)
        start = self._atom(bool_count, int_count)
        steps = [(self.rng.choice(["+", "-"]), self._atom(bool_count, int_count)) for _ in range(width - 1)]
        if isinstance(start, Const) and all(isinstance(value, Const) for _op, value in steps):
            steps[-1] = (steps[-1][0], IntAtom(self.rng.randrange(int_count)))
        return SequenceExpr(start, tuple(steps))

    @staticmethod
    def _constant_value(value: Value) -> int | None:
        if isinstance(value, Const):
            return value.value
        if isinstance(value, SequenceExpr):
            start = Grammar._constant_value(value.start)
            if start is None:
                return None
            result = start
            for op, step in value.steps:
                step_value = Grammar._constant_value(step)
                if step_value is None:
                    return None
                result = result + step_value if op == "+" else result - step_value
            return result
        return None

    def _sanitize_scalar_equality_rhs(
        self,
        lhs: Value,
        op: str,
        rhs: Value,
        domains: tuple[tuple[int, int], ...],
    ) -> Value:
        """Avoid direct equality/inequality against out-of-domain constants."""
        if op not in {"==", "!="}:
            return rhs
        constant = self._constant_value(rhs)
        if constant is None:
            return rhs

        if isinstance(lhs, BoolAtom):
            in_domain = constant in (0, 1)
        elif isinstance(lhs, IntAtom):
            lb, ub = domains[lhs.index]
            in_domain = lb <= constant <= ub
        else:
            return rhs

        if in_domain:
            return rhs

        # Preserve a PB comparison while avoiding the intentionally invalid
        # direct scalar form (for example, ``literal == 2`` or ``x == lb - 1``).
        return SequenceExpr(Const(0), (("+", IntAtom(self.rng.randrange(len(domains)))),))

    def _comparison(self, bool_count: int, domains: tuple[tuple[int, int], ...]) -> Comparison:
        int_count = len(domains)
        lhs = self._value(bool_count, int_count)
        rhs = self._value(bool_count, int_count)
        # Force the comparison through PBConstraint rather than the specialized
        # Literal/IntRelation APIs so every implication form below is supported.
        if not isinstance(lhs, SequenceExpr) and not isinstance(rhs, SequenceExpr):
            if isinstance(lhs, Const) and isinstance(rhs, Const):
                lhs = IntAtom(self.rng.randrange(int_count))
            rhs = SequenceExpr(Const(0), (("+", rhs),))
        op = self.rng.choice(["==", "!=", "<", "<=", ">", ">="])
        rhs = self._sanitize_scalar_equality_rhs(lhs, op, rhs, domains)
        mode = self.rng.choices(
            ["only_if", "literal_implies", "clause_implies", "pb_implies"],
            weights=[55, 20, 15, 10],
            k=1,
        )[0]
        atom = lambda: BoolAtom(self.rng.randrange(bool_count), self.rng.choice([False, True]))
        if mode == "only_if":
            gates = tuple(atom() for _ in range(self.rng.choices([0, 1, 2], weights=[55, 30, 15], k=1)[0]))
            return Comparison(op, lhs, rhs, gates=gates)
        if mode == "literal_implies":
            return Comparison(op, lhs, rhs, mode=mode, antecedent=(atom(),))
        if mode == "clause_implies":
            return Comparison(op, lhs, rhs, mode=mode, antecedent=(atom(), atom()))
        return Comparison(op, lhs, rhs, mode=mode, target=atom())

    def _native_int(self, domains: tuple[tuple[int, int], ...]) -> NativeIntComparison:
        index = self.rng.randrange(len(domains))
        op = self.rng.choice(["==", "!=", "<", "<=", ">", ">="])
        if self.rng.random() < 0.55:
            lb, ub = domains[index]
            constant = Const(self.rng.randint(lb, ub))
            return NativeIntComparison(op, IntAtom(index), constant) if self.rng.random() < 0.5 else NativeIntComparison(op, constant, IntAtom(index))
        return NativeIntComparison(op, IntAtom(index), IntAtom(self.rng.randrange(len(domains))))

    def _bool_clause(self, bool_count: int) -> BoolClauseConstraint:
        atom = lambda: BoolAtom(self.rng.randrange(bool_count), self.rng.choice([False, True]))
        literals = tuple(atom() for _ in range(self.rng.randint(2, 3)))
        gates = tuple(atom() for _ in range(self.rng.choice([0, 0, 1, 2])))
        return BoolClauseConstraint(literals, gates)

    def _reified_relation(self, bool_count: int, int_count: int) -> ReifiedIntRelation:
        return ReifiedIntRelation(
            BoolAtom(self.rng.randrange(bool_count), self.rng.choice([False, True])),
            self.rng.choice(["==", "<", "<=", ">", ">="]),
            IntAtom(self.rng.randrange(int_count)),
            IntAtom(self.rng.randrange(int_count)),
        )

    def _aggregate(self, domains: tuple[tuple[int, int], ...]) -> AggregateComparison:
        indices = tuple(self.rng.sample(range(len(domains)), k=min(2, len(domains))))
        kind = self.rng.choice(["min", "max"])
        lo, hi = self._aggregate_domain(kind, indices, domains)
        rhs = Const(self.rng.randint(lo, hi)) if self.rng.random() < 0.65 else IntAtom(self.rng.randrange(len(domains)))
        return AggregateComparison(kind, indices, self.rng.choice(["==", "!=", "<", "<=", ">", ">="]), rhs)

    @staticmethod
    def _aggregate_domain(kind: str, indices: tuple[int, ...], domains: tuple[tuple[int, int], ...]) -> tuple[int, int]:
        selected = [domains[index] for index in indices]
        if kind == "max":
            return max(lb for lb, _ub in selected), max(ub for _lb, ub in selected)
        if kind == "min":
            return min(lb for lb, _ub in selected), min(ub for _lb, ub in selected)
        raise ValueError(f"Unknown aggregate kind: {kind!r}")

    def _constraint(self, bool_count: int, domains: tuple[tuple[int, int], ...], enum_choices: tuple[tuple[str, ...], ...]):
        choices = ["pb", "native", "clause", "reified", "aggregate"]
        weights = [45, 25, 15, 10, 5]
        if enum_choices:
            choices.append("enum")
            weights.append(8)
        kind = self.rng.choices(choices, weights=weights, k=1)[0]
        if kind == "pb":
            return self._comparison(bool_count, domains)
        if kind == "native":
            return self._native_int(domains)
        if kind == "clause":
            return self._bool_clause(bool_count)
        if kind == "reified":
            return self._reified_relation(bool_count, len(domains))
        if kind == "aggregate":
            return self._aggregate(domains)
        return EnumComparison(0, self.rng.choice(["==", "!="]), self.rng.choice(enum_choices[0]))
