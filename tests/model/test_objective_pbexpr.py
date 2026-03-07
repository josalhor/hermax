from __future__ import annotations

import itertools

import pytest

from hermax.model import Model, PBExpr


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok
    return r


def _value_pbexpr(expr: PBExpr, assign: dict[int, bool]) -> int:
    # Tests in this file realize lazy int terms before calling this helper.
    assert not expr.int_terms
    total = int(expr.constant)
    for t in expr.terms:
        lit = t.literal
        val = assign[lit.id]
        truth = val if lit.polarity else (not val)
        if truth:
            total += int(t.coefficient)
    return total


def test_obj_add_pbexpr_is_supported_and_minimizes_expression_value():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    expr = 2 * a + b + 3
    m.obj[1] += expr
    r = _solve_ok(m)
    # Minimize 2*a + b + 3 => choose a=false,b=false -> cost 3
    assert r[a] is False
    assert r[b] is False
    assert r.cost == 3


def test_obj_add_pbexpr_with_negative_coefficients_normalizes_correctly():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    # expr = 5 - 2*a + b
    expr = 5 + (-2) * a + b
    m.obj[1] += expr
    r = _solve_ok(m)
    # Minimized at a=true, b=false => 3
    assert r[a] is True
    assert r[b] is False
    assert r.cost == 3


def test_obj_add_pbexpr_respects_outer_bucket_weight_scaling():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    expr = a + 2 * b + 1
    m.obj[4] += expr
    r = _solve_ok(m)
    assert r[a] is False and r[b] is False
    assert r.cost == 4  # 4 * (0 + 0 + 1)


def test_obj_add_pbexpr_composes_with_other_soft_constraints():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj[5] += ~a
    m.obj[1] += (2 * a + b + 1)
    r = _solve_ok(m)
    # obj[5] += ~a pays when a=True. Combined with 2*a+b+1, optimum is a=False,b=False.
    assert r[a] is False
    assert r[b] is False
    assert r.cost == 1


def test_obj_add_pbexpr_with_piecewise_cost_avoids_proxy_and_solves():
    m = Model()
    x = m.int("x", 0, 8)
    cost = x.piecewise(base_value=10, steps={2: 25, 4: 10, 6: 40})
    top_before = m._top_id()
    m.obj[1] += cost
    # Adding PBExpr objective should not materialize a proxy IntVar.
    assert m._top_id() == top_before
    r = _solve_ok(m)
    # minimum piecewise value is 10 on x in [0,2) and [4,6)
    assert r.cost == 10
    assert r[x] in {0, 1, 4, 5}


def test_obj_add_pbexpr_realizes_lazy_int_terms_inside_expression():
    m = Model()
    x = m.int("x", 0, 10)
    q = x // 3  # lazy DivExpr inside PBExpr
    expr = q + 2
    top_before = m._top_id()
    m.obj[1] += expr
    # Realization may allocate the quotient IntVar and links.
    assert m._top_id() > top_before
    r = _solve_ok(m)
    assert r[x] == 0
    assert r.cost == 2  # floor(0/3) + 2


def test_obj_add_pbexpr_cross_model_rejected():
    m1 = Model()
    a = m1.bool("a")
    m2 = Model()
    with pytest.raises(ValueError, match="different models"):
        m2.obj[1] += (a + 1)


def test_obj_add_pbexpr_bool_weight_bucket_matches_existing_int_weight_behavior():
    m = Model()
    a = m.bool("a")
    # The objective bucket currently accepts bool because bool is an int subclass.
    m.obj[True] += (a + 1)  # type: ignore[index]
    r = _solve_ok(m)
    assert r[a] is False
    assert r.cost == 1


def test_obj_add_pbexpr_exact_cost_matches_bruteforce_small_bools():
    # Lock the lowering semantics on a compact mixed-sign expression.
    for aval, bval, cval in itertools.product([False, True], repeat=3):
        m = Model()
        a = m.bool("a")
        b = m.bool("b")
        c = m.bool("c")
        expr = 7 + 2 * a + (-3) * b + c
        m.obj[2] += expr
        m &= (a if aval else ~a)
        m &= (b if bval else ~b)
        m &= (c if cval else ~c)
        r = _solve_ok(m)
        realized = expr._realize_int_terms(m)
        expect = 2 * _value_pbexpr(
            realized,
            {
                a.id: aval,
                b.id: bval,
                c.id: cval,
            },
        )
        assert r.cost == expect


def test_obj_add_pbexpr_stores_only_soft_unit_clauses_for_boolean_terms():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    expr = 3 + 2 * a + (-1) * b
    hard_before = len(m._hard)
    m.obj[5] += expr
    # A single hard clause may be introduced to define internal __false when
    # positive constants are lowered natively.
    assert len(m._hard) in (hard_before, hard_before + 1)
    # Expect one soft clause per nonzero term plus one native constant soft term.
    softs = m._soft
    assert len(softs) == 3
    weights = sorted(w for w, _ in softs)
    # Scaled by outer bucket 5: 2*a -> 10, (-1)*b -> weight 5 after normalization.
    assert weights == [5, 10, 10]
    # Positive constants are lowered natively to __false soft terms.
    assert m._objective_constant == 0


def test_obj_add_negated_piecewise_pbexpr_is_supported():
    m = Model()
    x = m.int("x", 0, 8)
    gain = x.piecewise(base_value=0, steps={2: 3, 5: 10})
    m.obj[1] += -gain
    r = _solve_ok(m)
    # Maximizing gain via minimizing -gain should push to highest tier.
    assert r[x] in {5, 6, 7}
    assert r.cost == -10
