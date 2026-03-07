from __future__ import annotations

import pytest

from hermax.model import Model


def test_model_exposes_tier_objective_proxy():
    m = Model()
    assert hasattr(m, "tier_obj")


def test_tier_obj_tuple_indexing_requires_two_items():
    m = Model()
    with pytest.raises((TypeError, ValueError)):
        _ = m.tier_obj[0]


def test_tier_obj_tuple_indexing_rejects_negative_tier_index():
    m = Model()
    a = m.bool("a")
    with pytest.raises((TypeError, ValueError)):
        m.tier_obj[-1, 1] += a


def test_tier_obj_tuple_indexing_rejects_non_integer_tier_index():
    m = Model()
    a = m.bool("a")
    with pytest.raises((TypeError, ValueError)):
        m.tier_obj[0.5, 1] += a  # type: ignore[index]


def test_tier_obj_tuple_indexing_rejects_non_positive_weight():
    m = Model()
    a = m.bool("a")
    with pytest.raises((TypeError, ValueError)):
        m.tier_obj[0, 0] += a
    with pytest.raises((TypeError, ValueError)):
        m.tier_obj[0, -1] += a


def test_tier_obj_tuple_indexing_rejects_non_integer_weight_without_precision():
    m = Model()
    a = m.bool("a")
    with pytest.raises((TypeError, ValueError)):
        m.tier_obj[0, 1.5] += a  # type: ignore[index]


def test_tier_obj_accepts_dynamic_building_from_loop():
    m = Model()
    xs = m.bool_vector("x", length=4)
    for i, x in enumerate(xs):
        m.tier_obj[0, i + 1] += x
    r = m.solve(lex_strategy="incremental")
    assert r.status in {"optimum", "sat"}
    assert r.tier_costs is not None
    assert len(r.tier_costs) == 1


def test_tier_obj_set_lexicographic_declares_tiers_in_order():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.tier_obj.set_lexicographic(a, b)
    r = m.solve(lex_strategy="incremental")
    assert r.tier_costs is not None
    assert len(r.tier_costs) == 2


def test_tier_obj_set_lexicographic_replaces_previous_tier_content():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.tier_obj[0, 1] += a
    m.tier_obj.set_lexicographic(b)
    r = m.solve(lex_strategy="incremental")
    assert r.tier_costs is not None
    assert len(r.tier_costs) == 1


def test_tier_obj_clear_removes_all_tiers():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.tier_obj[0, 1] += a
    m.tier_obj[1, 1] += b
    m.tier_obj.clear()
    r = m.solve()
    assert r.tier_costs is None


def test_tier_obj_clear_is_idempotent():
    m = Model()
    m.tier_obj.clear()
    m.tier_obj.clear()
    r = m.solve()
    assert r.tier_costs is None


def test_tier_obj_rejects_cross_model_expression():
    m1 = Model()
    m2 = Model()
    a1 = m1.bool("a1")
    _ = m2.bool("a2")
    with pytest.raises((TypeError, ValueError)):
        m2.tier_obj[0, 1] += a1


def test_tier_obj_rejects_pbconstraint_direct_addition():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    with pytest.raises((TypeError, ValueError)):
        m.tier_obj[0, 1] += (a + b <= 1)


def test_tier_obj_and_obj_are_mutually_exclusive_obj_then_tier():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj[1] += a
    with pytest.raises((TypeError, ValueError)):
        m.tier_obj[0, 1] += b


def test_tier_obj_and_obj_are_mutually_exclusive_tier_then_obj():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.tier_obj[0, 1] += a
    with pytest.raises((TypeError, ValueError)):
        m.obj[1] += b


def test_after_obj_clear_tier_obj_is_allowed():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj[1] += a
    m.obj.clear()
    m.tier_obj[0, 1] += b
    r = m.solve(lex_strategy="incremental")
    assert r.tier_costs is not None


def test_after_tier_obj_clear_flat_obj_is_allowed():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.tier_obj[0, 1] += a
    m.tier_obj.clear()
    m.obj[1] += b
    r = m.solve()
    assert r.cost is not None
    assert r.tier_costs is None


def test_solve_rejects_invalid_lex_strategy_value():
    m = Model()
    with pytest.raises((TypeError, ValueError)):
        m.solve(lex_strategy="weird")


def test_solve_with_lex_strategy_but_no_tiers_behaves_as_normal_solve():
    m = Model()
    a = m.bool("a")
    m &= a
    r = m.solve(lex_strategy="incremental")
    assert r.status == "sat"
    assert r.tier_costs is None


def test_solve_result_has_tier_fields_in_lex_mode():
    m = Model()
    a = m.bool("a")
    m.tier_obj[0, 1] += a
    r = m.solve(lex_strategy="incremental")
    assert hasattr(r, "tier_costs")
    assert hasattr(r, "tier_models")
    assert r.tier_costs is not None


def test_solve_result_tier_fields_are_none_in_non_lex_mode():
    m = Model()
    a = m.bool("a")
    m.obj[1] += a
    r = m.solve()
    assert r.tier_costs is None
    assert r.tier_models is None


def test_tier_obj_supports_objective_precision_floats_when_enabled():
    m = Model()
    m.set_objective_precision(decimals=2)
    a = m.bool("a")
    m.tier_obj[0, 1.25] += a
    r = m.solve(lex_strategy="incremental")
    assert r.tier_costs is not None
    assert len(r.tier_costs) == 1


def test_tier_obj_rejects_float_weight_without_precision():
    m = Model()
    a = m.bool("a")
    with pytest.raises((TypeError, ValueError)):
        m.tier_obj[0, 1.25] += a  # type: ignore[index]

