from __future__ import annotations

import itertools
import random

import pytest

from hermax.model import Model


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


@pytest.mark.parametrize("op", ("<=", "<"))
@pytest.mark.parametrize("swapped", (False, True))
def test_boolsum_bigm_negated_indicator_matches_every_assignment(op: str, swapped: bool):
    """A negated indicator must select the relaxed Big-M branch when true."""
    flipped = {"<=": ">=", "<": ">"}[op]
    for values in itertools.product((False, True), repeat=4):
        m = Model()
        b = [m.bool(f"b_{idx}") for idx in range(3)]
        gate = m.bool("gate")
        total = b[0] + b[1] + b[2]
        bound = 1 + 3 * ~gate
        m &= _compare(bound, flipped, total) if swapped else _compare(total, op, bound)
        for lit, value in zip([*b, gate], values):
            m &= lit if value else ~lit

        expected = _eval_compare(sum(values[:3]), op, 1 + 3 * int(not values[3]))
        assert m.solve().ok == expected, (op, swapped, values, expected)


@pytest.mark.parametrize("op", ("<=", "<", ">=", ">"))
@pytest.mark.parametrize("swapped", (False, True))
def test_mixed_bigm_negated_indicator_matches_every_assignment(op: str, swapped: bool):
    """Mixed Big-M bounds must be sound for both polarities of the indicator."""
    flipped = {"<=": ">=", "<": ">", ">=": "<=", ">": "<"}[op]
    for x_value in range(4):
        for bit_value, gate_value in itertools.product((False, True), repeat=2):
            m = Model()
            x = m.int("x", 0, 3)
            bit = m.bool("bit")
            gate = m.bool("gate")
            main = 2 * x + bit
            bound = 2 + 3 * ~gate
            m &= _compare(bound, flipped, main) if swapped else _compare(main, op, bound)
            m &= (x == x_value)
            m &= bit if bit_value else ~bit
            m &= gate if gate_value else ~gate

            expected = _eval_compare(2 * x_value + int(bit_value), op, 2 + 3 * int(not gate_value))
            assert m.solve().ok == expected, (op, swapped, x_value, bit_value, gate_value, expected)


def test_boolsum_bigm_negated_indicator_randomized_points():
    rng = random.Random(20260722)
    for _ in range(40):
        n_bools = rng.randint(2, 6)
        op = rng.choice(("<=", "<"))
        tight_bound = rng.choice((0, 1))
        mcoef = n_bools + rng.randint(1, 4)
        swapped = rng.choice((False, True))
        values = [rng.choice((False, True)) for _ in range(n_bools + 1)]

        m = Model()
        b = [m.bool(f"b_{idx}") for idx in range(n_bools)]
        gate = m.bool("gate")
        total = sum(b)
        bound = tight_bound + mcoef * ~gate
        flipped = {"<=": ">=", "<": ">"}[op]
        m &= _compare(bound, flipped, total) if swapped else _compare(total, op, bound)
        for lit, value in zip([*b, gate], values):
            m &= lit if value else ~lit

        expected = _eval_compare(sum(values[:-1]), op, tight_bound + mcoef * int(not values[-1]))
        assert m.solve().ok == expected, (op, swapped, n_bools, tight_bound, mcoef, values, expected)


def test_mixed_bigm_negated_indicator_randomized_points():
    rng = random.Random(20260722)
    for _ in range(40):
        n_bools = rng.randint(1, 4)
        a = rng.choice((-2, -1, 1, 2, 3))
        op = rng.choice(("<=", "<", ">=", ">"))
        bound_offset = rng.randint(-3, 6)
        mcoef = rng.randint(1, 6)
        swapped = rng.choice((False, True))
        x_value = rng.randint(-2, 3)
        bool_values = [rng.choice((False, True)) for _ in range(n_bools + 1)]

        m = Model()
        x = m.int("x", -2, 3)
        b = [m.bool(f"b_{idx}") for idx in range(n_bools)]
        gate = m.bool("gate")
        main = a * x + sum(b)
        bound = bound_offset + mcoef * ~gate
        flipped = {"<=": ">=", "<": ">", ">=": "<=", ">": "<"}[op]
        m &= _compare(bound, flipped, main) if swapped else _compare(main, op, bound)
        m &= (x == x_value)
        for lit, value in zip([*b, gate], bool_values):
            m &= lit if value else ~lit

        expected = _eval_compare(
            a * x_value + sum(bool_values[:-1]),
            op,
            bound_offset + mcoef * int(not bool_values[-1]),
        )
        assert m.solve().ok == expected, (op, swapped, a, bound_offset, mcoef, x_value, bool_values, expected)
