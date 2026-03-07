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


def _exists_sat_upper(n: int, k: int, mcoef: int) -> bool:
    # sum(x) <= k + mcoef*y
    for y in (0, 1):
        for bits in itertools.product((0, 1), repeat=n):
            if sum(bits) <= k + mcoef * y:
                return True
    return False


def _exists_sat_lower(n: int, k: int, mcoef: int) -> bool:
    # sum(x) >= k - mcoef*(1-y)  == sum(x) >= (k-mcoef) + mcoef*y
    for y in (0, 1):
        for bits in itertools.product((0, 1), repeat=n):
            if sum(bits) >= (k - mcoef) + mcoef * y:
                return True
    return False


@pytest.mark.parametrize("n,k,mcoef", [
    (3, 1, 2),
    (3, 2, 1),
    (4, 1, 3),
    (4, 2, 2),
    (4, 3, 1),
    (5, 2, 3),
    (5, 3, 2),
    (5, 4, 1),
])
def test_upper_gated_bound_matches_bruteforce(n: int, k: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= (k + mcoef * y))
    r = _solve(m)
    expected = _exists_sat_upper(n, k, mcoef)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("n,k,mcoef", [
    (3, 1, 2),
    (3, 2, 1),
    (4, 1, 3),
    (4, 2, 2),
    (4, 3, 1),
    (5, 2, 3),
    (5, 3, 2),
    (5, 4, 1),
])
def test_lower_gated_bound_matches_bruteforce(n: int, k: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) >= ((k - mcoef) + mcoef * y))
    r = _solve(m)
    expected = _exists_sat_lower(n, k, mcoef)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("n,k,mcoef", [
    (4, 2, 2),
    (5, 2, 3),
    (5, 3, 2),
])
def test_upper_gated_bound_no_pb_no_card(monkeypatch, n: int, k: int, mcoef: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for gated upper-card fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for gated upper-card fast path")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= (k + mcoef * y))
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


@pytest.mark.parametrize("n,k,mcoef", [
    (4, 2, 2),
    (5, 2, 3),
    (5, 3, 2),
])
def test_lower_gated_bound_no_pb_no_card(monkeypatch, n: int, k: int, mcoef: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for gated lower-card fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for gated lower-card fast path")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) >= ((k - mcoef) + mcoef * y))
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


@pytest.mark.parametrize("n,k,mcoef", [
    (4, 2, 2),
    (5, 3, 2),
])
def test_upper_bound_when_y_false_is_tighter(n: int, k: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= (k + mcoef * y))
    m &= ~y
    for i in range(k + 1):
        m &= xs[i]
    r = _solve(m)
    assert r.status == "unsat"


@pytest.mark.parametrize("n,k,mcoef", [
    (4, 2, 2),
    (5, 3, 2),
])
def test_lower_bound_when_y_true_is_tighter(n: int, k: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) >= ((k - mcoef) + mcoef * y))
    m &= y
    for i in range(max(0, k - 1)):
        m &= xs[i]
    # force remaining to false to keep sum < k
    for i in range(max(0, k - 1), n):
        m &= ~xs[i]
    r = _solve(m)
    assert r.status == "unsat"


@pytest.mark.parametrize("n,k,mcoef", [
    (4, 2, 2),
    (5, 2, 3),
    (5, 3, 2),
])
def test_strict_upper_gated_bound_semantics(n: int, k: int, mcoef: int):
    # sum(x) < k + M*y
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) < (k + mcoef * y))
    r = _solve(m)
    expected = any(
        sum(bits) < (k + mcoef * yy)
        for yy in (0, 1)
        for bits in itertools.product((0, 1), repeat=n)
    )
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("n,k,mcoef", [
    (4, 2, 2),
    (5, 2, 3),
    (5, 3, 2),
])
def test_strict_lower_gated_bound_semantics(n: int, k: int, mcoef: int):
    # sum(x) > (k - M) + M*y
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) > ((k - mcoef) + mcoef * y))
    r = _solve(m)
    expected = any(
        sum(bits) > ((k - mcoef) + mcoef * yy)
        for yy in (0, 1)
        for bits in itertools.product((0, 1), repeat=n)
    )
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("n,k,mcoef", [
    (4, 2, 2),
    (5, 2, 3),
])
def test_swapped_orientation_upper_supported_no_pb_no_card(monkeypatch, n: int, k: int, mcoef: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for swapped upper gated-card fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for swapped upper gated-card fast path")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= ((k + mcoef * y) >= _boolsum(xs))
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


@pytest.mark.parametrize("n,k,mcoef", [
    (4, 2, 2),
    (5, 3, 2),
])
def test_swapped_orientation_lower_supported_no_pb_no_card(monkeypatch, n: int, k: int, mcoef: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for swapped lower gated-card fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for swapped lower gated-card fast path")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (((k - mcoef) + mcoef * y) <= _boolsum(xs))
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}
