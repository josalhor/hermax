from __future__ import annotations

import pytest

import hermax.model as hm
from hermax.model import Model, PBExpr, sum_expr


def test_sum_expr_matches_python_sum_on_numeric_iterables() -> None:
    assert sum_expr([]) == sum([])
    assert sum_expr([], 7) == sum([], 7)
    assert sum_expr([1, 2, 3, 4]) == sum([1, 2, 3, 4])
    assert sum_expr([True, False, True], 3) == sum([True, False, True], 3)


def test_sum_expr_infers_model_and_builds_pbexpr() -> None:
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    expr = sum_expr([a, b, 2])
    assert isinstance(expr, PBExpr)
    assert expr._model is m
    assert expr.constant == 2
    assert len(expr.terms) == 2
    assert {t.literal.id for t in expr.terms} == {a.id, b.id}


def test_sum_expr_rejects_mixed_models() -> None:
    m1 = Model()
    m2 = Model()
    a = m1.bool("a")
    b = m2.bool("b")
    with pytest.raises(ValueError, match="different models"):
        _ = sum_expr([a, b])


def test_sum_expr_fast_path_avoids_pbexpr_merge(monkeypatch) -> None:
    m = Model()
    lits = [m.bool(f"x{i}") for i in range(64)]

    def _boom(*_args, **_kwargs):
        raise AssertionError("PBExpr._merge should not be used by sum_expr fast path")

    monkeypatch.setattr(hm.PBExpr, "_merge", _boom)

    expr = sum_expr(lits)
    assert isinstance(expr, PBExpr)
    assert len(expr.terms) == len(lits)

    with pytest.raises(AssertionError, match="fast path"):
        _ = sum(lits)

