"""Soundness, allocation boundaries and exact costs of internal integer sums."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.internal import _integer_sum_native as native_encoder


def native():
    return native_encoder


def chains(widths):
    result = []
    top = 0
    for w in widths:
        result.append(list(range(top + 1, top + w + 1)))
        top += w
    return result, top


def domain(rows):
    return [[-b, a] for row in rows for a, b in zip(row, row[1:])]


@pytest.mark.parametrize("mode", [0, 1])
@pytest.mark.parametrize(
    "widths", [[0], [1], [3], [2, 3], [1, 2, 3], [3, 3, 3], [1, 2, 1, 3, 1]]
)
@pytest.mark.parametrize("negative", [False, True])
def test_every_assignment_including_invalid_order_values(mode, widths, negative):
    api = native()
    rows, top = chains(widths)
    oriented = [[-x for x in reversed(row)] for row in rows] if negative else rows
    for bound in sorted({-1, 0, 1, top // 2, top - 1, top, top + 1}):
        for modulus in [0, 2, 3, 5] if mode else [0]:
            clauses, nv = api.encode_order_sum(oriented, bound, top + 7, mode, modulus)
            assert nv >= top + 7
            assert all(
                0 < abs(l) <= nv and (abs(l) <= top or abs(l) > top + 7)
                for c in clauses
                for l in c
            )
            with Solver(name="g4", bootstrap_with=domain(rows) + clauses) as s:
                for bits in itertools.product([False, True], repeat=top):
                    valid = all(
                        not bits[b - 1] or bits[a - 1]
                        for row in rows
                        for a, b in zip(row, row[1:])
                    )
                    total = sum(bits) if not negative else top - sum(bits)
                    expected = valid and total <= bound
                    assert (
                        s.solve(
                            assumptions=[i if b else -i for i, b in enumerate(bits, 1)]
                        )
                        == expected
                    ), (widths, mode, bound, modulus, bits)


def test_estimates_and_modulus_selection_match_actual_counts():
    api = native()
    rng = random.Random(0x10A51)
    for widths in [[1, 2], [10] * 8] + [
        [rng.randint(1, 9) for _ in range(rng.randint(2, 6))] for _ in range(20)
    ]:
        rows, top = chains(widths)
        for bound in sorted({0, 1, top // 2, top - 1, top}):
            cost = api.assess_order_sum(widths, bound)
            for mode, name in [(0, "leaf"), (1, "whole")]:
                c, nv = api.encode_order_sum(rows, bound, top, mode, 0)
                assert cost[name + "_clauses"] == len(c)
                assert cost[name + "_variables"] == nv - top
            if 0 < bound < top - 1:
                all_costs = []
                for p in range(2, top + 2):
                    c, nv = api.encode_order_sum(rows, bound, top, 1, p)
                    all_costs.append((len(c), nv - top, p))
                assert (
                    cost["whole_clauses"],
                    cost["whole_variables"],
                    cost["modulus"],
                ) == min(all_costs)


@pytest.mark.parametrize("mode", [0, 1])
def test_sparse_signed_inputs_and_aliasing(mode):
    api = native()
    rows = [[3, -7, 11], [20, 23, -29], [31, 37]]
    top = 50
    for bound in [0, 1, 4, 7, 8]:
        c, nv = api.encode_order_sum(rows, bound, top, mode, 0)
        with Solver(name="g4", bootstrap_with=domain(rows) + c) as s:
            for values in itertools.product(*(range(len(row) + 1) for row in rows)):
                ass = [
                    l if j < v else -l
                    for row, v in zip(rows, values)
                    for j, l in enumerate(row)
                ]
                assert s.solve(assumptions=ass) == (sum(values) <= bound)


@pytest.mark.parametrize(
    "args",
    [
        ([[0]], 1, 3, 0, 0),
        ([[1], [1]], 1, 3, 0, 0),
        ([[True]], 1, 3, 0, 0),
        ([[1]], True, 3, 0, 0),
        ([[1]], 1, -1, 0, 0),
        ([[1]], 1, 3, 3, 0),
        ([[1]], 1, 3, 1, 1),
        ([[2**31]], 1, 3, 0, 0),
    ],
)
def test_invalid_native_inputs_are_rejected(args):
    with pytest.raises((ValueError, TypeError, OverflowError)):
        native().encode_order_sum(*args)


@pytest.mark.parametrize("comparator", ["<=", ">=", "=="])
@pytest.mark.parametrize(
    "coefficients", [[1, 1, 1], [-1, 1, 1], [-1, -1, 1], [-1, -1, -1]]
)
def test_binary_views_signed_sums_and_full_domain_ranges(comparator, coefficients):
    from hermax.encoder._integer_sum import encode_binary

    rows, top = chains([2, 3, 1])
    for bound in range(-7, 8):
        cnf = encode_binary(rows, bound, top + 9, comparator, coefficients)
        assert cnf.nv >= top + 9
        with Solver(name="g4", bootstrap_with=domain(rows) + cnf.clauses) as s:
            for values in itertools.product(range(3), range(4), range(2)):
                total = sum(c * v for c, v in zip(coefficients, values))
                expected = {
                    "<=": total <= bound,
                    ">=": total >= bound,
                    "==": total == bound,
                }[comparator]
                ass = [
                    l if i < v else -l
                    for row, v in zip(rows, values)
                    for i, l in enumerate(row)
                ]
                assert s.solve(assumptions=ass) == expected, (
                    comparator,
                    coefficients,
                    bound,
                    values,
                )


def test_binary_channel_cost_and_invalid_binary_values():
    from hermax.encoder._integer_sum.encoding import bit_channels, channel_cost

    for width in range(2, 33):
        row = list(range(1, width + 1))
        bits = list(range(width + 1, width + 1 + width.bit_length()))
        definitions = list(bit_channels(row, bits))
        assert sum(len(c) for _, c in definitions) == channel_cost(width)
        clauses = domain([row]) + [c for _, cs in definitions for c in cs]
        with Solver(name="g4", bootstrap_with=clauses) as s:
            for value in range(1 << len(bits)):
                ass = [bit if value & (1 << j) else -bit for j, bit in enumerate(bits)]
                assert s.solve(assumptions=ass) == (value <= width)


@pytest.mark.parametrize("mode", [0, 1, "binary"])
def test_random_wider_chains_against_integer_arithmetic(mode):
    """Cross quotient/carry boundaries well beyond the exhaustive tiny domains."""
    from hermax.encoder._integer_sum import encode_binary

    rng = random.Random(0xCA771E)
    for _ in range(36):
        widths = [rng.randint(1, 35) for _ in range(rng.randint(2, 9))]
        rows, top = chains(widths)
        signs = [rng.choice([-1, 1]) for _ in rows]
        oriented = [
            row if sign > 0 else [-l for l in reversed(row)]
            for row, sign in zip(rows, signs)
        ]
        bound = rng.randrange(top + 1)
        if mode == "binary":
            signed_bound = bound - sum(w for w, sign in zip(widths, signs) if sign < 0)
            encoded = encode_binary(rows, signed_bound, top, coefficients=signs)
            clauses = encoded.clauses
        else:
            clauses, _ = native().encode_order_sum(oriented, bound, top, mode)
        with Solver(name="g4", bootstrap_with=domain(rows) + clauses) as solver:
            for _ in range(80):
                values = [rng.randrange(w + 1) for w in widths]
                total = sum(
                    v if sign > 0 else w - v
                    for w, v, sign in zip(widths, values, signs)
                )
                assignment = [
                    l if j < value else -l
                    for row, value in zip(rows, values)
                    for j, l in enumerate(row)
                ]
                assert solver.solve(assumptions=assignment) == (total <= bound)


@pytest.mark.parametrize("widths", [[-1], [True], [2**31], [2**31 - 1, 1]])
def test_invalid_native_assessment_widths(widths):
    with pytest.raises((ValueError, TypeError, OverflowError)):
        native().assess_order_sum(widths, 1)


@pytest.mark.parametrize("mode", [0, 1])
def test_auxiliary_id_exhaustion_raises_instead_of_wrapping(mode):
    with pytest.raises(OverflowError):
        native().encode_order_sum([[1, 2, 3], [4, 5, 6]], 3, 2**31 - 1, mode)


def test_empty_and_zero_width_inputs_are_constants():
    for rows in [[], [[], []]]:
        for mode in [0, 1]:
            for bound in [-1, 0, 1]:
                clauses, top = native().encode_order_sum(rows, bound, 10, mode)
                assert clauses == ([[]] if bound < 0 else [])
                assert top == 10
                cost = native().assess_order_sum([len(row) for row in rows], bound)
                assert cost["whole_variables"] == cost["leaf_variables"] == 0
                assert cost["whole_clauses"] == cost["leaf_clauses"] == len(clauses)
