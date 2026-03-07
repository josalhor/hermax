from __future__ import annotations

import pytest

from hermax.model import Model


def _solve_status(m: Model) -> str:
    return m.solve().status


def test_int_floordiv_returns_lazy_divexpr_with_expected_bounds_positive_domain():
    m = Model()
    x = m.int("x", 0, 10)  # 0..9
    q = x // 3
    assert q.lb == 0
    assert q.ub == 4  # values 0..3


def test_int_floordiv_returns_intvar_with_expected_bounds_negative_domain():
    m = Model()
    x = m.int("x", -5, 6)  # -5..5
    q = x // 2
    assert q.lb == (-5) // 2
    assert q.ub == (5 // 2) + 1
    assert q.lb == -3
    assert q.ub == 3


@pytest.mark.parametrize("bad", [0, -1, -5, True])
def test_int_floordiv_rejects_nonpositive_divisor(bad):
    m = Model()
    x = m.int("x", 0, 10)
    with pytest.raises(ValueError):
        _ = x // bad  # type: ignore[operator]


@pytest.mark.parametrize("bad", [1.5, "2", None])
def test_int_floordiv_rejects_non_integer_divisor_type(bad):
    m = Model()
    x = m.int("x", 0, 10)
    with pytest.raises(TypeError):
        _ = x // bad  # type: ignore[operator]


def test_int_floordiv_is_holding_tank_and_does_not_mutate_model_until_used():
    m = Model()
    x = m.int("x", 0, 10)
    hard_before = len(m._hard)
    top_before = m._top_id()

    q = x // 3

    assert m._top_id() == top_before
    assert len(m._hard) == hard_before
    assert len(m._pending_literal_defs) == 0

    # Materializing through the explicit Model API performs the actual work.
    q_real = m.floor_div(x, 3, name="q")
    span = q_real.ub - q_real.lb
    assert m._top_id() - top_before == max(0, span - 1)
    assert len(m._hard) - hard_before == max(0, span - 2)
    assert len(m._pending_literal_defs) >= max(0, len(q_real._threshold_lits) - 1)


@pytest.mark.parametrize("divisor", [1, 2, 3, 5])
def test_int_floordiv_exactness_exhaustive_small_positive(divisor):
    m = Model()
    x = m.int("x", 0, 10)
    q = x // divisor
    for xv in range(x.lb, x.ub):
        expected = xv // divisor
        mm = Model()
        xx = mm.int("x", 0, 10)
        qq = xx // divisor
        mm &= (xx == xv)
        mm &= (qq == expected)
        assert _solve_status(mm) != "unsat", (divisor, xv, expected)
        mm_bad = Model()
        xxb = mm_bad.int("x", 0, 10)
        qqb = xxb // divisor
        mm_bad &= (xxb == xv)
        wrong = expected + 1 if (expected + 1) < qqb.ub else expected - 1
        if wrong < qqb.lb:
            continue  # singleton quotient-domain case
        mm_bad &= (qqb == wrong)
        assert _solve_status(mm_bad) == "unsat", (divisor, xv, expected, wrong)


@pytest.mark.parametrize("divisor", [2, 3, 4])
def test_int_floordiv_exactness_exhaustive_small_negative_domain(divisor):
    for xv in range(-6, 7):
        m = Model()
        x = m.int("x", -6, 7)
        q = x // divisor
        m &= (x == xv)
        m &= (q == (xv // divisor))
        assert _solve_status(m) != "unsat", (divisor, xv, xv // divisor)


def test_int_floordiv_composes_in_pb_constraint():
    m = Model()
    x = m.int("x", 0, 20)
    q = x // 4
    m &= (x == 13)
    m &= (q + 2 <= 5)  # 13//4 = 3; 3+2 <= 5
    assert _solve_status(m) != "unsat"

    m2 = Model()
    x2 = m2.int("x", 0, 20)
    q2 = x2 // 4
    m2 &= (x2 == 13)
    m2 &= (q2 + 2 <= 4)
    assert _solve_status(m2) == "unsat"


def test_int_floordiv_chain_is_exact():
    m = Model()
    x = m.int("x", 0, 50)
    q = x // 5
    r = q // 2
    m &= (x == 37)
    m &= (r == ((37 // 5) // 2))
    assert _solve_status(m) != "unsat"


def test_int_floordiv_triggers_deferred_links_when_used():
    m = Model()
    x = m.int("x", 0, 12)
    q = x // 3
    hard_before = len(m._hard)
    m &= (q == 2)
    # Using q should realize some deferred division links.
    assert len(m._hard) > hard_before
    m &= (x == 7)
    assert _solve_status(m) != "unsat"


def test_model_floor_div_eager_workhorse_matches_lazy_operator_semantics():
    m = Model()
    x = m.int("x", 0, 12)
    q_lazy = x // 3
    q_eager = m.floor_div(x, 3, name="q_eager")
    m &= (x == 7)
    m &= (q_lazy == 2)
    m &= (q_eager == 2)
    assert _solve_status(m) != "unsat"


def test_int_floordiv_value_partition_property():
    m = Model()
    x = m.int("x", 0, 12)
    q = x // 3

    # q == 2 should allow exactly x in {6,7,8}
    for xv in range(0, 12):
        mm = Model()
        xx = mm.int("x", 0, 12)
        qq = xx // 3
        mm &= (qq == 2)
        mm &= (xx == xv)
        status = _solve_status(mm)
        expect_sat = xv in {6, 7, 8}
        assert (status != "unsat") == expect_sat, xv


def test_int_floordiv_respects_model_ownership():
    m1 = Model()
    x1 = m1.int("x", 0, 10)
    q1 = x1 // 2

    m2 = Model()
    y2 = m2.int("y", 0, 10)
    with pytest.raises(ValueError):
        m2 &= (q1 == y2)
