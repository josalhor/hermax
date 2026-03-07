from __future__ import annotations

import pytest

from hermax.model import ClauseGroup, IntVar, Literal, Model


def _solve_status(m: Model) -> str:
    return m.solve().status


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal result, got {r.status!r}"
    return r


def test_in_range_returns_literal_and_is_lazy_holding_tank():
    m = Model()
    x = m.int("x", 0, 10)
    hard_before = len(m._hard)
    top_before = m._top_id()
    b = x.in_range(2, 5)
    assert isinstance(b, Literal)
    assert len(m._hard) == hard_before
    assert m._top_id() > top_before  # indicator literal allocated
    # Definition should be deferred, not materialized yet.
    assert b.id in m._pending_literal_defs


@pytest.mark.parametrize("bad_start", [1.5, "1", None, True])
def test_in_range_rejects_bad_start_type(bad_start):
    m = Model()
    x = m.int("x", 0, 5)
    with pytest.raises(TypeError):
        x.in_range(bad_start, 3)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_end", [1.5, "1", None, False])
def test_in_range_rejects_bad_end_type(bad_end):
    m = Model()
    x = m.int("x", 0, 5)
    with pytest.raises(TypeError):
        x.in_range(1, bad_end)  # type: ignore[arg-type]


def test_in_range_empty_requested_interval_returns_false_constant():
    m = Model()
    x = m.int("x", 0, 5)
    b = x.in_range(4, 3)
    assert b is m._get_bool_constant_literal(False)


def test_in_range_no_overlap_returns_false_constant():
    m = Model()
    x = m.int("x", 10, 20)
    assert x.in_range(0, 9) is m._get_bool_constant_literal(False)
    assert x.in_range(20, 30) is m._get_bool_constant_literal(False)


def test_in_range_full_domain_returns_true_constant():
    m = Model()
    x = m.int("x", 10, 20)  # values 10..19
    assert x.in_range(0, 100) is m._get_bool_constant_literal(True)
    assert x.in_range(10, 19) is m._get_bool_constant_literal(True)


def test_in_range_singleton_reuses_exact_equality_indicator():
    m = Model()
    x = m.int("x", 0, 10)
    b = x.in_range(4, 4)
    e = (x == 4)
    assert isinstance(b, Literal)
    assert b is e


def test_in_range_boundary_reduces_to_scalar_comparison_literals():
    m = Model()
    x = m.int("x", 0, 10)
    left = x.in_range(0, 3)   # x <= 3
    right = x.in_range(7, 9)  # x >= 7
    assert left is (x <= 3)
    assert right is (x >= 7)


def test_in_range_exact_semantics_exhaustive_small_domain():
    for xv in range(-2, 6):
        truth = (1 <= xv <= 3)

        m_in = Model()
        x_in = m_in.int("x", -2, 6)
        b_in = x_in.in_range(1, 3)
        m_in &= (x_in == xv)
        m_in &= b_in
        assert (_solve_status(m_in) != "unsat") is truth

        m_out = Model()
        x_out = m_out.int("x", -2, 6)
        b_out = x_out.in_range(1, 3)
        m_out &= (x_out == xv)
        m_out &= ~b_out
        assert (_solve_status(m_out) != "unsat") is (not truth)


def test_in_range_can_be_enforced_directly():
    m = Model()
    x = m.int("x", 0, 10)
    m &= x.in_range(2, 4)
    m &= (x == 3)
    assert _solve_status(m) != "unsat"

    m2 = Model()
    x2 = m2.int("x", 0, 10)
    m2 &= x2.in_range(2, 4)
    m2 &= (x2 == 5)
    assert _solve_status(m2) == "unsat"


def test_in_range_negation_works_for_not_in_bin():
    m = Model()
    x = m.int("x", 0, 10)
    b = x.in_range(2, 4)
    m &= ~b
    m &= (x == 1)
    assert _solve_status(m) != "unsat"

    m2 = Model()
    x2 = m2.int("x", 0, 10)
    b2 = x2.in_range(2, 4)
    m2 &= ~b2
    m2 &= (x2 == 3)
    assert _solve_status(m2) == "unsat"


def test_in_range_indicator_definition_materializes_when_consumed():
    m = Model()
    x = m.int("x", 0, 10)
    b = x.in_range(2, 5)
    hard_before = len(m._hard)
    m &= b
    assert len(m._hard) > hard_before


def test_in_range_caches_same_interval_literal():
    m = Model()
    x = m.int("x", 0, 10)
    a = x.in_range(2, 5)
    b = x.in_range(2, 5)
    assert a is b


def test_in_range_works_in_histogram_style_counting():
    m = Model()
    xs = m.int_vector("t", length=3, lb=0, ub=6)  # 0..5

    morning = [x.in_range(0, 1) for x in xs]
    afternoon = [x.in_range(2, 3) for x in xs]
    evening = [x.in_range(4, 5) for x in xs]

    # Exactly one variable in each bin.
    m &= (sum(morning) == 1)
    m &= (sum(afternoon) == 1)
    m &= (sum(evening) == 1)

    # Pick one concrete witness to make the solve deterministic.
    m &= (xs[0] == 0)
    m &= (xs[1] == 2)
    m &= (xs[2] == 4)
    r = _solve_ok(m)
    assert r[morning[0]] is True and r[morning[1]] is False and r[morning[2]] is False
    assert r[afternoon[1]] is True
    assert r[evening[2]] is True


def test_in_range_can_be_used_inside_clausegroup_only_if_pipeline():
    m = Model()
    x = m.int("x", 0, 10)
    gate = m.bool("g")
    target = ClauseGroup(m, [])
    target &= x.in_range(3, 6)
    m &= target.only_if(gate)
    m &= gate
    m &= (x == 5)
    assert _solve_status(m) != "unsat"
