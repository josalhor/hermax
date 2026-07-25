"""Regression coverage for strict formula-comparison boundaries."""

from __future__ import annotations

import pytest

from hermax.model import Model, PBConstraint


_ORDERING = {
    "<=": lambda lhs, rhs: lhs <= rhs,
    "<": lambda lhs, rhs: lhs < rhs,
    ">=": lambda lhs, rhs: lhs >= rhs,
    ">": lambda lhs, rhs: lhs > rhs,
}


@pytest.mark.parametrize("op", ["==", "!="])
@pytest.mark.parametrize(
    "formula_kind",
    ["int_inequality", "clause", "clausegroup", "deferred_clausegroup", "pb", "gated_pb"],
)
def test_literal_rejects_non_native_formula_comparison(formula_kind, op):
    m = Model()
    indicator = m.bool("indicator")
    a = m.bool("a")
    b = m.bool("b")
    x = m.int("x", 0, 1)
    y = m.int("y", 0, 1)
    formula = {
        "int_inequality": x != y,
        "clause": a | b,
        "clausegroup": a & b,
        "deferred_clausegroup": (x + a == 1).implies(indicator),
        "pb": x + a >= 1,
        "gated_pb": (x >= 1).only_if(a),
    }[formula_kind]

    with pytest.raises(TypeError, match="(?i)flatten the formula"):
        _ = indicator == formula if op == "==" else indicator != formula


def test_literal_inequality_rejects_identity_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    with pytest.raises(TypeError, match="(?i)flatten the formula"):
        _ = a != b


@pytest.mark.parametrize("op", ["==", "!="])
@pytest.mark.parametrize("lhs_kind", ["intvar", "pbexpr", "lazy_aggregate"])
def test_arithmetic_expressions_reject_constraint_comparison(lhs_kind, op):
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    x = m.int("x", 0, 1)
    target = a | b
    lhs = {
        "intvar": x,
        "pbexpr": x + a,
        "lazy_aggregate": m.max([x, x]),
    }[lhs_kind]

    with pytest.raises(TypeError, match="Unsupported.*comparison"):
        _ = lhs == target if op == "==" else lhs != target


@pytest.mark.parametrize("op", ["==", "!="])
@pytest.mark.parametrize("domain_kind", ["enum", "int_set", "int_vector"])
def test_domain_objects_reject_incompatible_model_operands(domain_kind, op):
    m = Model()
    literal = m.bool("literal")
    lhs = {
        "enum": m.enum("color", ["red", "green"]),
        "int_set": m.int_set("selected", lb=0, ub=1),
        "int_vector": m.int_vector("items", length=2, lb=0, ub=1),
    }[domain_kind]

    with pytest.raises(TypeError, match="Unsupported.*comparison|Vector equality"):
        _ = lhs == literal if op == "==" else lhs != literal


def test_literal_equality_with_native_int_relation_remains_supported():
    m = Model()
    indicator = m.bool("indicator")
    x = m.int("x", 0, 1)
    y = m.int("y", 0, 1)

    m &= indicator == (x <= y)
    m &= indicator
    m &= x == 1
    m &= y == 0

    assert not m.solve().ok


@pytest.mark.parametrize("negated", [False, True])
@pytest.mark.parametrize("op", ["<=", "<", ">=", ">"])
@pytest.mark.parametrize("constant", [-1, 0, 1, 2])
def test_literal_ordering_is_a_numeric_pb_comparison(negated, op, constant):
    for bool_value in (False, True):
        m = Model()
        boolean = m.bool("boolean")
        literal = ~boolean if negated else boolean
        constraint = _ORDERING[op](literal, constant)

        assert isinstance(constraint, PBConstraint)
        m &= constraint
        m &= boolean if bool_value else ~boolean

        literal_value = int(not bool_value) if negated else int(bool_value)
        assert m.solve().ok is _ORDERING[op](literal_value, constant)


@pytest.mark.parametrize("negated", [False, True])
@pytest.mark.parametrize("rhs_kind", ["intvar", "pbexpr", "lazy_aggregate"])
def test_literal_ordering_accepts_model_bound_pb_operands(negated, rhs_kind):
    for bool_value in (False, True):
        for int_value in (0, 1):
            m = Model()
            boolean = m.bool("boolean")
            literal = ~boolean if negated else boolean
            integer = m.int("integer", 0, 1)
            rhs = {
                "intvar": integer,
                "pbexpr": integer + 1,
                "lazy_aggregate": m.max([integer, integer]),
            }[rhs_kind]
            constraint = literal >= rhs

            assert isinstance(constraint, PBConstraint)
            m &= constraint
            m &= boolean if bool_value else ~boolean
            m &= integer == int_value

            literal_value = int(not bool_value) if negated else int(bool_value)
            rhs_value = int_value + 1 if rhs_kind == "pbexpr" else int_value
            assert m.solve().ok is (literal_value >= rhs_value)


@pytest.mark.parametrize("negated", [False, True])
@pytest.mark.parametrize("constant", [-1, 2])
@pytest.mark.parametrize("op, expected_when_enabled", [("==", "unsat"), ("!=", "sat")])
@pytest.mark.parametrize("gate_enabled", [False, True])
def test_literal_exact_comparison_outside_boolean_domain_is_lazy_and_gateable(
    negated, constant, op, expected_when_enabled, gate_enabled
):
    m = Model()
    boolean = m.bool("boolean")
    literal = ~boolean if negated else boolean
    gate = m.bool("gate")
    next_id_before = m._next_id
    hard_before = len(m._hard)

    comparison = literal == constant if op == "==" else literal != constant
    assert m._next_id == next_id_before
    assert len(m._hard) == hard_before
    assert m._const_lits == {}

    m &= comparison.only_if(gate)
    assert m._next_id == next_id_before
    assert m._const_lits == {}
    m &= gate if gate_enabled else ~gate
    expected = expected_when_enabled if gate_enabled else "sat"
    assert m.solve().status == expected
    assert m._const_lits == {}


def test_out_of_domain_boolean_order_comparison_is_gateable():
    for gate_enabled, expected in ((False, "sat"), (True, "unsat")):
        m = Model()
        a = m.bool("a")
        gate = m.bool("gate")

        m &= (a >= 2).only_if(gate)
        m &= gate if gate_enabled else ~gate
        assert m.solve().status == expected
