from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
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
    assert r.status in {"sat", "optimum", "unsat"}


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

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 4)
    bs = [m.bool("b0"), m.bool("b1"), m.bool("b2")]
    y = m.bool("y")
    m &= (a * x + _boolsum(bs) <= (k + mcoef * y))
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


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

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 4)
    bs = [m.bool("b0"), m.bool("b1"), m.bool("b2")]
    y = m.bool("y")
    m &= ((k + mcoef * y) >= (a * x + _boolsum(bs)))
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


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
    assert r.status in {"sat", "unsat"}  # semantic guard: must not crash / fallback errors

