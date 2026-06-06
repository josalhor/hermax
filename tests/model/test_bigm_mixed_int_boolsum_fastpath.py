from __future__ import annotations

import itertools
import random

import pytest

import hermax.model as hm
from hermax.internal.card import CardEnc
from hermax.internal.pb import PBEnc
from hermax.model import Model


def _solve(m: Model):
    return m.solve()


def _boolsum(xs):
    out = 0
    for x in xs:
        out = out + x
    return out


def _exists_sat_mixed(
    xdom: range,
    nbool: int,
    a: int,
    k: int,
    mcoef: int,
    op: str = "<=",
) -> bool:
    for xv in xdom:
        for yv in (0, 1):
            for bits in itertools.product((0, 1), repeat=nbool):
                lhs = a * xv + sum(bits)
                rhs = k + mcoef * yv
                if op == "<=" and lhs <= rhs:
                    return True
                if op == "<" and lhs < rhs:
                    return True
    return False


@pytest.mark.parametrize("a,k,mcoef", [
    (1, 1, 2),
    (1, 2, 2),
    (1, 3, 1),
    (2, 3, 2),
    (2, 4, 1),
    (-1, 2, 2),
    (-2, 1, 3),
])
def test_mixed_int_boolsum_bigm_le_matches_bruteforce(a: int, k: int, mcoef: int):
    m = Model()
    x = m.int("x", 0, 4)
    bs = [m.bool("b0"), m.bool("b1"), m.bool("b2")]
    y = m.bool("y")
    m &= (a * x + _boolsum(bs) <= (k + mcoef * y))
    r = _solve(m)
    expected = _exists_sat_mixed(range(0, 4), 3, a, k, mcoef, "<=")
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("a,k,mcoef", [
    (1, 2, 2),
    (2, 4, 1),
    (-1, 2, 2),
])
def test_mixed_int_boolsum_bigm_lt_matches_bruteforce(a: int, k: int, mcoef: int):
    m = Model()
    x = m.int("x", 0, 4)
    bs = [m.bool("b0"), m.bool("b1"), m.bool("b2")]
    y = m.bool("y")
    m &= (a * x + _boolsum(bs) < (k + mcoef * y))
    r = _solve(m)
    expected = _exists_sat_mixed(range(0, 4), 3, a, k, mcoef, "<")
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("a,k,mcoef", [
    (1, 2, 2),
    (2, 4, 1),
    (-1, 2, 2),
])
def test_mixed_int_boolsum_swapped_orientation_supported(a: int, k: int, mcoef: int):
    m = Model()
    x = m.int("x", 0, 4)
    bs = [m.bool("b0"), m.bool("b1"), m.bool("b2")]
    y = m.bool("y")
    m &= ((k + mcoef * y) >= (a * x + _boolsum(bs)))
    r = _solve(m)
    expected = _exists_sat_mixed(range(0, 4), 3, a, k, mcoef, "<=")
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("a,k,mcoef", [
    (1, 2, 2),
    (2, 4, 1),
    (-1, 2, 2),
])
def test_mixed_int_boolsum_no_pb_no_card(monkeypatch, a: int, k: int, mcoef: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for mixed int+boolsum Big-M fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for mixed int+boolsum Big-M fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 4)
    bs = [m.bool("b0"), m.bool("b1"), m.bool("b2")]
    y = m.bool("y")
    m &= (a * x + _boolsum(bs) <= (k + mcoef * y))
    r = _solve(m)
    expected = _exists_sat_mixed(range(0, 4), 3, a, k, mcoef, "<=")
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("a,k,mcoef", [
    (1, 2, 2),
    (2, 4, 1),
    (-1, 2, 2),
])
def test_mixed_int_boolsum_swapped_no_pb_no_card(monkeypatch, a: int, k: int, mcoef: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for swapped mixed int+boolsum Big-M fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for swapped mixed int+boolsum Big-M fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 4)
    bs = [m.bool("b0"), m.bool("b1"), m.bool("b2")]
    y = m.bool("y")
    m &= ((k + mcoef * y) >= (a * x + _boolsum(bs)))
    r = _solve(m)
    expected = _exists_sat_mixed(range(0, 4), 3, a, k, mcoef, "<=")
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("a,k,mcoef", [
    (1, 0, 2),
    (2, 1, 2),
    (-1, 0, 2),
])
def test_mixed_int_boolsum_y_false_tighter_branch(a: int, k: int, mcoef: int):
    m = Model()
    x = m.int("x", 0, 4)
    bs = [m.bool("b0"), m.bool("b1"), m.bool("b2")]
    y = m.bool("y")
    m &= (a * x + _boolsum(bs) <= (k + mcoef * y))
    m &= ~y
    # Force a violating assignment for the y=false branch when possible.
    m &= (x == 3)
    m &= bs[0]
    m &= bs[1]
    r = _solve(m)
    expected = any((a * 3 + (2 + b2)) <= k for b2 in (0, 1))
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("seed", [201, 202, 203])
def test_mixed_int_boolsum_randomized_point_checks(seed: int):
    rng = random.Random(seed)
    for _ in range(20):
        a = rng.choice([-3, -2, -1, 1, 2, 3])
        k = rng.randint(-2, 8)
        mcoef = rng.randint(1, 5)
        op = rng.choice(["<=", "<"])
        lb = rng.randint(-2, 1)
        ub = lb + rng.randint(3, 7)
        xv = rng.randint(lb, ub)
        gate = rng.randint(0, 1)
        bits = [rng.randint(0, 1) for _ in range(4)]

        m = Model()
        x = m.int("x", lb, ub)
        bs = [m.bool(f"b{i}") for i in range(4)]
        y = m.bool("y")
        lhs = a * x + _boolsum(bs)
        rhs = k + mcoef * y
        if op == "<=":
            m &= (lhs <= rhs)
            expected = a * xv + sum(bits) <= k + mcoef * gate
        else:
            m &= (lhs < rhs)
            expected = a * xv + sum(bits) < k + mcoef * gate
        m &= (x == xv)
        m &= (y if gate else ~y)
        for lit, bit in zip(bs, bits):
            m &= (lit if bit else ~lit)
        r = _solve(m)
        assert (r.ok if expected else r.status == "unsat"), (
            seed,
            a,
            k,
            mcoef,
            op,
            (lb, ub),
            xv,
            bits,
            gate,
        )
