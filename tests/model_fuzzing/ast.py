"""Typed, serializable AST used by the model-semantics fuzzer.

Nodes have two independent meanings: ``evaluate`` is the integer oracle and
``emit`` builds the corresponding public Hermax expression.  Keeping these
paths separate is what makes compiler mismatches observable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from hermax.model import Model


Environment = Mapping[str, int]


@dataclass(frozen=True)
class BoolAtom:
    index: int
    negated: bool = False

    def evaluate(self, env: Environment) -> int:
        value = int(env[f"b{self.index}"])
        return 1 - value if self.negated else value

    def emit(self, bools, _ints):
        lit = bools[self.index]
        return ~lit if self.negated else lit

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "bool", "index": self.index, "negated": self.negated}


@dataclass(frozen=True)
class IntAtom:
    index: int

    def evaluate(self, env: Environment) -> int:
        return int(env[f"i{self.index}"])

    def emit(self, _bools, ints):
        return ints[self.index]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "int", "index": self.index}


@dataclass(frozen=True)
class ScaledInt:
    index: int
    factor: int

    def evaluate(self, env: Environment) -> int:
        return self.factor * int(env[f"i{self.index}"])

    def emit(self, _bools, ints):
        return ints[self.index].scale(self.factor)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "scaled_int", "index": self.index, "factor": self.factor}


@dataclass(frozen=True)
class WeightedBool:
    coefficient: int
    atom: BoolAtom

    def evaluate(self, env: Environment) -> int:
        return self.coefficient * self.atom.evaluate(env)

    def emit(self, bools, ints):
        return self.coefficient * self.atom.emit(bools, ints)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "weighted_bool", "coefficient": self.coefficient, "atom": self.atom.to_dict()}


@dataclass(frozen=True)
class Linear:
    constant: int
    terms: tuple[BoolAtom | IntAtom | ScaledInt | WeightedBool, ...]

    def evaluate(self, env: Environment) -> int:
        return self.constant + sum(term.evaluate(env) for term in self.terms)

    def emit(self, bools, ints):
        result = self.constant
        for term in self.terms:
            result = result + term.emit(bools, ints)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "linear", "constant": self.constant, "terms": [term.to_dict() for term in self.terms]}


Value = BoolAtom | IntAtom | ScaledInt | WeightedBool | Linear


def value_from_dict(payload: Mapping[str, Any]) -> Value:
    kind = str(payload["kind"])
    if kind == "bool":
        return BoolAtom(int(payload["index"]), bool(payload.get("negated", False)))
    if kind == "int":
        return IntAtom(int(payload["index"]))
    if kind == "scaled_int":
        return ScaledInt(int(payload["index"]), int(payload["factor"]))
    if kind == "weighted_bool":
        atom = value_from_dict(payload["atom"])
        if not isinstance(atom, BoolAtom):
            raise ValueError("weighted_bool requires a Boolean atom")
        return WeightedBool(int(payload["coefficient"]), atom)
    if kind == "linear":
        terms = tuple(value_from_dict(item) for item in payload["terms"])
        if not all(isinstance(term, (BoolAtom, IntAtom, ScaledInt, WeightedBool)) for term in terms):
            raise ValueError("linear terms must be atomic values")
        return Linear(int(payload["constant"]), terms)
    raise ValueError(f"Unknown value kind: {kind!r}")


@dataclass(frozen=True)
class Comparison:
    op: str
    lhs: Value
    rhs: Value
    gate: BoolAtom | None = None

    def evaluate(self, env: Environment) -> bool:
        left = self.lhs.evaluate(env)
        right = self.rhs.evaluate(env)
        satisfied = {
            "==": left == right,
            "!=": left != right,
            "<": left < right,
            "<=": left <= right,
            ">": left > right,
            ">=": left >= right,
        }[self.op]
        if self.gate is None:
            return satisfied
        return not self.gate.evaluate(env) or satisfied

    def emit(self, bools, ints):
        lhs = self.lhs.emit(bools, ints)
        rhs = self.rhs.emit(bools, ints)
        constraint = {
            "==": lambda: lhs == rhs,
            "!=": lambda: lhs != rhs,
            "<": lambda: lhs < rhs,
            "<=": lambda: lhs <= rhs,
            ">": lambda: lhs > rhs,
            ">=": lambda: lhs >= rhs,
        }[self.op]()
        if isinstance(constraint, bool):
            raise TypeError("Generated comparison unexpectedly evaluated to a Python bool")
        return constraint if self.gate is None else constraint.only_if(self.gate.emit(bools, ints))

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "lhs": self.lhs.to_dict(),
            "rhs": self.rhs.to_dict(),
            "gate": None if self.gate is None else self.gate.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Comparison":
        gate_payload = payload.get("gate")
        gate = None if gate_payload is None else value_from_dict(gate_payload)
        if gate is not None and not isinstance(gate, BoolAtom):
            raise ValueError("comparison gate must be a Boolean atom")
        return cls(str(payload["op"]), value_from_dict(payload["lhs"]), value_from_dict(payload["rhs"]), gate)


@dataclass(frozen=True)
class Case:
    bool_count: int
    int_domains: tuple[tuple[int, int], ...]
    constraints: tuple[Comparison, ...]

    def build(self) -> tuple[Model, list, list]:
        model = Model()
        bools = [model.bool(f"b{index}") for index in range(self.bool_count)]
        ints = [model.int(f"i{index}", lb, ub) for index, (lb, ub) in enumerate(self.int_domains)]
        return model, bools, ints

    def to_dict(self) -> dict[str, Any]:
        return {
            "bool_count": self.bool_count,
            "int_domains": [list(domain) for domain in self.int_domains],
            "constraints": [constraint.to_dict() for constraint in self.constraints],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Case":
        domains = tuple((int(lb), int(ub)) for lb, ub in payload["int_domains"])
        return cls(int(payload["bool_count"]), domains, tuple(Comparison.from_dict(c) for c in payload["constraints"]))
