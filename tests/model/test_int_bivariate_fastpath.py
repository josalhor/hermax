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
    if op == "!=":
        return a != b
    raise ValueError(op)


def _solve(m: Model):
    return m.solve()


@pytest.mark.parametrize("a", [-3, -2, -1, 1, 2, 3])
@pytest.mark.parametrize("b", [-3, -2, -1, 1, 2, 3])
@pytest.mark.parametrize("op", OPS)
def test_bivariate_int_fastpath_matches_bruteforce_small_same_domain(a: int, b: int, op: str):
    if a == 0 or b == 0:
        pytest.skip("Need exactly two active integer variables")
    dom = range(0, 4)
    for c in range(-10, 11):
        expected = any(_cmp(a * x + b * y, op, c) for x, y in itertools.product(dom, dom))

        m = Model()
        x = m.int("x", 0, 4)
        y = m.int("y", 0, 4)
        m &= _build_expr(x, y, a, b, op, c)
        r = _solve(m)
        assert (r.ok if expected else r.status == "unsat"), (a, b, op, c)


@pytest.mark.parametrize("op", ["<=", ">=", "=="])
def test_bivariate_int_fastpath_matches_bruteforce_shifted_domains(op: str):
    a, b = 2, -3
    xdom = range(-2, 3)
    ydom = range(5, 9)
    for c in range(-20, 21):
        expected = any(_cmp(a * x + b * y, op, c) for x, y in itertools.product(xdom, ydom))

        m = Model()
        x = m.int("x", -2, 3)
        y = m.int("y", 5, 9)
        m &= _build_expr(x, y, a, b, op, c)
        r = _solve(m)
        assert (r.ok if expected else r.status == "unsat"), (op, c)


def test_bivariate_int_fastpath_bypasses_pb_and_card_encoders(monkeypatch):
    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for bivariate Int fast path")

    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for bivariate Int fast path")

    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))
    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))

    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    m &= (2 * x + 3 * y <= 17)
    m &= (x == 1)
    m &= (y == 5)
    r = _solve(m)
    assert r.ok and r[x] == 1 and r[y] == 5


def test_three_ints_still_fall_back_to_pb_encoder(monkeypatch):
    seen = {"pb": 0}
    real_pb_leq = hm.PBEnc.leq

    def wrapped_pb_leq(*args, **kwargs):
        seen["pb"] += 1
        return real_pb_leq(*args, **kwargs)

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(wrapped_pb_leq))

    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 0, 5)
    z = m.int("z", 0, 5)
    m &= (x + 2 * y + 3 * z <= 10)
    m &= (x == 1)
    m &= (y == 1)
    m &= (z == 2)
    r = _solve(m)
    assert r.ok
    assert seen["pb"] >= 1


def test_bivariate_fastpath_handles_infeasible_eq_branch_without_pb(monkeypatch):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))

    m = Model()
    x = m.int("x", 0, 4)
    y = m.int("y", 0, 4)
    m &= (2 * x + 4 * y == 3)  # impossible parity
    r = _solve(m)
    assert r.status == "unsat"


def _build_expr(x, y, a: int, b: int, op: str, c: int):
    lhs = a * x + b * y
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


def test_bivariate_int_fastpath_does_not_allocate_point_equality_proxies():
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    top_before = m._top_id()
    hard_before = len(m._hard)

    # Compiling the bivariate fast path should ideally introduce no new helper vars.
    m &= (2 * x + 3 * y <= 17)

    assert len(m._hard) > hard_before
    assert m._top_id() == top_before
