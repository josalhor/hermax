"""Python regressions for PBAMO boundaries and compact counter construction."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.internal import _pbamo

ENCODERS = ['mdd', 'gswc', 'ggpw', 'gmto', 'rggt']


def encode(weights, bound, encoder, *, lits=None, groups=None, top_id=None, emit_amo=True):
    lits = list(range(1, len(weights) + 1)) if lits is None else lits
    return _pbamo.encode_leq(
        wlits=list(zip(lits, weights)), groups=groups or [[l] for l in lits],
        bound=bound, top_id=max(map(abs, lits), default=0) if top_id is None else top_id,
        encoder=encoder, emit_amo=emit_amo,
    )


@pytest.mark.parametrize('encoder', ENCODERS)
def test_negative_bound_is_rejected(encoder):
    with pytest.raises((ValueError, OverflowError), match='bound|negative|unsigned'):
        encode([1, 2], -1, encoder)


@pytest.mark.parametrize('encoder', ENCODERS)
def test_small_top_id_does_not_alias_inputs(encoder):
    assert encode([1, 2, 3], 3, encoder, top_id=0) == encode([1, 2, 3], 3, encoder)
    assert encode([1, 2, 3], 3, encoder, lits=[-2, 8, -19], top_id=1) == encode(
        [1, 2, 3], 3, encoder, lits=[-2, 8, -19])


def test_gswc_preserves_wide_weights():
    clauses, _ = encode([2**32 + 1, 1], 1, 'gswc')
    with Solver(name='g4', bootstrap_with=clauses) as solver:
        assert not solver.solve(assumptions=[1, -2])
        assert solver.solve(assumptions=[-1, 2])


@pytest.mark.parametrize('encoder', ['gswc', 'ggpw'])
@pytest.mark.parametrize('emit_amo', [False, True])
def test_compact_encoders_match_exhaustive_arithmetic(encoder, emit_amo):
    rng = random.Random(303)
    cases = [([1, 2, 3, 4, 5], k, width) for k in (0, 1, 7, 15, 18) for width in (1, 2, 5)]
    cases += [([rng.randint(1, 25) for _ in range(5)], rng.randint(0, 100), rng.choice([1, 2, 5])) for _ in range(40)]
    for weights, bound, width in cases:
        lits = [i * rng.choice([-1, 1]) for i in range(1, 6)]
        groups = [lits[i:i + width] for i in range(0, 5, width)]
        clauses, nv = encode(weights, bound, encoder, lits=lits, groups=groups, top_id=12, emit_amo=emit_amo)
        assert all(0 < abs(l) <= nv and (abs(l) <= 5 or abs(l) > 12) for c in clauses for l in c)
        external_amo = [[-a, -b] for g in groups for a, b in itertools.combinations(g, 2)]
        with Solver(name='g4', bootstrap_with=clauses + external_amo) as solver:
            for bits in itertools.product([False, True], repeat=5):
                active = lambda l: bits[abs(l) - 1] == (l > 0)
                expected = sum(w for l, w in zip(lits, weights) if active(l)) <= bound
                expected &= all(sum(active(l) for l in g) <= 1 for g in groups)
                assumptions = [i if b else -i for i, b in enumerate(bits, 1)]
                assert solver.solve(assumptions=assumptions) == expected, (weights, bound, groups, assumptions)


@pytest.mark.parametrize('encoder, max_clauses, max_aux', [('gswc', 180000, 90000), ('ggpw', 21500, 3200)])
def test_counter_size_regression(encoder, max_clauses, max_aux):
    weights = [random.Random(i + 77).randint(1, 30) for i in range(128)]
    clauses, nv = encode(weights, sum(weights) // 2, encoder)
    assert len(clauses) <= max_clauses
    assert nv - len(weights) <= max_aux


@pytest.mark.parametrize('encoder', ENCODERS)
def test_public_boundary_matches_native(encoder):
    from hermax.encoder.pbamo import PBAMOEnc

    with pytest.raises((ValueError, OverflowError)):
        PBAMOEnc.leq([1, 2], [1, 2], [[1], [2]], -1, encoding=encoder)
    result = PBAMOEnc.leq([1, 2, 3], [1, 2, 3], [[1], [2], [3]], 3, top_id=0, encoding=encoder)
    assert (result.clauses, result.nv) == encode([1, 2, 3], 3, encoder)


def test_gswc_rejects_unrepresentable_counter_dimensions():
    with pytest.raises(RuntimeError, match='dimensions'):
        encode([1, 2**32 + 1], 2**32, 'gswc')


@pytest.mark.parametrize('lit', [2**31, -(2**31), 2**40, -(2**40)])
def test_native_rejects_unrepresentable_literals(lit):
    with pytest.raises(ValueError, match='literal ID'):
        encode([1], 0, 'mdd', lits=[lit], top_id=0)


@pytest.mark.parametrize('top_id', [-1, 2**31 - 1])
def test_native_rejects_invalid_top_id(top_id):
    with pytest.raises(ValueError, match='top_id'):
        encode([1, 2], 1, 'gswc', top_id=top_id)


def test_auxiliary_id_exhaustion_is_rejected():
    with pytest.raises(RuntimeError, match='variable ID'):
        encode([1, 2, 3], 3, 'gswc', top_id=2**31 - 2)
