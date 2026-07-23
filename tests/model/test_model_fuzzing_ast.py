"""Finite unit coverage for semantic-fuzzer AST emission paths.

These are fixed AST cases, not randomized or long-running fuzzing.
"""

import random

import pytest

from tests.model_fuzzing.ast import (
    AggregateComparison,
    BoolAtom,
    BoolClauseConstraint,
    Case,
    Comparison,
    Const,
    EnumComparison,
    IntAtom,
    Linear,
    NativeIntComparison,
    ReifiedIntRelation,
    SequenceExpr,
)
from tests.model_fuzzing.grammar import Grammar
from tests.model_fuzzing.oracle import check_case


def _pb_comparison(*, mode="only_if", gates=(), antecedent=(), target=None):
    return Comparison(
        ">=",
        Linear(0, (IntAtom(0), BoolAtom(0))),
        Linear(1, ()),
        gates=gates,
        mode=mode,
        antecedent=antecedent,
        target=target,
    )


def test_semantic_fuzzer_ast_emits_supported_implication_forms():
    cases = [
        Case(2, ((0, 1),), (_pb_comparison(gates=(BoolAtom(0), BoolAtom(1, True))),)),
        Case(2, ((0, 1),), (_pb_comparison(mode="literal_implies", antecedent=(BoolAtom(0),)),)),
        Case(2, ((0, 1),), (_pb_comparison(mode="clause_implies", antecedent=(BoolAtom(0), BoolAtom(1, True))),)),
        Case(2, ((0, 1),), (_pb_comparison(mode="pb_implies", target=BoolAtom(1)),)),
    ]

    for case in cases:
        assert check_case(case) is None


def test_semantic_fuzzer_ast_reads_legacy_single_gate_artifacts():
    payload = {
        "op": ">=",
        "lhs": {"kind": "linear", "constant": 0, "terms": [{"kind": "int", "index": 0}]},
        "rhs": {"kind": "linear", "constant": 0, "terms": []},
        "gate": {"kind": "bool", "index": 0, "negated": False},
    }
    comparison = Comparison.from_dict(payload)
    assert comparison.mode == "only_if"
    assert comparison.gates == (BoolAtom(0),)


def test_semantic_fuzzer_depth_is_a_bounded_flat_expression_width():
    grammar = Grammar(random.Random(1337), max_width=4)
    values = [grammar._value(bool_count=2, int_count=1) for _ in range(100)]

    assert any(not isinstance(value, SequenceExpr) for value in values)
    assert any(isinstance(value, SequenceExpr) and len(value.steps) + 1 == 4 for value in values)
    assert all(not isinstance(value, SequenceExpr) or 2 <= len(value.steps) + 1 <= 4 for value in values)
    assert all(
        not isinstance(value, SequenceExpr)
        or not isinstance(value.start, Const)
        or any(not isinstance(step_value, Const) for _op, step_value in value.steps)
        for value in values
    )


def test_semantic_fuzzer_avoids_invalid_direct_scalar_equality():
    grammar = Grammar(random.Random(2027), max_width=2)
    rhs = SequenceExpr(Const(0), (("+", Const(2)),))
    domains = ((-2, 0),)

    sanitized = grammar._sanitize_scalar_equality_rhs(BoolAtom(0), "==", rhs, domains)
    assert Grammar._constant_value(sanitized) is None

    valid = grammar._sanitize_scalar_equality_rhs(BoolAtom(0), "!=", Const(1), domains)
    assert valid == Const(1)

    int_sanitized = grammar._sanitize_scalar_equality_rhs(IntAtom(0), "==", rhs, domains)
    assert Grammar._constant_value(int_sanitized) is None

    int_valid = grammar._sanitize_scalar_equality_rhs(IntAtom(0), "!=", Const(-2), domains)
    assert int_valid == Const(-2)


def test_semantic_fuzzer_ast_emits_native_constraint_families():
    cases = [
        Case(1, ((-1, 1), (0, 2)), (NativeIntComparison("==", IntAtom(0), Const(0)),)),
        Case(1, ((-1, 1), (0, 2)), (NativeIntComparison("<=", Const(0), IntAtom(0)),)),
        Case(2, ((0, 2), (0, 2)), (BoolClauseConstraint((BoolAtom(0), BoolAtom(1, True)), (BoolAtom(0, True),)),)),
        Case(1, ((0, 2), (0, 2)), (ReifiedIntRelation(BoolAtom(0), "<=", IntAtom(0), IntAtom(1)),)),
        Case(1, ((0, 2), (0, 2)), (AggregateComparison("min", (0, 1), ">=", Const(0)),)),
        Case(1, ((0, 2), (0, 2)), (AggregateComparison("max", (0, 1), "<=", Const(2)),)),
        Case(1, ((0, 1),), (EnumComparison(0, "!=", "red"),), (("red", "green"),)),
    ]

    for case in cases:
        assert check_case(case) is None


def test_semantic_fuzzer_reified_integer_relations_are_native_only():
    grammar = Grammar(random.Random(2026), max_width=2)

    assert {
        grammar._reified_relation(bool_count=2, int_count=2).op
        for _ in range(100)
    } <= {"==", "<", "<=", ">", ">="}

    with pytest.raises(ValueError, match="Unsupported reified integer relation"):
        ReifiedIntRelation(BoolAtom(0), "!=", IntAtom(0), IntAtom(1))


def test_semantic_fuzzer_aggregate_constants_use_materialized_aggregate_domain():
    domains = ((0, 3), (-2, -1))

    assert Grammar._aggregate_domain("max", (0, 1), domains) == (0, 3)
    assert Grammar._aggregate_domain("min", (0, 1), domains) == (-2, -1)
