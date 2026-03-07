from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
from hermax.model import Model


OPS = ("<=", "<", ">=", ">", "==")


def _cmp(a: int, op: str, b: int) -> bool:
    if op == "<=":
        return a <= b
    if op == "<":
        return a < b
    if op == ">=":
        return a >= b
    if op == ">":
        return a > b
    if op == "==":
        return a == b
    raise ValueError(op)


def _solve(m: Model):
    return m.solve()


def _constrain_expr(m: Model, x, y, a: int, b: int, op: str, c: int):
    lhs = a * x + b * y
    if op == "<=":
        m &= (lhs <= c)
    elif op == "<":
        m &= (lhs < c)
    elif op == ">=":
        m &= (lhs >= c)
    elif op == ">":
        m &= (lhs > c)
    elif op == "==":
        m &= (lhs == c)
    else:
        raise ValueError(op)


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("a,b,c", [
    (1, -1, 5),   # offset
    (1, 1, 10),   # additive upper bound
    (2, -1, 0),   # scaled-vs-int
    (3, 2, 17),   # general positive coefficients
    (-2, 3, 4),   # mixed signs
    (-3, -1, -6), # both negative
])
def test_unified_bivariate_fastpath_matches_bruteforce_small_domains(op: str, a: int, b: int, c: int):
    dom = range(0, 5)
    expected = any(_cmp(a * xv + b * yv, op, c) for xv, yv in itertools.product(dom, dom))

    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 0, 5)
    _constrain_expr(m, x, y, a, b, op, c)
    r = _solve(m)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("a,b", [(2, -3), (-2, 3), (3, 1), (-1, -2)])
def test_unified_bivariate_fastpath_matches_bruteforce_shifted_domains(op: str, a: int, b: int):
    xdom = range(-2, 4)
    ydom = range(5, 10)
    for c in (-12, -3, 0, 4, 9, 17):
        expected = any(_cmp(a * xv + b * yv, op, c) for xv, yv in itertools.product(xdom, ydom))
        m = Model()
        x = m.int("x", -2, 4)
        y = m.int("y", 5, 10)
        _constrain_expr(m, x, y, a, b, op, c)
        r = _solve(m)
        assert (r.ok if expected else r.status == "unsat"), (op, a, b, c)


@pytest.mark.parametrize("expr_builder", [
    lambda x, y: (x + 5 <= y),
    lambda x, y: (x - 3 <= y),
    lambda x, y: (3 * x <= y),
    lambda x, y: (x + 0 <= 2 * y + 1),
    lambda x, y: (2 * x + 3 * y <= 17),
    lambda x, y: (2 * x - 3 * y < 4),
    lambda x, y: (-2 * x + 3 * y >= -1),
    lambda x, y: (3 * x + 2 * y == 11),
])
def test_unified_bivariate_fastpath_bypasses_pb_and_card_encoders(monkeypatch, expr_builder):
    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for unified bivariate Int fast path")

    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for unified bivariate Int fast path")

    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))
    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))

    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    m &= expr_builder(x, y)
    # Add a loose witness to force solving and materialization.
    m &= (x >= 0)
    r = _solve(m)
    assert r.status in {"sat", "optimum"}


@pytest.mark.parametrize("expr_builder", [
    lambda x, y: (x + 5 <= y),
    lambda x, y: (3 * x <= y),
    lambda x, y: (2 * x + 3 * y <= 17),
    lambda x, y: (2 * x + 3 * y == 17),
    lambda x, y: (-2 * x + 3 * y >= -1),
])
def test_unified_bivariate_fastpath_allocates_no_helper_variables(monkeypatch, expr_builder):
    # Ensure no fallback encoder is used; the check is specifically about helper vars.
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))

    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    top_before = m._top_id()
    hard_before = len(m._hard)

    m &= expr_builder(x, y)

    assert len(m._hard) > hard_before
    assert m._top_id() == top_before


@pytest.mark.parametrize("a,b,op,c", [
    (2, 4, "==", 3),   # parity impossible
    (3, 6, "==", 5),   # gcd impossible
    (1, 1, "<", -1),   # impossible over nonnegative domain
    (-1, -1, ">", 0),  # impossible over nonnegative domain
])
def test_unified_bivariate_fastpath_handles_impossible_cases_without_pb(monkeypatch, a: int, b: int, op: str, c: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))

    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 0, 5)
    _constrain_expr(m, x, y, a, b, op, c)
    r = _solve(m)
    assert r.status == "unsat"


@pytest.mark.parametrize("a,b,op,c,xv,yv", [
    (1, 1, "<=", 5, 2, 3),
    (1, 1, "<=", 4, 2, 3),
    (2, -1, ">=", 1, 2, 3),
    (2, -1, ">=", 2, 2, 3),
    (3, 2, "==", 12, 2, 3),
    (3, 2, "==", 13, 2, 3),
    (-2, 3, "<", 4, 1, 2),
    (-2, 3, "<", 3, 1, 2),
])
def test_unified_bivariate_fastpath_point_witness_cases(a, b, op, c, xv, yv):
    m = Model()
    x = m.int("x", 0, 6)
    y = m.int("y", 0, 6)
    _constrain_expr(m, x, y, a, b, op, c)
    m &= (x == xv)
    m &= (y == yv)
    r = _solve(m)
    expected = _cmp(a * xv + b * yv, op, c)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("a,b,c", [(1,1,5), (2,3,17), (-2,3,4), (3,-1,7)])
def test_unified_bivariate_fastpath_stricts_equivalent_to_shifted_nonstrict(a: int, b: int, c: int):
    dom = range(0, 5)
    # Compare semantics only via brute force, ensuring strict lowering is correct.
    lt_expected = any((a*x + b*y) < c for x, y in itertools.product(dom, dom))
    gt_expected = any((a*x + b*y) > c for x, y in itertools.product(dom, dom))

    m1 = Model(); x1 = m1.int('x',0,5); y1 = m1.int('y',0,5); _constrain_expr(m1,x1,y1,a,b,'<',c)
    m2 = Model(); x2 = m2.int('x',0,5); y2 = m2.int('y',0,5); _constrain_expr(m2,x2,y2,a,b,'>',c)
    r1 = _solve(m1); r2 = _solve(m2)
    assert (r1.ok if lt_expected else r1.status == 'unsat')
    assert (r2.ok if gt_expected else r2.status == 'unsat')


@pytest.mark.parametrize("a,b,c", [(1,1,4), (2,-3,1), (3,2,11), (-2,-1,-4)])
def test_unified_bivariate_fastpath_equality_matches_double_inequality(a: int, b: int, c: int):
    dom = range(0, 5)
    expected = any((a*x + b*y) == c for x, y in itertools.product(dom, dom))

    m_eq = Model(); x = m_eq.int('x',0,5); y = m_eq.int('y',0,5); _constrain_expr(m_eq,x,y,a,b,'==',c)
    m_dbl = Model(); x2 = m_dbl.int('x',0,5); y2 = m_dbl.int('y',0,5); _constrain_expr(m_dbl,x2,y2,a,b,'<=',c); _constrain_expr(m_dbl,x2,y2,a,b,'>=',c)
    r_eq = _solve(m_eq); r_dbl = _solve(m_dbl)
    assert (r_eq.ok if expected else r_eq.status == 'unsat')
    assert (r_dbl.ok if expected else r_dbl.status == 'unsat')
