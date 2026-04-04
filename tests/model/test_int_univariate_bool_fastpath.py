from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
from hermax.model.encoders import _EncoderDispatch
from hermax.internal.card import CardEnc
from hermax.internal.pb import PBEnc
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


def _build_expr(x, b, a: int, w: int, op: str, c: int, *, neg_lit: bool = False):
    lit = (~b) if neg_lit else b
    lhs = a * x + w * lit
    if op == "<=":
        return lhs <= c
    if op == "<":
        return lhs < c
    if op == ">=":
        return lhs >= c
    if op == ">":
        return lhs > c
    if op == "==":
        return lhs == c
    raise ValueError(op)


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("a,w,c", [
    (1, 10, 0),    # classic Big-M style x - 10*b <= 0 encoded with w negative in other tests
    (2, 5, 11),
    (3, -4, 7),
    (-2, 6, -1),
    (-3, -5, 4),
])
@pytest.mark.parametrize("neg_lit", [False, True])
def test_univariate_bool_fastpath_matches_bruteforce_small_domains(op: str, a: int, w: int, c: int, neg_lit: bool):
    xdom = range(0, 6)
    bdom = (False, True)
    expected = any(
        _cmp(a * xv + w * (int((not bv) if neg_lit else bv)), op, c)
        for xv, bv in itertools.product(xdom, bdom)
    )
    m = Model()
    x = m.int("x", 0, 6)
    b = m.bool("b")
    m &= _build_expr(x, b, a, w, op, c, neg_lit=neg_lit)
    r = _solve(m)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("a,w,op,c,xv,bv", [
    (1, -10, "<=", 0, 0, False),
    (1, -10, "<=", 0, 11, True),
    (2, 5, "<=", 11, 3, False),
    (2, 5, "<=", 11, 4, True),
    (-2, 6, ">=", -1, 0, True),
    (-2, 6, ">=", -1, 2, False),
    (3, -4, "==", 5, 3, True),
    (3, -4, "==", 5, 1, False),
])
@pytest.mark.parametrize("neg_lit", [False, True])
def test_univariate_bool_fastpath_point_witness_cases(a, w, op, c, xv, bv, neg_lit):
    m = Model()
    x = m.int("x", 0, 12)
    b = m.bool("b")
    m &= _build_expr(x, b, a, w, op, c, neg_lit=neg_lit)
    m &= (x == xv)
    m &= ((~b) if not bv else b)
    r = _solve(m)
    lit_val = int((not bv) if neg_lit else bv)
    expected = _cmp(a * xv + w * lit_val, op, c)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("expr_builder", [
    lambda x, b: (x - 10 * b <= 0),
    lambda x, b: (2 * x + 5 * b <= 11),
    lambda x, b: (3 * x - 4 * b == 5),
    lambda x, b: (-2 * x + 6 * b >= -1),
    lambda x, b: (2 * x + 5 * ~b < 12),
])
def test_univariate_bool_fastpath_bypasses_pb_and_card(monkeypatch, expr_builder):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 12)
    b = m.bool("b")
    m &= expr_builder(x, b)
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


@pytest.mark.parametrize("expr_builder", [
    lambda x, b: (x - 10 * b <= 0),
    lambda x, b: (2 * x + 5 * b <= 11),
    lambda x, b: (3 * x - 4 * b == 5),
    lambda x, b: (-2 * x + 6 * b >= -1),
    lambda x, b: (2 * x + 5 * ~b < 12),
])
def test_univariate_bool_fastpath_allocates_no_helper_variables(expr_builder):
    m = Model()
    x = m.int("x", 0, 12)
    b = m.bool("b")
    top_before = m._top_id()
    hard_before = len(m._hard)
    m &= expr_builder(x, b)
    assert len(m._hard) >= hard_before
    assert m._top_id() == top_before


@pytest.mark.parametrize("expr_builder", [
    lambda x, y, b: (x + y + 5 * b <= 10),   # two IntVars + bool -> bivariate-bool path
    lambda x, b1, b2: (x + 3 * b1 + 4 * b2 <= 10),  # one IntVar + two bools -> generic fallback
])
def test_univariate_bool_fastpath_does_not_claim_unsupported_shapes(monkeypatch, expr_builder):
    seen = {"uni_calls": 0, "uni_hits": 0, "bivar_bool_hits": 0}
    o_uni = _EncoderDispatch._try_univariate_with_bool_fastpath
    o_bivar_bool = _EncoderDispatch._try_bivariate_with_bool_fastpath

    def w_uni(*args, **kwargs):
        seen["uni_calls"] += 1
        out = o_uni(*args, **kwargs)
        if out is not None:
            seen["uni_hits"] += 1
        return out

    def w_bivar_bool(*args, **kwargs):
        out = o_bivar_bool(*args, **kwargs)
        if out is not None:
            seen["bivar_bool_hits"] += 1
        return out

    monkeypatch.setattr(_EncoderDispatch, "_try_univariate_with_bool_fastpath", staticmethod(w_uni))
    monkeypatch.setattr(_EncoderDispatch, "_try_bivariate_with_bool_fastpath", staticmethod(w_bivar_bool))

    m = Model()
    x = m.int("x", 0, 6)
    if expr_builder.__code__.co_argcount == 3:
        y = m.int("y", 0, 6)
        b = m.bool("b")
        m &= expr_builder(x, y, b)
    else:
        b1 = m.bool("b1")
        b2 = m.bool("b2")
        m &= expr_builder(x, b1, b2)
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}
    assert seen["uni_calls"] >= 1
    assert seen["uni_hits"] == 0
    if expr_builder.__code__.co_argcount == 3:
        assert seen["bivar_bool_hits"] >= 1


@pytest.mark.parametrize("a,w,op,c", [
    (2, 4, "==", 3),   # parity impossible for both b branches
    (1, 1, "<", -1),   # impossible on x>=0 and b in {0,1}
    (-1, -1, ">", 0),  # impossible on x>=0 and b in {0,1}
])
def test_univariate_bool_fastpath_impossible_cases_without_pb(monkeypatch, a, w, op, c):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))

    m = Model()
    x = m.int("x", 0, 6)
    b = m.bool("b")
    m &= _build_expr(x, b, a, w, op, c)
    r = _solve(m)
    assert r.status == "unsat"


@pytest.mark.parametrize("const_x", [1, 3, 7, 11])
def test_int_equals_bool_times_constant_semantics(const_x: int):
    m = Model()
    a = m.int("A", 0, const_x + 2)
    b = m.bool("b")
    m &= (a == b * const_x)

    # b=false -> A must be 0
    m0 = Model()
    a0 = m0.int("A", 0, const_x + 2)
    b0 = m0.bool("b")
    m0 &= (a0 == b0 * const_x)
    m0 &= ~b0
    r0 = _solve(m0)
    assert r0.ok
    assert r0[a0] == 0

    # b=true -> A must be const_x
    m1 = Model()
    a1 = m1.int("A", 0, const_x + 2)
    b1 = m1.bool("b")
    m1 &= (a1 == b1 * const_x)
    m1 &= b1
    r1 = _solve(m1)
    assert r1.ok
    assert r1[a1] == const_x

    # Impossible witness: b=false and A=const_x is UNSAT
    m_bad = Model()
    a_bad = m_bad.int("A", 0, const_x + 2)
    b_bad = m_bad.bool("b")
    m_bad &= (a_bad == b_bad * const_x)
    m_bad &= ~b_bad
    m_bad &= (a_bad == const_x)
    r_bad = _solve(m_bad)
    assert r_bad.status == "unsat"


@pytest.mark.parametrize("const_x", [2, 5])
@pytest.mark.parametrize("op", ["<=", "<", ">=", ">"])
@pytest.mark.parametrize("aval,bval", [
    (0, False),
    (1, False),
    (0, True),
    (2, True),
    (4, True),
])
def test_int_relops_with_bool_times_constant_pointwise(const_x: int, op: str, aval: int, bval: bool):
    m = Model()
    a = m.int("A", 0, const_x + 3)
    b = m.bool("b")

    rhs = b * const_x
    if op == "<=":
        m &= (a <= rhs)
        expected = aval <= (const_x if bval else 0)
    elif op == "<":
        m &= (a < rhs)
        expected = aval < (const_x if bval else 0)
    elif op == ">=":
        m &= (a >= rhs)
        expected = aval >= (const_x if bval else 0)
    elif op == ">":
        m &= (a > rhs)
        expected = aval > (const_x if bval else 0)
    else:  # pragma: no cover
        raise ValueError(op)

    m &= (a == aval)
    m &= (b if bval else ~b)
    r = _solve(m)
    assert (r.ok if expected else r.status == "unsat")
