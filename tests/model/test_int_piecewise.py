from __future__ import annotations

import itertools

import pytest

from hermax.model import Model, PBExpr


def _solve_status(m: Model) -> str:
    return m.solve().status


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok
    return r


def _pw_value(v: int, base: int, steps: dict[int, int]) -> int:
    cur = base
    for t in sorted(steps):
        if v >= t:
            cur = steps[t]
        else:
            break
    return cur


def _domain_vals(x):
    return list(range(x.lb, x.ub))


@pytest.mark.parametrize(
    "base,steps",
    [
        (10, {}),
        (10, {2: 20}),
        (10, {2: 20, 4: 50}),
        (10, {2: 20, 4: 5}),      # non-monotonic down
        (10, {1: 20, 3: 5, 5: 30}),  # oscillating
        (0, {0: 1, 2: 3, 5: -2}),    # includes negatives
    ],
)
def test_piecewise_exactness_exhaustive_small_domain(base, steps):
    m = Model()
    x = m.int("x", 0, 6)
    expr = x.piecewise(base_value=base, steps=steps)
    assert isinstance(expr, PBExpr)

    for xv in _domain_vals(x):
        expected = _pw_value(xv, base, steps)
        m_ok = Model()
        xx = m_ok.int("x", 0, 6)
        ee = xx.piecewise(base_value=base, steps=steps)
        m_ok &= (xx == xv)
        m_ok &= (ee == expected)
        assert _solve_status(m_ok) != "unsat", (xv, expected, base, steps)

        m_bad = Model()
        xb = m_bad.int("x", 0, 6)
        eb = xb.piecewise(base_value=base, steps=steps)
        m_bad &= (xb == xv)
        m_bad &= (eb == expected + 1)
        assert _solve_status(m_bad) == "unsat", (xv, expected, base, steps)


@pytest.mark.parametrize(
    "base,steps",
    [
        (7, {-10: 3}),                   # always-active step folds into base
        (7, {100: 99}),                  # never-active step ignored
        (7, {-10: 3, 100: 99}),          # both
        (7, {-10: 3, 0: 4, 6: 8}),       # threshold at lb
        (7, {6: 8, 50: 100}),            # threshold at ub (inactive)
        (7, {-100: 1, -1: 2, 2: 9}),     # multiple pre-domain changes
    ],
)
def test_piecewise_boundary_thresholds_clip_correctly(base, steps):
    m = Model()
    x = m.int("x", 0, 6)
    expr = x.piecewise(base_value=base, steps=steps)
    assert isinstance(expr, PBExpr)
    for xv in _domain_vals(x):
        expected = _pw_value(xv, base, steps)
        mm = Model()
        xx = mm.int("x", 0, 6)
        ee = xx.piecewise(base_value=base, steps=steps)
        mm &= (xx == xv)
        mm &= (ee == expected)
        assert _solve_status(mm) != "unsat"


def test_piecewise_returns_pbexpr_and_does_not_eagerly_mutate_model_hard():
    m = Model()
    x = m.int("x", 0, 10)
    hard_before = len(m._hard)
    top_before = m._top_id()
    expr = x.piecewise(base_value=10, steps={2: 20, 5: 15})
    assert isinstance(expr, PBExpr)
    assert len(m._hard) == hard_before
    # Threshold literals already exist; piecewise should not burn new ids.
    assert m._top_id() == top_before


@pytest.mark.parametrize(
    "rhs,expect_unsat",
    [
        (9, True),
        (10, False),
        (11, False),
        (20, False),
    ],
)
def test_piecewise_budget_constraint_monotone_case(rhs, expect_unsat):
    # f(x): 10 for x<3, 25 for x>=3
    m = Model()
    x = m.int("x", 0, 6)
    cost = x.piecewise(base_value=10, steps={3: 25})
    m &= (x == 2)
    m &= (cost <= rhs)
    assert (_solve_status(m) == "unsat") is expect_unsat


@pytest.mark.parametrize(
    "xv,rhs,expect_unsat",
    [
        (0, 9, True),
        (0, 10, False),
        (2, 24, True),
        (2, 25, False),
        (4, 24, False),  # non-monotonic drop
        (4, 9, True),
    ],
)
def test_piecewise_budget_constraint_non_monotone_case(xv, rhs, expect_unsat):
    # 10 -> 25 at 2, then back to 10 at 4
    m = Model()
    x = m.int("x", 0, 6)
    cost = x.piecewise(base_value=10, steps={2: 25, 4: 10})
    m &= (x == xv)
    m &= (cost <= rhs)
    assert (_solve_status(m) == "unsat") is expect_unsat


@pytest.mark.parametrize("xv", [0, 1, 2, 3, 4, 5])
def test_piecewise_can_be_compared_to_another_int_expression(xv):
    m = Model()
    x = m.int("x", 0, 6)
    y = m.int("y", 0, 100)
    cost = x.piecewise(base_value=10, steps={2: 25, 4: 10})
    m &= (x == xv)
    m &= (y == _pw_value(xv, 10, {2: 25, 4: 10}))
    m &= (cost == y)
    assert _solve_status(m) != "unsat"


@pytest.mark.parametrize(
    "xv,other,expect",
    [
        (0, 1, 11),
        (2, 3, 28),
        (4, 7, 17),   # non-monotonic drop path
        (5, -1, 9),
    ],
)
def test_piecewise_composes_with_pb_addition(xv, other, expect):
    m = Model()
    x = m.int("x", 0, 6)
    expr = x.piecewise(base_value=10, steps={2: 25, 4: 10}) + other
    m &= (x == xv)
    m &= (expr == expect)
    assert _solve_status(m) != "unsat"


@pytest.mark.parametrize(
    "xv,expect",
    [
        (0, 10),
        (1, 10),
        (2, 25),
        (3, 25),
        (4, 100),
        (5, 100),
    ],
)
def test_piecewise_can_drive_int_objective_via_pb_budget_style(xv, expect):
    # Indirectly checks negative/positive delta semantics through equality.
    m = Model()
    x = m.int("x", 0, 6)
    c = x.piecewise(base_value=10, steps={2: 25, 4: 100})
    m &= (x == xv)
    m &= (c == expect)
    assert _solve_status(m) != "unsat"


def test_piecewise_with_negative_delta_is_exact_over_domain():
    base = 50
    steps = {2: 80, 4: 30, 5: 60}
    for xv in range(0, 7):
        m = Model()
        x = m.int("x", 0, 7)
        c = x.piecewise(base_value=base, steps=steps)
        m &= (x == xv)
        m &= (c == _pw_value(xv, base, steps))
        assert _solve_status(m) != "unsat"


def test_piecewise_invalid_base_type_rejected():
    m = Model()
    x = m.int("x", 0, 5)
    with pytest.raises(TypeError):
        x.piecewise(base_value=True, steps={})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "steps",
    [
        {True: 1},        # bool key not allowed
        {1: True},        # bool value not allowed
        {"1": 2},         # non-int key
        {1: "2"},         # non-int value
    ],
)
def test_piecewise_invalid_steps_types_rejected(steps):
    m = Model()
    x = m.int("x", 0, 5)
    with pytest.raises(TypeError):
        x.piecewise(base_value=0, steps=steps)  # type: ignore[arg-type]


def test_piecewise_requires_mapping_steps():
    m = Model()
    x = m.int("x", 0, 5)
    with pytest.raises(TypeError):
        x.piecewise(base_value=0, steps=[(1, 2)])  # type: ignore[arg-type]


def test_piecewise_zero_deltas_are_elided_structurally():
    m = Model()
    x = m.int("x", 0, 10)
    e1 = x.piecewise(base_value=10, steps={2: 20, 5: 20, 7: 15})
    e2 = x.piecewise(base_value=10, steps={2: 20, 7: 15})
    # Same semantics; also same number of non-constant terms after eliding no-op step.
    assert len(e1.terms) == len(e2.terms)
    for xv in range(0, 10):
        mm = Model()
        xx = mm.int("x", 0, 10)
        a = xx.piecewise(base_value=10, steps={2: 20, 5: 20, 7: 15})
        b = xx.piecewise(base_value=10, steps={2: 20, 7: 15})
        mm &= (xx == xv)
        mm &= (a == b)
        assert _solve_status(mm) != "unsat"


@pytest.mark.parametrize(
    "base,steps",
    [
        (10, {0: 10, 2: 12, 4: 12, 6: 7}),
        (3, {1: 8, 3: -2, 5: 8}),
    ],
)
def test_piecewise_matches_bruteforce_for_all_values(base, steps):
    m = Model()
    x = m.int("x", 0, 8)
    expr = x.piecewise(base_value=base, steps=steps)
    assert isinstance(expr, PBExpr)

    for xv in range(0, 8):
        expected = _pw_value(xv, base, steps)
        mm = Model()
        xx = mm.int("x", 0, 8)
        ee = xx.piecewise(base_value=base, steps=steps)
        mm &= (xx == xv)
        mm &= (ee <= expected)
        mm &= (ee >= expected)
        assert _solve_status(mm) != "unsat"


def test_piecewise_works_inside_mixed_pb_constraint():
    m = Model()
    x = m.int("x", 0, 6)
    b = m.bool("b")
    cost = x.piecewise(base_value=10, steps={2: 25, 4: 10})
    m &= (x == 3)
    m &= b
    m &= (cost + b <= 26)   # 25 + 1
    assert _solve_status(m) != "unsat"

    m2 = Model()
    x2 = m2.int("x", 0, 6)
    b2 = m2.bool("b")
    cost2 = x2.piecewise(base_value=10, steps={2: 25, 4: 10})
    m2 &= (x2 == 3)
    m2 &= b2
    m2 &= (cost2 + b2 <= 25)  # too tight
    assert _solve_status(m2) == "unsat"


def test_piecewise_respects_model_ownership():
    m1 = Model()
    x1 = m1.int("x", 0, 5)
    e1 = x1.piecewise(base_value=0, steps={2: 3})

    m2 = Model()
    y2 = m2.int("y", 0, 5)

    with pytest.raises(ValueError):
        m2 &= (e1 == y2)
