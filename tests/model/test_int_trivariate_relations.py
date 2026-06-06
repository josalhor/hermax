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


@pytest.mark.parametrize("op", ["<=", "<"])
def test_trivariate_sum_relation_matches_bruteforce_small_domains(op: str):
    xdom = range(0, 5)
    ydom = range(0, 5)
    zdom = range(0, 5)

    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 0, 5)
    z = m.int("z", 0, 5)

    if op == "<=":
        m &= (x + y <= z)
    else:
        m &= (x + y < z)

    for xv, yv, zv in itertools.product(xdom, ydom, zdom):
        mpt = Model()
        xp = mpt.int("x", 0, 5)
        yp = mpt.int("y", 0, 5)
        zp = mpt.int("z", 0, 5)
        if op == "<=":
            mpt &= (xp + yp <= zp)
            expected = (xv + yv <= zv)
        else:
            mpt &= (xp + yp < zp)
            expected = (xv + yv < zv)
        mpt &= (xp == xv)
        mpt &= (yp == yv)
        mpt &= (zp == zv)
        r = _solve(mpt)
        assert (r.ok if expected else r.status == "unsat"), (op, xv, yv, zv)


def test_trivariate_sum_leq_sat_and_unsat_witnesses():
    # SAT witness: 1 + 2 <= 4
    m_sat = Model()
    x = m_sat.int("x", 0, 6)
    y = m_sat.int("y", 0, 6)
    z = m_sat.int("z", 0, 6)
    m_sat &= (x + y <= z)
    m_sat &= (x == 1)
    m_sat &= (y == 2)
    m_sat &= (z == 4)
    r_sat = _solve(m_sat)
    assert r_sat.ok

    # UNSAT witness: 3 + 3 <= 5 is false
    m_unsat = Model()
    x2 = m_unsat.int("x", 0, 6)
    y2 = m_unsat.int("y", 0, 6)
    z2 = m_unsat.int("z", 0, 6)
    m_unsat &= (x2 + y2 <= z2)
    m_unsat &= (x2 == 3)
    m_unsat &= (y2 == 3)
    m_unsat &= (z2 == 5)
    r_unsat = _solve(m_unsat)
    assert r_unsat.status == "unsat"


def test_trivariate_sum_lt_sat_and_unsat_witnesses():
    # SAT witness: 1 + 2 < 4
    m_sat = Model()
    x = m_sat.int("x", 0, 6)
    y = m_sat.int("y", 0, 6)
    z = m_sat.int("z", 0, 6)
    m_sat &= (x + y < z)
    m_sat &= (x == 1)
    m_sat &= (y == 2)
    m_sat &= (z == 4)
    r_sat = _solve(m_sat)
    assert r_sat.ok

    # UNSAT witness: 2 + 2 < 4 is false
    m_unsat = Model()
    x2 = m_unsat.int("x", 0, 6)
    y2 = m_unsat.int("y", 0, 6)
    z2 = m_unsat.int("z", 0, 6)
    m_unsat &= (x2 + y2 < z2)
    m_unsat &= (x2 == 2)
    m_unsat &= (y2 == 2)
    m_unsat &= (z2 == 4)
    r_unsat = _solve(m_unsat)
    assert r_unsat.status == "unsat"


@pytest.mark.parametrize("op", ["<=", "<"])
def test_trivariate_sum_relation_matches_bruteforce_shifted_domains(op: str):
    xdom = range(-2, 3)
    ydom = range(1, 6)
    zdom = range(-1, 8)

    for shift in (-2, 0, 3):
        for xv, yv, zv in itertools.product(xdom, ydom, zdom):
            m = Model()
            x = m.int("x", -2, 3)
            y = m.int("y", 1, 6)
            z = m.int("z", -1, 8)
            if op == "<=":
                m &= (x + y + shift <= z)
                expected = (xv + yv + shift <= zv)
            else:
                m &= (x + y + shift < z)
                expected = (xv + yv + shift < zv)
            m &= (x == xv)
            m &= (y == yv)
            m &= (z == zv)
            r = _solve(m)
            assert (r.ok if expected else r.status == "unsat"), (op, shift, xv, yv, zv)


def test_trivariate_sum_relation_random_shifted_witnesses():
    rng = random.Random(20260606)
    for _ in range(50):
        xl = rng.randint(-4, 1)
        xu = xl + rng.randint(2, 6)
        yl = rng.randint(-3, 2)
        yu = yl + rng.randint(2, 6)
        zl = rng.randint(-5, 1)
        zu = zl + rng.randint(4, 10)
        shift = rng.randint(-4, 4)
        strict = rng.choice([False, True])
        xv = rng.randint(xl, xu)
        yv = rng.randint(yl, yu)
        zv = rng.randint(zl, zu)

        m = Model()
        x = m.int("x", xl, xu)
        y = m.int("y", yl, yu)
        z = m.int("z", zl, zu)
        if strict:
            m &= (x + y + shift < z)
            expected = (xv + yv + shift < zv)
        else:
            m &= (x + y + shift <= z)
            expected = (xv + yv + shift <= zv)
        m &= (x == xv)
        m &= (y == yv)
        m &= (z == zv)
        r = _solve(m)
        assert (r.ok if expected else r.status == "unsat"), (
            strict,
            shift,
            (xl, xu),
            (yl, yu),
            (zl, zu),
            (xv, yv, zv),
        )


@pytest.mark.parametrize("strict", [False, True])
def test_trivariate_fastpath_bypasses_pb_and_card(strict: bool, monkeypatch):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for trivariate fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for trivariate fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    z = m.int("z", 0, 10)
    if strict:
        m &= (x + y < z)
        m &= (x == 2)
        m &= (y == 3)
        m &= (z == 6)
    else:
        m &= (x + y <= z)
        m &= (x == 2)
        m &= (y == 3)
        m &= (z == 5)
    r = _solve(m)
    assert r.ok


@pytest.mark.parametrize("strict", [False, True])
def test_trivariate_large_domains_with_offset_still_bypass_pb_and_card(strict: bool, monkeypatch):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for trivariate fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for trivariate fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", -3, 17)
    y = m.int("y", 2, 22)
    z = m.int("z", -4, 40)
    if strict:
        m &= (x + y + 3 < z)
        m &= (x == 7)
        m &= (y == 11)
        m &= (z == 22)
    else:
        m &= (x + y - 2 <= z)
        m &= (x == 7)
        m &= (y == 11)
        m &= (z == 16)
    r = _solve(m)
    assert r.ok
