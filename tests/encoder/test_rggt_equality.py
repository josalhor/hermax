"""Native grouped equality: independent arithmetic and propagation regressions."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.encoder.pbamo import PBAMOEnc
from hermax.encoder.pb_enc import PBEnc
from hermax.internal import _pbamo


def encode(lits, weights, groups, bound, emit_amo=True, top_id=19):
    return _pbamo.encode_eq(
        wlits=list(zip(lits, weights)), groups=groups, bound=bound,
        top_id=top_id, encoder='rggt', emit_amo=emit_amo,
    )


def check(lits, weights, groups, bound, emit_amo=True, top_id=19):
    clauses, nv = encode(lits, weights, groups, bound, emit_amo, top_id)
    n = max(map(abs, lits), default=0)
    assert nv >= max(n, top_id)
    assert all(0 < abs(l) <= nv and (abs(l) <= n or abs(l) > top_id) for c in clauses for l in c)
    external_amo = [[-a, -b] for g in groups for a, b in itertools.combinations(g, 2)]
    with Solver(name='g4', bootstrap_with=clauses + external_amo) as solver:
        for bits in itertools.product([False, True], repeat=n):
            active = lambda l: bits[abs(l)-1] == (l > 0)
            expected = sum(w for l, w in zip(lits, weights) if active(l)) == bound
            expected &= all(sum(active(l) for l in g) <= 1 for g in groups)
            assert solver.solve(assumptions=[i if b else -i for i, b in enumerate(bits, 1)]) == expected, (
                lits, weights, groups, bound, bits, emit_amo,
            )
    return clauses, nv


@pytest.mark.parametrize('emit_amo', [False, True])
@pytest.mark.parametrize('weights, groups, bound', [
    ([], [], 0), ([], [], 1),
    ([3], [[1]], 0), ([3], [[1]], 3), ([3], [[1]], 2),
    ([2, 3], [[1], [2]], 5), ([2, 3], [[1], [2]], 4),
    ([2, 3], [[1, 2]], 5), ([2, 3], [[1, 2]], 3),
    ([3, 3, 7], [[1, 2, 3]], 3),
    ([2, 4, 6], [[1], [2], [3]], 5),
    ([2, 4, 6], [[1], [2], [3]], 6),
    ([1, 2, 4, 8], [[1, 2], [3, 4]], 9),
    ([7, 11, 13], [[1], [2], [3]], 100),
    ([2**32 + 1, 1], [[1], [2]], 1),
    ([2**63, 2**63 - 1], [[1], [2]], 2**64 - 1),
    ([2**64 - 1, 1], [[1], [2]], 0),
    ([2**64 - 1, 1], [[1], [2]], 2**64 - 1),
])
def test_edges_match_independent_arithmetic(weights, groups, bound, emit_amo):
    check(list(range(1, len(weights)+1)), weights, groups, bound, emit_amo)


@pytest.mark.parametrize('emit_amo', [False, True])
def test_signed_and_complementary_literals(emit_amo):
    for lits, groups in [([1, -2, 3], [[1, -2], [3]]),
                         ([1, -1, 2], [[1], [-1], [2]]),
                         ([1, -1, 2], [[1, -1], [2]])]:
        for bound in range(11):
            check(lits, [2, 3, 5], groups, bound, emit_amo)


@pytest.mark.parametrize('seed', range(40))
def test_random_grouped_equalities(seed):
    rng = random.Random(f'rggt-eq:{seed}')
    lits = [i*rng.choice([-1, 1]) for i in range(1, 7)]
    weights = [rng.randint(1, 20)*rng.choice([1, 1, 6]) for _ in lits]
    width = rng.choice([1, 2, 3, 6])
    groups = [lits[i:i+width] for i in range(0, 6, width)]
    # Include both reachable and unreachable targets; do not assume group validity.
    for bound in {0, sum(weights), sum(weights)+1, sum(weights[::2]), rng.randrange(sum(weights)+1)}:
        check(lits, weights, groups, bound, bool(seed % 2))


def test_public_equals_and_reserved_ids():
    result = PBAMOEnc.equals([1, -8, 12], [2, 3, 5], [[1], [-8], [12]], 5, top_id=20)
    expected = encode([1, -8, 12], [2, 3, 5], [[1], [-8], [12]], 5, top_id=20)
    assert (result.clauses, result.nv) == expected
    assert encode([1, 2], [2, 3], [[1], [2]], 3, top_id=0) == encode([1, 2], [2, 3], [[1], [2]], 3, top_id=2)
    assert encode([1, 2], [2, 3], [[1], [2]], 3) == encode([1, 2], [2, 3], [[1], [2]], 3)


def test_default_equality_route_remains_pblib(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('auto_eq unexpectedly routed into the experimental native equality path')
    monkeypatch.setattr(_pbamo, 'encode_eq', forbidden)
    result = PBAMOEnc.auto_eq(lits=[1, 2, 3], weights=[2, 3, 5], bound=5)
    expected = PBEnc.equals([1, 2, 3], [2, 3, 5], 5, top_id=3)
    assert (result.clauses, result.nv) == (expected.clauses, expected.nv)


def unit_propagate(clauses, assumptions):
    known = set(assumptions)
    while True:
        changed = False
        for clause in clauses:
            if any(l in known for l in clause):
                continue
            remaining = [l for l in clause if -l not in known]
            if not remaining:
                return None
            if len(remaining) == 1 and remaining[0] not in known:
                known.add(remaining[0]); changed = True
        if not changed:
            return known


def test_equality_shares_information_between_both_directions():
    weights = [1, 4, 4, 2, 4, 5, 2, 1]
    lits = list(range(1, 9)); groups = [[l] for l in lits]
    clauses, _ = encode(lits, weights, groups, 11)
    result = unit_propagate(clauses, [-1, -2, -3])
    assert result is not None and -8 in result


@pytest.mark.parametrize('kwargs', [
    dict(bound=-1), dict(top_id=-1), dict(encoder='mdd'),
    dict(groups=[[1, 2], [2]]), dict(wlits=[(1, 0), (2, 1)]),
])
def test_native_rejects_invalid_input(kwargs):
    args = dict(wlits=[(1, 1), (2, 2)], groups=[[1], [2]], bound=1,
                top_id=2, encoder='rggt', emit_amo=True)
    args.update(kwargs)
    with pytest.raises((ValueError, RuntimeError, OverflowError)):
        _pbamo.encode_eq(**args)


@pytest.mark.parametrize('seed', range(12))
def test_term_and_group_order_do_not_change_solutions(seed):
    rng = random.Random(seed)
    lits = [1, -2, 3, -4, 5, -6]
    weights = [3, 3, 5, 8, 11, 13]
    groups = [lits[:2], lits[2:4], lits[4:]]
    pairs = list(zip(lits, weights)); rng.shuffle(pairs)
    rng.shuffle(groups)
    for group in groups:
        rng.shuffle(group)
    reordered_lits, reordered_weights = map(list, zip(*pairs))
    for bound in (0, 8, 16, 24, 43):
        check(reordered_lits, reordered_weights, groups, bound, bool(seed % 2))


def test_invalid_partition_is_rejected_even_when_gcd_proves_unsat():
    with pytest.raises(RuntimeError, match='partition|exactly one|group'):
        encode([1, 2], [2, 4], [[1], [1]], 3)


@pytest.mark.parametrize('seed', range(20))
def test_unsigned_sum_overflow_cannot_create_a_spurious_solution(seed):
    rng = random.Random(0xFFFF + seed)
    weights = [rng.randrange(2**63 - 100, 2**63 + 100) for _ in range(6)]
    lits = [i*rng.choice([-1, 1]) for i in range(1, 7)]
    width = rng.choice([1, 2, 3])
    groups = [lits[i:i+width] for i in range(0, 6, width)]
    for bound in {weights[0], min(weights[0]+weights[1], 2**64-1), 2**64-1}:
        check(lits, weights, groups, bound, bool(seed % 2))
