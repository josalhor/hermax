"""Exhaustive semantic oracle for generated model cases."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Iterator

from .ast import Case, Environment


@dataclass(frozen=True)
class Mismatch:
    kind: str
    environment: dict[str, int]
    expected_sat: bool
    actual_sat: bool | None
    detail: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "environment": self.environment,
            "expected_sat": self.expected_sat,
            "actual_sat": self.actual_sat,
            "detail": self.detail,
        }


def environments(case: Case) -> Iterator[dict[str, Any]]:
    names = [
        *(f"b{index}" for index in range(case.bool_count)),
        *(f"i{index}" for index in range(len(case.int_domains))),
        *(f"e{index}" for index in range(len(case.enum_choices))),
    ]
    domains = [
        *(range(2) for _ in range(case.bool_count)),
        *(range(lb, ub + 1) for lb, ub in case.int_domains),
        *case.enum_choices,
    ]
    for values in product(*domains):
        yield dict(zip(names, values, strict=True))


def expected_sat(case: Case, env: Environment) -> bool:
    return all(constraint.evaluate(env) for constraint in case.constraints)


def check_case(case: Case) -> Mismatch | None:
    """Return the first disagreement between the AST semantics and Hermax."""
    for env in environments(case):
        expected = expected_sat(case, env)
        try:
            model, bools, ints, enums = case.build()
            for index, literal in enumerate(bools):
                model &= literal if env[f"b{index}"] else ~literal
            for index, variable in enumerate(ints):
                model &= variable == env[f"i{index}"]
            for index, variable in enumerate(enums):
                model &= variable == env[f"e{index}"]
            for constraint in case.constraints:
                model &= constraint.emit(bools, ints, model=model, enums=enums)
            result = model.solve()
        except Exception as exc:  # A generated, documented operation must compile cleanly.
            return Mismatch("exception", dict(env), expected, None, f"{type(exc).__name__}: {exc}")

        actual = bool(result.ok)
        if actual != expected:
            kind = "unsound" if actual else "incomplete"
            return Mismatch(kind, dict(env), expected, actual, "solver status disagrees with AST semantics")

        if actual:
            for index, literal in enumerate(bools):
                if int(result[literal]) != env[f"b{index}"]:
                    return Mismatch("decode", dict(env), expected, actual, f"b{index} did not retain its pinned value")
            for index, variable in enumerate(ints):
                if int(result[variable]) != env[f"i{index}"]:
                    return Mismatch("decode", dict(env), expected, actual, f"i{index} did not retain its pinned value")
            for index, variable in enumerate(enums):
                if result[variable] != env[f"e{index}"]:
                    return Mismatch("decode", dict(env), expected, actual, f"e{index} did not retain its pinned value")
    return None
