"""Typed, serializable AST used by the model-semantics fuzzer.

Nodes have two independent meanings: ``evaluate`` is the integer oracle and
``emit`` builds the corresponding public Hermax expression.  Keeping these
paths separate is what makes compiler mismatches observable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from hermax.model import Model


Environment = Mapping[str, Any]


def _compare(op: str, lhs, rhs):
    return {
        "==": lambda: lhs == rhs,
        "!=": lambda: lhs != rhs,
        "<": lambda: lhs < rhs,
        "<=": lambda: lhs <= rhs,
        ">": lambda: lhs > rhs,
        ">=": lambda: lhs >= rhs,
    }[op]()


def _compare_values(op: str, lhs: int, rhs: int) -> bool:
    return {"==": lhs == rhs, "!=": lhs != rhs, "<": lhs < rhs, "<=": lhs <= rhs, ">": lhs > rhs, ">=": lhs >= rhs}[op]


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
class Const:
    value: int

    def evaluate(self, _env: Environment) -> int:
        return self.value

    def emit(self, _bools, _ints):
        return self.value

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "const", "value": self.value}


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

    def emit(self, bools, ints, **_ignored):
        return self.coefficient * self.atom.emit(bools, ints)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "weighted_bool", "coefficient": self.coefficient, "atom": self.atom.to_dict()}


@dataclass(frozen=True)
class Linear:
    constant: int
    terms: tuple[BoolAtom | IntAtom | ScaledInt | WeightedBool, ...]

    def evaluate(self, env: Environment) -> int:
        return self.constant + sum(term.evaluate(env) for term in self.terms)

    def emit(self, bools, ints, **_ignored):
        result = self.constant
        for term in self.terms:
            result = result + term.emit(bools, ints)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "linear", "constant": self.constant, "terms": [term.to_dict() for term in self.terms]}


@dataclass(frozen=True)
class SequenceExpr:
    """A left-to-right Python ``+``/``-`` construction sequence."""
    start: Const | BoolAtom | IntAtom | ScaledInt | WeightedBool
    steps: tuple[tuple[str, Const | BoolAtom | IntAtom | ScaledInt | WeightedBool], ...]

    def evaluate(self, env: Environment) -> int:
        result = self.start.evaluate(env)
        for op, value in self.steps:
            result = result + value.evaluate(env) if op == "+" else result - value.evaluate(env)
        return result

    def emit(self, bools, ints, **_ignored):
        result = self.start.emit(bools, ints)
        for op, value in self.steps:
            result = result + value.emit(bools, ints) if op == "+" else result - value.emit(bools, ints)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "sequence", "start": self.start.to_dict(), "steps": [[op, value.to_dict()] for op, value in self.steps]}


AtomicValue = Const | BoolAtom | IntAtom | ScaledInt | WeightedBool
Value = AtomicValue | Linear | SequenceExpr


def value_from_dict(payload: Mapping[str, Any]) -> Value:
    kind = str(payload["kind"])
    if kind == "bool":
        return BoolAtom(int(payload["index"]), bool(payload.get("negated", False)))
    if kind == "const":
        return Const(int(payload["value"]))
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
    if kind == "sequence":
        start = value_from_dict(payload["start"])
        steps = tuple((str(op), value_from_dict(value)) for op, value in payload["steps"])
        if not isinstance(start, (Const, BoolAtom, IntAtom, ScaledInt, WeightedBool)):
            raise ValueError("sequence start must be atomic")
        if not all(op in {"+", "-"} and isinstance(value, (Const, BoolAtom, IntAtom, ScaledInt, WeightedBool)) for op, value in steps):
            raise ValueError("sequence steps must be atomic additions/subtractions")
        return SequenceExpr(start, steps)
    raise ValueError(f"Unknown value kind: {kind!r}")


@dataclass(frozen=True)
class Comparison:
    op: str
    lhs: Value
    rhs: Value
    gates: tuple[BoolAtom, ...] = ()
    mode: str = "only_if"
    antecedent: tuple[BoolAtom, ...] = ()
    target: BoolAtom | None = None

    def __post_init__(self) -> None:
        if self.mode == "only_if":
            return
        if self.mode == "literal_implies" and len(self.antecedent) == 1:
            return
        if self.mode == "clause_implies" and self.antecedent:
            return
        if self.mode == "pb_implies" and self.target is not None:
            return
        raise ValueError(f"Invalid operands for comparison mode: {self.mode!r}")

    def evaluate(self, env: Environment) -> bool:
        left = self.lhs.evaluate(env)
        right = self.rhs.evaluate(env)
        satisfied = _compare_values(self.op, left, right)
        if self.mode == "only_if":
            return not all(gate.evaluate(env) for gate in self.gates) or satisfied
        if self.mode == "literal_implies":
            return not self.antecedent[0].evaluate(env) or satisfied
        if self.mode == "clause_implies":
            return not any(atom.evaluate(env) for atom in self.antecedent) or satisfied
        if self.mode == "pb_implies":
            if self.target is None:
                raise ValueError("pb_implies requires a literal target")
            return not satisfied or bool(self.target.evaluate(env))
        raise ValueError(f"Unknown comparison mode: {self.mode!r}")

    def emit(self, bools, ints, **_ignored):
        lhs = self.lhs.emit(bools, ints)
        rhs = self.rhs.emit(bools, ints)
        constraint = _compare(self.op, lhs, rhs)
        if isinstance(constraint, bool):
            raise TypeError("Generated comparison unexpectedly evaluated to a Python bool")
        if self.mode == "only_if":
            for gate in self.gates:
                constraint = constraint.only_if(gate.emit(bools, ints))
            return constraint
        if self.mode == "literal_implies":
            return self.antecedent[0].emit(bools, ints).implies(constraint)
        if self.mode == "clause_implies":
            source = self.antecedent[0].emit(bools, ints)
            for atom in self.antecedent[1:]:
                source = source | atom.emit(bools, ints)
            return source.implies(constraint)
        if self.mode == "pb_implies":
            if self.target is None:
                raise ValueError("pb_implies requires a literal target")
            return constraint.implies(self.target.emit(bools, ints))
        raise ValueError(f"Unknown comparison mode: {self.mode!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "comparison",
            "op": self.op,
            "lhs": self.lhs.to_dict(),
            "rhs": self.rhs.to_dict(),
            "gates": [gate.to_dict() for gate in self.gates],
            "mode": self.mode,
            "antecedent": [atom.to_dict() for atom in self.antecedent],
            "target": None if self.target is None else self.target.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Comparison":
        # Accept artifacts emitted before multi-gate and implication support.
        if "gates" in payload:
            gate_values = tuple(value_from_dict(item) for item in payload["gates"])
        else:
            legacy_gate = payload.get("gate")
            gate_values = () if legacy_gate is None else (value_from_dict(legacy_gate),)
        antecedent = tuple(value_from_dict(item) for item in payload.get("antecedent", []))
        target_payload = payload.get("target")
        target = None if target_payload is None else value_from_dict(target_payload)
        if not all(isinstance(gate, BoolAtom) for gate in gate_values):
            raise ValueError("comparison gates must be Boolean atoms")
        if not all(isinstance(atom, BoolAtom) for atom in antecedent):
            raise ValueError("comparison antecedent must contain Boolean atoms")
        if target is not None and not isinstance(target, BoolAtom):
            raise ValueError("comparison target must be a Boolean atom")
        return cls(
            str(payload["op"]),
            value_from_dict(payload["lhs"]),
            value_from_dict(payload["rhs"]),
            gate_values,
            str(payload.get("mode", "only_if")),
            antecedent,
            target,
        )


@dataclass(frozen=True)
class NativeIntComparison:
    """Direct ``IntVar``/constant or ``IntVar``/``IntVar`` relation."""
    op: str
    lhs: Const | IntAtom
    rhs: Const | IntAtom

    def evaluate(self, env: Environment) -> bool:
        return _compare_values(self.op, self.lhs.evaluate(env), self.rhs.evaluate(env))

    def emit(self, bools, ints, **_ignored):
        return _compare(self.op, self.lhs.emit(bools, ints), self.rhs.emit(bools, ints))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "native_int", "op": self.op, "lhs": self.lhs.to_dict(), "rhs": self.rhs.to_dict()}


@dataclass(frozen=True)
class BoolClauseConstraint:
    literals: tuple[BoolAtom, ...]
    gates: tuple[BoolAtom, ...] = ()

    def evaluate(self, env: Environment) -> bool:
        return not all(gate.evaluate(env) for gate in self.gates) or any(lit.evaluate(env) for lit in self.literals)

    def emit(self, bools, ints, **_ignored):
        clause = self.literals[0].emit(bools, ints)
        for literal in self.literals[1:]:
            clause = clause | literal.emit(bools, ints)
        for gate in self.gates:
            clause = clause.only_if(gate.emit(bools, ints))
        return clause

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "bool_clause", "literals": [lit.to_dict() for lit in self.literals], "gates": [gate.to_dict() for gate in self.gates]}


@dataclass(frozen=True)
class ReifiedIntRelation:
    literal: BoolAtom
    op: str
    lhs: IntAtom
    rhs: IntAtom

    def __post_init__(self) -> None:
        # IntVar != IntVar is a ClauseGroup, not a native IntRelation, and the
        # strict modeling API intentionally does not reify arbitrary formulas.
        if self.op not in {"==", "<", "<=", ">", ">="}:
            raise ValueError(f"Unsupported reified integer relation: {self.op!r}")

    def evaluate(self, env: Environment) -> bool:
        return bool(self.literal.evaluate(env)) == _compare_values(self.op, self.lhs.evaluate(env), self.rhs.evaluate(env))

    def emit(self, bools, ints, **_ignored):
        return self.literal.emit(bools, ints) == _compare(self.op, self.lhs.emit(bools, ints), self.rhs.emit(bools, ints))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "reified_int", "literal": self.literal.to_dict(), "op": self.op, "lhs": self.lhs.to_dict(), "rhs": self.rhs.to_dict()}


@dataclass(frozen=True)
class AggregateComparison:
    kind: str
    indices: tuple[int, ...]
    op: str
    rhs: Const | IntAtom

    def evaluate(self, env: Environment) -> bool:
        values = [int(env[f"i{index}"]) for index in self.indices]
        aggregate = min(values) if self.kind == "min" else max(values)
        return _compare_values(self.op, aggregate, self.rhs.evaluate(env))

    def emit(self, bools, ints, *, model, **_ignored):
        aggregate = model.min([ints[index] for index in self.indices]) if self.kind == "min" else model.max([ints[index] for index in self.indices])
        return _compare(self.op, aggregate, self.rhs.emit(bools, ints))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "aggregate", "aggregate": self.kind, "indices": list(self.indices), "op": self.op, "rhs": self.rhs.to_dict()}


@dataclass(frozen=True)
class EnumComparison:
    index: int
    op: str
    choice: str

    def evaluate(self, env: Environment) -> bool:
        value = env[f"e{self.index}"]
        return value == self.choice if self.op == "==" else value != self.choice

    def emit(self, _bools, _ints, *, enums, **_ignored):
        return _compare(self.op, enums[self.index], self.choice)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "enum", "index": self.index, "op": self.op, "choice": self.choice}


Constraint = Comparison | NativeIntComparison | BoolClauseConstraint | ReifiedIntRelation | AggregateComparison | EnumComparison


def constraint_from_dict(payload: Mapping[str, Any]) -> Constraint:
    kind = str(payload.get("kind", "comparison"))
    if kind == "comparison":
        return Comparison.from_dict(payload)
    if kind == "native_int":
        lhs, rhs = value_from_dict(payload["lhs"]), value_from_dict(payload["rhs"])
        if not isinstance(lhs, (Const, IntAtom)) or not isinstance(rhs, (Const, IntAtom)):
            raise ValueError("native integer relation requires integer atoms/constants")
        return NativeIntComparison(str(payload["op"]), lhs, rhs)
    if kind == "bool_clause":
        literals = tuple(value_from_dict(item) for item in payload["literals"])
        gates = tuple(value_from_dict(item) for item in payload.get("gates", []))
        if not literals or not all(isinstance(item, BoolAtom) for item in (*literals, *gates)):
            raise ValueError("Boolean clause requires Boolean literals")
        return BoolClauseConstraint(literals, gates)
    if kind == "reified_int":
        literal, lhs, rhs = value_from_dict(payload["literal"]), value_from_dict(payload["lhs"]), value_from_dict(payload["rhs"])
        if not isinstance(literal, BoolAtom) or not isinstance(lhs, IntAtom) or not isinstance(rhs, IntAtom):
            raise ValueError("reified integer relation requires Boolean and integer atoms")
        return ReifiedIntRelation(literal, str(payload["op"]), lhs, rhs)
    if kind == "aggregate":
        rhs = value_from_dict(payload["rhs"])
        if not isinstance(rhs, (Const, IntAtom)):
            raise ValueError("aggregate comparison requires integer atom/constant RHS")
        return AggregateComparison(str(payload["aggregate"]), tuple(int(index) for index in payload["indices"]), str(payload["op"]), rhs)
    if kind == "enum":
        return EnumComparison(int(payload["index"]), str(payload["op"]), str(payload["choice"]))
    raise ValueError(f"Unknown constraint kind: {kind!r}")


@dataclass(frozen=True)
class Case:
    bool_count: int
    int_domains: tuple[tuple[int, int], ...]
    constraints: tuple[Constraint, ...]
    enum_choices: tuple[tuple[str, ...], ...] = ()

    def build(self) -> tuple[Model, list, list, list]:
        model = Model()
        bools = [model.bool(f"b{index}") for index in range(self.bool_count)]
        ints = [model.int(f"i{index}", lb, ub) for index, (lb, ub) in enumerate(self.int_domains)]
        enums = [model.enum(f"e{index}", choices=choices) for index, choices in enumerate(self.enum_choices)]
        return model, bools, ints, enums

    def to_dict(self) -> dict[str, Any]:
        return {
            "bool_count": self.bool_count,
            "int_domains": [list(domain) for domain in self.int_domains],
            "constraints": [constraint.to_dict() for constraint in self.constraints],
            "enum_choices": [list(choices) for choices in self.enum_choices],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Case":
        domains = tuple((int(lb), int(ub)) for lb, ub in payload["int_domains"])
        enum_choices = tuple(tuple(str(choice) for choice in choices) for choices in payload.get("enum_choices", []))
        return cls(int(payload["bool_count"]), domains, tuple(constraint_from_dict(c) for c in payload["constraints"]), enum_choices)
