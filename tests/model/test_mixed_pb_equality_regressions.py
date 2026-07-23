"""Regression coverage for equality between PB-compatible operands.

Every pair below is fixed to equal numeric values.  Equality must therefore be
satisfiable and inequality must be unsatisfiable, independently of operand
order or the expression wrapper used to represent the value.
"""

from __future__ import annotations

import pytest

from hermax.model import ClauseGroup, Literal, Model, PBConstraint


def _equal_operands(kind: str):
    m = Model()
    x = m.bool("x")
    i = m.int("i", 0, 2)

    # Interpret Boolean literals as 0/1 and pin both base values to zero.
    m &= ~x
    m &= i == 0

    operands = {
        "literal": x,
        "intvar": i,
        "term": 1 * x,
        "pbexpr": x + 0,
        "lazy": i.scale(1),
        "constant": 0,
    }
    lhs_name, rhs_name = kind.split("/")
    return m, operands[lhs_name], operands[rhs_name]


_MIXED_EQUALITY_PAIRS = [
    "literal/intvar",
    "intvar/literal",
    "literal/term",
    "term/literal",
    "literal/pbexpr",
    "pbexpr/literal",
    "literal/lazy",
    "lazy/literal",
    "literal/constant",
    "term/constant",
    "intvar/term",
    "intvar/pbexpr",
    "intvar/lazy",
]


@pytest.mark.parametrize("kind", _MIXED_EQUALITY_PAIRS)
@pytest.mark.parametrize("op", ["==", "!="])
def test_mixed_pb_equality_and_inequality_are_constraints_with_correct_semantics(kind, op):
    m, lhs, rhs = _equal_operands(kind)
    constraint = lhs == rhs if op == "==" else lhs != rhs

    # A modelling comparison must never silently become a Python truth value.
    assert isinstance(constraint, (Literal, ClauseGroup, PBConstraint))

    m &= constraint
    assert m.solve().ok is (op == "==")


@pytest.mark.parametrize("op", ["==", "!="])
def test_literal_intvar_equality_rejects_cross_model_operands(op):
    m1 = Model()
    m2 = Model()
    x = m1.bool("x")
    i = m2.int("i", 0, 2)

    with pytest.raises(ValueError, match="different models"):
        _ = x == i if op == "==" else x != i
