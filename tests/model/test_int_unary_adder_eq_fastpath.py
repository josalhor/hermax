from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
from hermax.model import Model


def _solve(m: Model):
    return m.solve()


def test_unary_adder_eq_fastpath_matches_bruteforce_small_domains():
    xdom = range(0, 5)
    ydom = range(0, 5)
    zdom = range(0, 9)

    for xv, yv, zv in itertools.product(xdom, ydom, zdom):
        m = Model()
        x = m.int("x", 0, 5)
        y = m.int("y", 0, 5)
        z = m.int("z", 0, 9)
        m &= (x + y == z)
        m &= (x == xv)
        m &= (y == yv)
        m &= (z == zv)
        r = _solve(m)
        expected = (xv + yv == zv)
        assert (r.ok if expected else r.status == "unsat"), (xv, yv, zv)


def test_unary_adder_eq_fastpath_matches_bruteforce_shifted_domains():
    xdom = range(3, 8)
    ydom = range(-2, 3)
    zdom = range(1, 10)

    for xv, yv, zv in itertools.product(xdom, ydom, zdom):
        m = Model()
        x = m.int("x", 3, 8)
        y = m.int("y", -2, 3)
        z = m.int("z", 1, 10)
        m &= (x + y == z)
        m &= (x == xv)
        m &= (y == yv)
        m &= (z == zv)
        r = _solve(m)
        expected = (xv + yv == zv)
        assert (r.ok if expected else r.status == "unsat"), (xv, yv, zv)


def test_unary_adder_eq_fastpath_bypasses_pb_and_card(monkeypatch):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for unary-adder equality fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for unary-adder equality fast path")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 12)
    y = m.int("y", 0, 8)
    z = m.int("z", 0, 19)
    m &= (x + y == z)
    m &= (x == 7)
    m &= (y == 5)
    m &= (z == 12)
    r = _solve(m)
    assert r.ok


def test_unary_adder_eq_fastpath_skewed_sizes_still_solves():
    # Shape that benefits from padded merge topology.
    m = Model()
    x = m.int("x", 0, 1200)
    y = m.int("y", 0, 500)
    z = m.int("z", 0, 1699)
    m &= (x + y == z)
    m &= (x == 777)
    m &= (y == 211)
    m &= (z == 988)
    r = _solve(m)
    assert r.ok


def test_unary_adder_eq_fastpath_unsat_when_sum_below_min_bound():
    m = Model()
    x = m.int("x", 3, 8)    # min 3
    y = m.int("y", 2, 7)    # min 2
    z = m.int("z", 0, 20)
    m &= (x + y == z)
    m &= (z == 4)           # below 3+2
    r = _solve(m)
    assert r.status == "unsat"


def test_unary_adder_eq_fastpath_unsat_when_sum_above_max_bound():
    m = Model()
    x = m.int("x", 0, 5)    # max 4
    y = m.int("y", 0, 6)    # max 5
    z = m.int("z", 0, 20)
    m &= (x + y == z)
    m &= (z == 10)          # above 4+5
    r = _solve(m)
    assert r.status == "unsat"


def test_unary_adder_eq_fastpath_commutative_operands():
    m1 = Model()
    x1 = m1.int("x", 0, 10)
    y1 = m1.int("y", 0, 10)
    z1 = m1.int("z", 0, 19)
    m1 &= (x1 + y1 == z1)
    m1 &= (x1 == 6)
    m1 &= (y1 == 4)
    m1 &= (z1 == 10)
    r1 = _solve(m1)
    assert r1.ok

    m2 = Model()
    x2 = m2.int("x", 0, 10)
    y2 = m2.int("y", 0, 10)
    z2 = m2.int("z", 0, 19)
    m2 &= (y2 + x2 == z2)
    m2 &= (x2 == 6)
    m2 &= (y2 == 4)
    m2 &= (z2 == 10)
    r2 = _solve(m2)
    assert r2.ok


def test_unary_adder_eq_fastpath_triggered_for_matching_shape(monkeypatch):
    seen = {"called": 0, "matched": 0}
    orig = hm._EncoderDispatch._try_unary_adder_eq_fastpath

    def wrapped(model, lhs, op, rhs):
        seen["called"] += 1
        out = orig(model, lhs, op, rhs)
        if out is not None:
            seen["matched"] += 1
        return out

    monkeypatch.setattr(hm._EncoderDispatch, "_try_unary_adder_eq_fastpath", staticmethod(wrapped))

    m = Model()
    x = m.int("x", 0, 9)
    y = m.int("y", 0, 7)
    z = m.int("z", 0, 15)
    m &= (x + y == z)
    m &= (x == 5)
    m &= (y == 3)
    m &= (z == 8)
    r = _solve(m)
    assert r.ok
    assert seen["called"] >= 1
    assert seen["matched"] >= 1


def test_unary_adder_eq_fastpath_not_used_for_weighted_coefficients(monkeypatch):
    seen = {"matched": 0}
    orig = hm._EncoderDispatch._try_unary_adder_eq_fastpath

    def wrapped(model, lhs, op, rhs):
        out = orig(model, lhs, op, rhs)
        if out is not None:
            seen["matched"] += 1
        return out

    monkeypatch.setattr(hm._EncoderDispatch, "_try_unary_adder_eq_fastpath", staticmethod(wrapped))

    m = Model()
    x = m.int("x", 0, 6)
    y = m.int("y", 0, 6)
    z = m.int("z", 0, 18)
    m &= (2 * x + y == z)  # not unary-adder shape
    m &= (x == 2)
    m &= (y == 4)
    m &= (z == 8)
    r = _solve(m)
    assert r.ok
    assert seen["matched"] == 0


def test_unary_adder_eq_fastpath_random_witnesses_small_domains():
    # Dense witness check without exhaustive blow-up on larger mixed domains.
    samples = [
        (0, 0, 0),
        (1, 2, 3),
        (4, 3, 7),
        (2, 5, 7),
        (3, 3, 7),  # unsat witness (3+3!=7)
        (0, 4, 3),  # unsat witness
    ]
    for xv, yv, zv in samples:
        m = Model()
        x = m.int("x", 0, 6)
        y = m.int("y", 0, 6)
        z = m.int("z", 0, 11)
        m &= (x + y == z)
        m &= (x == xv)
        m &= (y == yv)
        m &= (z == zv)
        r = _solve(m)
        expected = (xv + yv == zv)
        assert (r.ok if expected else r.status == "unsat"), (xv, yv, zv)
