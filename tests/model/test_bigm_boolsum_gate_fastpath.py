from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
from hermax.internal.card import CardEnc
from hermax.internal.pb import PBEnc
from hermax.model import Model


def _solve(m: Model):
    return m.solve()


def _boolsum(xs):
    expr = 0
    for x in xs:
        expr = expr + x
    return expr


def _compare(lhs, op: str, rhs):
    if op == "<=":
        return lhs <= rhs
    if op == "<":
        return lhs < rhs
    if op == ">=":
        return lhs >= rhs
    if op == ">":
        return lhs > rhs
    raise ValueError(f"Unsupported comparator {op!r}")


def _eval_compare(lhs: int, op: str, rhs: int) -> bool:
    if op == "<=":
        return lhs <= rhs
    if op == "<":
        return lhs < rhs
    if op == ">=":
        return lhs >= rhs
    if op == ">":
        return lhs > rhs
    raise ValueError(f"Unsupported comparator {op!r}")


def _assert_sum_gate_points(n: int, mcoef: int, op: str, *, swapped: bool = False) -> None:
    flipped = {"<=": ">=", "<": ">"}[op]
    for gate, bits in itertools.product((False, True), itertools.product((False, True), repeat=n)):
        m = Model()
        xs = [m.bool(f"x{i}") for i in range(n)]
        y = m.bool("y")
        lhs = _boolsum(xs)
        rhs = mcoef * y
        m &= _compare(rhs, flipped, lhs) if swapped else _compare(lhs, op, rhs)
        m &= y if gate else ~y
        for lit, bit in zip(xs, bits):
            m &= lit if bit else ~lit
        expected = _eval_compare(sum(bits), op, mcoef * int(gate))
        assert _solve(m).ok == expected, (n, mcoef, op, swapped, gate, bits, expected)


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
    _assert_sum_gate_points(n, mcoef, "<=")


@pytest.mark.parametrize("n", [3, 4, 5])
def test_sum_le_m_times_y_no_pb_no_card(monkeypatch, n: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for sum(x) <= M*y fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for sum(x) <= M*y fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= n * y)
    r = _solve(m)
    assert r.ok


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
    _assert_sum_gate_points(n, mcoef, "<")


@pytest.mark.parametrize("n,mcoef", [
    (3, 1),
    (4, 2),
    (5, 3),
])
def test_swapped_orientation_m_times_y_ge_sum_supported(n: int, mcoef: int):
    _assert_sum_gate_points(n, mcoef, "<=", swapped=True)


@pytest.mark.parametrize("n", [3, 4, 5])
def test_swapped_orientation_uses_no_pb_no_card(monkeypatch, n: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for swapped bool-sum Big-M fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for swapped bool-sum Big-M fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (n * y >= _boolsum(xs))
    r = _solve(m)
    assert r.ok
