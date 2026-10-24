"""Soundness and size regressions for native PB coefficient normalization."""
from __future__ import annotations

import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.internal import _pblib


ENCODERS = [
    _pblib.PB_BEST, _pblib.PB_BDD, _pblib.PB_SWC,
    _pblib.PB_SORTINGNETWORKS, _pblib.PB_ADDER,
    _pblib.PB_BINARY_MERGE, _pblib.PB_LPW,
]
COMPARATORS = [_pblib.LEQ, _pblib.GEQ, _pblib.BOTH]


def encode(terms, comparator, bound, encoder, conditions=(), top_id=8):
    return _pblib.encode_pb(
        wlits=list(terms), comparator=comparator, bound=bound,
        top_id=top_id, pb_encoder=encoder, conditionals=list(conditions),
    )


@pytest.mark.parametrize("encoder", ENCODERS)
@pytest.mark.parametrize("comparator", COMPARATORS)
def test_common_factor_produces_the_same_encoding_as_reduced_input(encoder, comparator):
    terms = [(1, 2), (-2, 3), (3, 5), (4, 7), (5, 11)]
    offset = {_pblib.LEQ: 5, _pblib.GEQ: -5, _pblib.BOTH: 0}[comparator]
    actual = encode([(l, w * 6) for l, w in terms], comparator, 13 * 6 + offset, encoder)
    expected = encode(terms, comparator, 13, encoder)
    assert actual == expected


def assert_truth_table(terms, comparator, bound, encoder, conditions=(), n=5):
    clauses, nv = encode(terms, comparator, bound, encoder, conditions, top_id=12)
    assert nv >= 12
    assert all(0 < abs(l) <= nv for c in clauses for l in c)
    assert all(abs(l) <= n or abs(l) > 12 for c in clauses for l in c)
    with Solver(name="g4", bootstrap_with=clauses) as solver:
        for bits in itertools.product((False, True), repeat=n):
            def value(lit):
                return bits[abs(lit) - 1] == (lit > 0)
            total = sum(w for l, w in terms if value(l))
            expected = {
                _pblib.LEQ: total <= bound,
                _pblib.GEQ: total >= bound,
                _pblib.BOTH: total == bound,
            }[comparator]
            expected = not all(value(l) for l in conditions) or expected
            assumptions = [i if b else -i for i, b in enumerate(bits, 1)]
            assert solver.solve(assumptions=assumptions) == expected, (
                terms, comparator, bound, conditions, assumptions, encoder,
            )


@pytest.mark.parametrize("encoder", ENCODERS)
def test_normalization_matches_independent_exhaustive_arithmetic(encoder):
    rng = random.Random(0x6CD)
    cases = [
        ([], -1), ([], 0),
        ([(1, 0), (-2, 0)], 0),
        ([(1, 6), (-1, 12), (2, -6), (2, 6)], 7),
        ([(1, 6), (-2, 12), (3, 18)], -1),
        ([(1, 6), (-2, 12), (3, 18)], 13),
        ([(1, 6), (-2, 12), (3, 18)], 36),
        ([(1, 6), (-2, 12), (3, 18)], 100),
    ]
    for _ in range(32):
        terms = [(rng.choice((-1, 1)) * rng.randrange(1, 5), rng.randrange(-5, 6) * 6)
                 for _ in range(rng.randrange(1, 9))]
        cases.append((terms, rng.randrange(-20, 21) * 6 + rng.randrange(2)))
    for terms, bound in cases:
        for comparator in COMPARATORS:
            for conditions in ((), (5,), (-5,), (1, -5)):
                assert_truth_table(terms, comparator, bound, encoder, conditions)


@pytest.mark.parametrize("encoder", [
    _pblib.PB_BEST, _pblib.PB_BDD, _pblib.PB_ADDER,
    _pblib.PB_BINARY_MERGE, _pblib.PB_LPW,
])
@pytest.mark.parametrize("comparator", COMPARATORS)
def test_large_common_factors_do_not_truncate_or_overflow(encoder, comparator):
    factor = 1 << 55
    terms = [(1, 2 * factor), (-2, 3 * factor), (3, 5 * factor)]
    for offset in (-1, 0, 1):
        assert_truth_table(terms, comparator, 5 * factor + offset, encoder, (5,))
