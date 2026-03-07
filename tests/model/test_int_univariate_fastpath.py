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


def _constrain_expr(m: Model, x, a: int, op: str, c: int):
    lhs = a * x
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
@pytest.mark.parametrize("a,c", [
    (1, 5),
    (2, 10),
    (3, 8),
    (-1, -3),
    (-2, 7),
    (5, 0),
])
def test_univariate_fastpath_matches_bruteforce_small_domains(op: str, a: int, c: int):
    dom = range(0, 6)
    expected = any(_cmp(a * xv, op, c) for xv in dom)
    m = Model()
    x = m.int("x", 0, 6)
    _constrain_expr(m, x, a, op, c)
    r = _solve(m)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("a", [1, 2, -1, -3])
def test_univariate_fastpath_matches_bruteforce_shifted_domains(op: str, a: int):
    dom = range(-3, 4)
    for c in (-12, -5, -1, 0, 3, 7, 11):
        expected = any(_cmp(a * xv, op, c) for xv in dom)
        m = Model()
        x = m.int("x", -3, 4)
        _constrain_expr(m, x, a, op, c)
        r = _solve(m)
        assert (r.ok if expected else r.status == "unsat"), (op, a, c)


@pytest.mark.parametrize("expr_builder", [
    lambda x: (2 * x <= 10),
    lambda x: (3 * x < 8),
    lambda x: (-2 * x >= -1),
    lambda x: (5 * x == 15),
    lambda x: (-3 * x > -9),
])
def test_univariate_fastpath_bypasses_pb_and_card(monkeypatch, expr_builder):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 10)
    m &= expr_builder(x)
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


@pytest.mark.parametrize("expr_builder", [
    lambda x: (2 * x <= 10),
    lambda x: (3 * x < 8),
    lambda x: (-2 * x >= -1),
    lambda x: (5 * x == 15),
    lambda x: (-3 * x > -9),
])
def test_univariate_fastpath_allocates_no_helper_variables(expr_builder):
    m = Model()
    x = m.int("x", 0, 10)
    top_before = m._top_id()
    hard_before = len(m._hard)
    m &= expr_builder(x)
    assert len(m._hard) >= hard_before
    assert m._top_id() == top_before


@pytest.mark.parametrize("a,op,c", [
    (2, "==", 3),   # parity impossible
    (3, "==", 5),   # gcd impossible
    (1, "<", 0),    # x<0 impossible on nonnegative domain
    (-1, ">", 0),   # -x>0 impossible on nonnegative domain
])
def test_univariate_fastpath_impossible_cases_without_pb(monkeypatch, a: int, op: str, c: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))

    m = Model()
    x = m.int("x", 0, 5)
    _constrain_expr(m, x, a, op, c)
    r = _solve(m)
    assert r.status == "unsat"


@pytest.mark.parametrize("a,op,c,xv", [
    (2, "<=", 10, 5),
    (2, "<=", 10, 6),
    (-2, ">=", -4, 2),
    (-2, ">=", -4, 3),
    (3, "==", 9, 3),
    (3, "==", 9, 4),
    (-3, ">", -7, 2),
    (-3, ">", -7, 3),
])
def test_univariate_fastpath_point_witness_cases(a, op, c, xv):
    m = Model()
    x = m.int("x", 0, 8)
    _constrain_expr(m, x, a, op, c)
    m &= (x == xv)
    r = _solve(m)
    expected = _cmp(a * xv, op, c)
    assert (r.ok if expected else r.status == "unsat")


def test_univariate_fastpath_fallback_for_non_affine_mixed_boolean_uses_pb(monkeypatch):
    called = {"pb": 0}

    orig = hm.PBEnc.leq

    def wrapped(*args, **kwargs):
        called["pb"] += 1
        return orig(*args, **kwargs)

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(wrapped))

    m = Model()
    x = m.int("x", 0, 6)
    a = m.bool("a")
    b = m.bool("b")
    # One IntVar + two booleans is outside the univariate/big-M fastpath.
    m &= (2 * x + a + b <= 7)
    _solve(m)
    assert called["pb"] >= 1
