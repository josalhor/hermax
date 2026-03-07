from __future__ import annotations

import pytest

from hermax.model import Model


def _solve_status(m: Model) -> str:
    return m.solve().status


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal result, got {r.status!r}"
    return r


def test_int_scale_returns_lazy_object_with_expected_bounds_positive():
    m = Model()
    x = m.int("x", 0, 10)
    y = x.scale(3)
    assert y.lb == 0
    assert y.ub == 28  # values 0..27


def test_int_scale_returns_lazy_object_with_expected_bounds_negative_domain():
    m = Model()
    x = m.int("x", -5, 6)  # -5..5
    y = x.scale(2)
    assert y.lb == -10
    assert y.ub == 11  # values -10..10


@pytest.mark.parametrize("bad", [True, False, 0, -1, -3])
def test_int_scale_rejects_nonpositive_factor(bad):
    m = Model()
    x = m.int("x", 0, 10)
    with pytest.raises(ValueError):
        _ = x.scale(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [1.5, "2", None])
def test_int_scale_rejects_non_integer_factor_type(bad):
    m = Model()
    x = m.int("x", 0, 10)
    with pytest.raises(TypeError):
        _ = x.scale(bad)  # type: ignore[arg-type]


def test_int_scale_is_holding_tank_and_does_not_mutate_model_until_used():
    m = Model()
    x = m.int("x", 0, 10)
    hard_before = len(m._hard)
    top_before = m._top_id()
    s = x.scale(3)
    assert m._hard == m._hard[:hard_before]
    assert len(m._hard) == hard_before
    assert m._top_id() == top_before
    assert len(m._pending_literal_defs) == 0
    # explicit workhorse mutates
    y = m.scale(x, 3, name="y")
    assert y.lb == 0 and y.ub == 28
    assert m._top_id() > top_before
    assert len(m._hard) > hard_before


def test_model_scale_accepts_lazy_input_and_chains():
    m = Model()
    x = m.int("x", 0, 20)
    y = m.scale(x.scale(2), 3, name="y")
    m &= (x == 4)
    m &= (y == 24)
    assert _solve_status(m) != "unsat"


@pytest.mark.parametrize("factor", [1, 2, 3, 4, 5])
def test_model_scale_exactness_exhaustive_small_positive(factor):
    for xv in range(0, 8):
        m = Model()
        x = m.int("x", 0, 8)
        y = m.scale(x, factor, name="y")
        m &= (x == xv)
        m &= (y == xv * factor)
        assert _solve_status(m) != "unsat", (factor, xv)


@pytest.mark.parametrize("factor", [2, 3, 4])
def test_model_scale_exactness_exhaustive_small_negative_domain(factor):
    for xv in range(-4, 5):
        m = Model()
        x = m.int("x", -4, 5)
        y = m.scale(x, factor, name="y")
        m &= (x == xv)
        m &= (y == xv * factor)
        assert _solve_status(m) != "unsat", (factor, xv)


@pytest.mark.parametrize("factor", [2, 3, 5])
def test_model_scale_partition_property_for_exact_values(factor):
    m = Model()
    x = m.int("x", 0, 9)
    y = m.scale(x, factor, name="y")
    for xv in range(0, 9):
        mm = Model()
        xx = mm.int("x", 0, 9)
        yy = mm.scale(xx, factor, name="y")
        mm &= (xx == xv)
        mm &= (yy == xv * factor)
        assert _solve_status(mm) != "unsat"
        wrong = xv * factor + 1
        if wrong < yy.ub:
            mm2 = Model()
            xx2 = mm2.int("x", 0, 9)
            yy2 = mm2.scale(xx2, factor, name="y")
            mm2 &= (xx2 == xv)
            mm2 &= (yy2 == wrong)
            assert _solve_status(mm2) == "unsat"


def test_int_scale_triggers_realization_when_used_in_constraint():
    m = Model()
    x = m.int("x", 0, 10)
    y = x.scale(3)
    hard_before = len(m._hard)
    m &= (y == 6)
    assert len(m._hard) > hard_before
    m &= (x == 2)
    assert _solve_status(m) != "unsat"


def test_int_scale_composes_in_pb_constraint_via_lazy_realization():
    m = Model()
    x = m.int("x", 0, 10)
    y = x.scale(3)
    m &= (x == 2)
    m &= (y + 1 <= 7)
    assert _solve_status(m) != "unsat"

    m2 = Model()
    x2 = m2.int("x", 0, 10)
    y2 = x2.scale(3)
    m2 &= (x2 == 2)
    m2 &= (y2 + 1 <= 6)
    assert _solve_status(m2) == "unsat"


def test_model_scale_can_be_added_to_objective_and_realizes():
    m = Model()
    x = m.int("x", 0, 6)
    y = x.scale(2)
    m.obj[1] += y
    r = _solve_ok(m)
    assert r[x] == 0


@pytest.mark.parametrize("op", ["<=", "<", ">=", ">", "=="])
def test_pb_fastpath_scaled_intvar_relations_match_truth_table_same_domain(op):
    for xv in range(0, 6):
        for yv in range(0, 18):
            m = Model()
            x = m.int("x", 0, 6)
            y = m.int("y", 0, 18)
            if op == "<=":
                c = (x * 3 <= y)
                truth = (xv * 3) <= yv
            elif op == "<":
                c = (x * 3 < y)
                truth = (xv * 3) < yv
            elif op == ">=":
                c = (x * 3 >= y)
                truth = (xv * 3) >= yv
            elif op == ">":
                c = (x * 3 > y)
                truth = (xv * 3) > yv
            else:
                c = (x * 3 == y)
                truth = (xv * 3) == yv
            m &= c
            m &= (x == xv)
            m &= (y == yv)
            sat = _solve_status(m) != "unsat"
            assert sat == truth, (op, xv, yv)


def test_pb_fastpath_scaled_intvar_relations_bypass_pb_and_card_encoders():
    import hermax.model as hm

    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 30)

    orig_pb_leq = hm.PBEnc.leq
    orig_pb_geq = hm.PBEnc.geq
    orig_pb_eq = hm.PBEnc.equals
    orig_card_atmost = hm.CardEnc.atmost
    orig_card_atleast = hm.CardEnc.atleast
    orig_card_eq = hm.CardEnc.equals

    def bomb(*args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("PB/Card encoder should not be used for scaled IntVar fastpath")

    hm.PBEnc.leq = bomb
    hm.PBEnc.geq = bomb
    hm.PBEnc.equals = bomb
    hm.CardEnc.atmost = bomb
    hm.CardEnc.atleast = bomb
    hm.CardEnc.equals = bomb
    try:
        m &= (x * 3 + 1 <= y)
        m &= (x == 4)
        m &= (y == 13)
        assert _solve_status(m) != "unsat"
    finally:
        hm.PBEnc.leq = orig_pb_leq
        hm.PBEnc.geq = orig_pb_geq
        hm.PBEnc.equals = orig_pb_eq
        hm.CardEnc.atmost = orig_card_atmost
        hm.CardEnc.atleast = orig_card_atleast
        hm.CardEnc.equals = orig_card_eq


def test_weighted_pb_still_uses_pb_encoder_when_not_scaled_intvar_pattern():
    import hermax.model as hm

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    x = m.int("x", 0, 10)
    called = {"pb": 0}
    orig_pb_leq = hm.PBEnc.leq

    def wrapped(*args, **kwargs):
        called["pb"] += 1
        return orig_pb_leq(*args, **kwargs)

    hm.PBEnc.leq = wrapped
    try:
        # One IntVar + two booleans is not covered by the specialized fast paths.
        m &= (2 * a + b + 3 * x <= 20)
        assert called["pb"] >= 1
    finally:
        hm.PBEnc.leq = orig_pb_leq
