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


def _assert_gated_bound_points(n: int, k: int, mcoef: int, op: str, *, lower: bool) -> None:
    """Check every input assignment, rather than merely existence of a model."""
    for gate, bits in itertools.product((False, True), itertools.product((False, True), repeat=n)):
        m = Model()
        xs = [m.bool(f"x{i}") for i in range(n)]
        y = m.bool("y")
        lhs = _boolsum(xs)
        rhs = (k - mcoef) + mcoef * y if lower else k + mcoef * y
        m &= _compare(lhs, op, rhs)
        m &= y if gate else ~y
        for lit, bit in zip(xs, bits):
            m &= lit if bit else ~lit
        expected = _eval_compare(sum(bits), op, (k - mcoef if lower else k) + mcoef * int(gate))
        assert _solve(m).ok == expected, (n, k, mcoef, op, lower, gate, bits, expected)


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
    _assert_gated_bound_points(n, k, mcoef, "<=", lower=False)


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
    _assert_gated_bound_points(n, k, mcoef, ">=", lower=True)


@pytest.mark.parametrize("n", [4, 5, 6])
def test_upper_gated_bound_no_pb_no_card(monkeypatch, n: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for gated upper-card fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for gated upper-card fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= (n * y))
    r = _solve(m)
    assert r.ok


@pytest.mark.parametrize("n", [4, 5, 6])
def test_upper_gated_bound_k_eq_1_no_pb_no_card(monkeypatch, n: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for canonical gated upper-card k=1 fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for canonical gated upper-card k=1 fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= (1 + ((n - 1) * y)))
    r = _solve(m)
    assert r.ok


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
    _assert_gated_bound_points(n, k, mcoef, "<", lower=False)


@pytest.mark.parametrize("n,k,mcoef", [
    (4, 2, 2),
    (5, 2, 3),
    (5, 3, 2),
])
def test_strict_lower_gated_bound_semantics(n: int, k: int, mcoef: int):
    _assert_gated_bound_points(n, k, mcoef, ">", lower=True)


@pytest.mark.parametrize("n", [4, 5, 6])
def test_swapped_orientation_upper_supported_no_pb_no_card(monkeypatch, n: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for swapped upper gated-card fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for swapped upper gated-card fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= ((n * y) >= _boolsum(xs))
    r = _solve(m)
    assert r.ok


def test_lower_gated_bound_supported_with_fallback():
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(5)]
    y = m.bool("y")
    m &= (_boolsum(xs) >= (1 + (4 * y)))
    r = _solve(m)
    assert r.ok


@pytest.mark.parametrize("n", [4, 5, 6])
def test_swapped_orientation_upper_k_eq_1_supported_no_pb_no_card(monkeypatch, n: int):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for swapped canonical upper gated-card k=1 fast path")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for swapped canonical upper gated-card k=1 fast path")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= ((1 + ((n - 1) * y)) >= _boolsum(xs))
    r = _solve(m)
    assert r.ok


@pytest.mark.parametrize("n,mcoef", [
    (4, 3),
    (5, 2),
    (6, 4),
])
def test_upper_gated_bound_all_but_one_true_boundary(n: int, mcoef: int):
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(n)]
    y = m.bool("y")
    m &= (_boolsum(xs) <= ((n - 1) + mcoef * y))
    m &= ~y
    for bit in xs:
        m &= bit
    r = _solve(m)
    assert r.status == "unsat"


@pytest.mark.parametrize("seed", [101, 102, 103])
def test_boolsum_bigm_randomized_point_checks(seed: int):
    rng = random.Random(seed)
    for _ in range(20):
        n = rng.randint(1, 6)
        k = rng.randint(-1, n + 1)
        mcoef = rng.randint(1, max(1, n))
        op = rng.choice(["<=", "<", ">=", ">"])
        bits = [rng.randint(0, 1) for _ in range(n)]
        gate = rng.randint(0, 1)

        m = Model()
        xs = [m.bool(f"x{i}") for i in range(n)]
        y = m.bool("y")
        lhs = _boolsum(xs)
        rhs = k + mcoef * y
        if op == "<=":
            m &= (lhs <= rhs)
            expected = sum(bits) <= k + mcoef * gate
        elif op == "<":
            m &= (lhs < rhs)
            expected = sum(bits) < k + mcoef * gate
        elif op == ">=":
            m &= (lhs >= rhs)
            expected = sum(bits) >= k + mcoef * gate
        else:
            m &= (lhs > rhs)
            expected = sum(bits) > k + mcoef * gate
        m &= (y if gate else ~y)
        for lit, bit in zip(xs, bits):
            m &= (lit if bit else ~lit)
        r = _solve(m)
        assert (r.ok if expected else r.status == "unsat"), (seed, n, k, mcoef, op, bits, gate)
