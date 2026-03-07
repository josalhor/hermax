from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
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


@pytest.mark.parametrize("strict", [False, True])
def test_trivariate_fastpath_bypasses_pb_and_card(strict: bool, monkeypatch):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for trivariate fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for trivariate fast path")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    z = m.int("z", 0, 10)
    top_before = m._top_id()
    if strict:
        m &= (x + y < z)
        assert m._top_id() == top_before
        m &= (x == 2)
        m &= (y == 3)
        m &= (z == 6)
    else:
        m &= (x + y <= z)
        assert m._top_id() == top_before
        m &= (x == 2)
        m &= (y == 3)
        m &= (z == 5)
    r = _solve(m)
    assert r.ok
