from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
from hermax.model import Model


def _solve(m: Model):
    return m.solve()


def _boolsum(xs):
    expr = 0
    for x in xs:
        expr = expr + x
    return expr


def _sat_expected_sum_le_m_y(n: int, mcoef: int) -> bool:
    # Exists assignment over x_1..x_n and y with: sum(x) <= mcoef * y.
    for y in (0, 1):
        for bits in itertools.product((0, 1), repeat=n):
            if sum(bits) <= mcoef * y:
                return True
    return False


@pytest.mark.parametrize("n,mcoef", [
    (1, 0),
    (1, 1),
    (2, 0),
    (2, 1),
    (2, 2),
    (3, 0),
    (3, 1),
    (3, 2),
    (3, 3),
    (4, 0),
    (4, 1),
    (4, 2),
    (4, 4),
])
def test_sum_le_m_times_y_matches_bruteforce(n: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= mcoef * y)
    r = _solve(m)
    expected = _sat_expected_sum_le_m_y(n, mcoef)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("n,mcoef", [
    (3, 0),
    (3, 1),
    (3, 2),
    (4, 1),
    (4, 2),
    (5, 3),
])
def test_sum_le_m_times_y_no_pb_no_card(monkeypatch, n: int, mcoef: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for sum(x) <= M*y fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for sum(x) <= M*y fast path")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= mcoef * y)
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


@pytest.mark.parametrize("n", [2, 3, 5])
def test_sum_le_m_times_y_shortcircuit_when_m_ge_n(n: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    top_before = m._top_id()
    hard_before = len(m._hard)
    m &= (_boolsum(xs) <= n * y)
    # In the ideal fast path this should reduce to only x_i -> y clauses.
    assert m._top_id() == top_before
    assert len(m._hard) >= hard_before


@pytest.mark.parametrize("n,mcoef", [
    (3, 1),
    (4, 2),
    (5, 3),
])
def test_sum_le_m_times_y_y_false_forces_all_x_false(n: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= mcoef * y)
    m &= ~y
    m &= xs[0]
    r = _solve(m)
    assert r.status == "unsat"


@pytest.mark.parametrize("n,mcoef", [
    (3, 1),
    (4, 2),
    (5, 3),
])
def test_sum_le_m_times_y_y_true_allows_up_to_m(n: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= mcoef * y)
    m &= y
    for i in range(min(mcoef, n)):
        m &= xs[i]
    r = _solve(m)
    assert r.ok


@pytest.mark.parametrize("n,mcoef", [
    (3, 1),
    (4, 2),
    (5, 3),
])
def test_sum_strict_lt_m_times_y_semantics(n: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) < mcoef * y)
    r = _solve(m)
    expected = any(
        sum(bits) < (mcoef * yy)
        for yy in (0, 1)
        for bits in itertools.product((0, 1), repeat=n)
    )
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("n,mcoef", [
    (3, 1),
    (4, 2),
    (5, 3),
])
def test_swapped_orientation_m_times_y_ge_sum_supported(n: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (mcoef * y >= _boolsum(xs))
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


@pytest.mark.parametrize("n,mcoef", [
    (3, 1),
    (4, 2),
    (5, 3),
])
def test_swapped_orientation_uses_no_pb_no_card(monkeypatch, n: int, mcoef: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for swapped bool-sum Big-M fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for swapped bool-sum Big-M fast path")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (mcoef * y >= _boolsum(xs))
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}
