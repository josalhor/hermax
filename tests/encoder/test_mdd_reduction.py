"""MDD ordering, structural reduction, literal reuse, and arithmetic soundness."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.internal import _pbamo


def encode(lits, weights, groups, bound, emit_amo=True, top_id=24):
    return _pbamo.encode_leq(wlits=list(zip(lits, weights)), groups=groups, bound=bound,
                            top_id=top_id, encoder='mdd', emit_amo=emit_amo)


def test_literal_nodes_reuse_the_original_literal():
    for lit in [7, -7]:
        clauses, nv = encode([lit], [3], [[lit]], 0, top_id=19)
        assert clauses == [[-lit]]
        assert nv == 19


def test_descending_weight_order_avoids_duplicate_power_states():
    lits = list(range(1, 17)); weights = [2**i for i in range(16)]
    clauses, nv = encode(lits, weights, [[l] for l in lits], 2**15-1, top_id=16)
    assert clauses == [[-16]]
    assert nv == 16


def test_identical_subgraphs_are_shared_across_remaining_budgets():
    rng = random.Random('weighted-defaults:narrow_weights:32:0')
    # Match the benchmark generator's initial draw before its family override.
    for _ in range(32):
        rng.randint(1, 30)
    weights = [rng.randint(995, 1005) for _ in range(32)]
    lits = list(range(1, 33))
    clauses, nv = encode(lits, weights, [[l] for l in lits], sum(weights)//2, top_id=32)
    assert nv-32 <= 1400
    assert len(clauses) <= 2800


def reduction_cases():
    rng = random.Random(0x4DD)
    for i in range(48):
        lits = [j*rng.choice([-1, 1]) for j in range(1, 8)]
        weights = [rng.randint(1, 30) for _ in lits]
        shuffled = rng.sample(lits, len(lits))
        width = 1 + i % 7
        yield dict(lits=lits, weights=weights,
                   groups=[shuffled[j:j+width] for j in range(0, 7, width)],
                   bound=rng.randrange(sum(weights)+2), emit_amo=bool(i % 2))


@pytest.mark.parametrize('case', list(reduction_cases()))
def test_reduction_preserves_arithmetic(case):
    lits, weights, groups, bound = (case[k] for k in ['lits', 'weights', 'groups', 'bound'])
    clauses, nv = encode(lits, weights, groups, bound, case['emit_amo'])
    assert all(0 < abs(l) <= nv and (abs(l) <= 7 or abs(l) > 24) for c in clauses for l in c)
    amo = [[-a, -b] for g in groups for a, b in itertools.combinations(g, 2)]
    with Solver(name='g4', bootstrap_with=clauses+amo) as solver:
        for bits in itertools.product([False, True], repeat=7):
            active = lambda l: bits[abs(l)-1] == (l > 0)
            expected = sum(w for l, w in zip(lits, weights) if active(l)) <= bound
            expected &= all(sum(active(l) for l in g) <= 1 for g in groups)
            assert solver.solve(assumptions=[i if b else -i for i, b in enumerate(bits, 1)]) == expected


@pytest.mark.parametrize('lits, weights, groups, bound', [
    ([], [], [], 0), ([], [], [], 1),
    ([1, -1], [2, 3], [[1], [-1]], 2),
    ([1, -1], [2, 3], [[1, -1]], 1),
    ([1, -2, 3], [2, 2, 3], [[1, -2], [3]], 3),
    ([1, 2], [2**64-1, 1], [[1], [2]], 2**64-1),
    ([1, 2], [2**63, 2**63+1], [[1], [2]], 2**64-1),
    ([1, 2, 3], [2**63, 2**63-1, 1], [[1, 2], [3]], 2**64-1),
])
@pytest.mark.parametrize('emit_amo', [False, True])
def test_edges_and_unsigned_sum_overflow(lits, weights, groups, bound, emit_amo):
    clauses, nv = encode(lits, weights, groups, bound, emit_amo)
    n = max(map(abs, lits), default=0)
    amo = [[-a, -b] for g in groups for a, b in itertools.combinations(g, 2)]
    with Solver(name='g4', bootstrap_with=clauses+amo) as solver:
        for bits in itertools.product([False, True], repeat=n):
            active = lambda l: bits[abs(l)-1] == (l > 0)
            expected = sum(w for l,w in zip(lits, weights) if active(l)) <= bound
            expected &= all(sum(active(l) for l in g) <= 1 for g in groups)
            assert solver.solve(assumptions=[i if b else -i for i,b in enumerate(bits, 1)]) == expected


def test_canonical_key_preserves_literal_identities():
    # Identical child shapes on different input literals must not be conflated.
    lits = [1, -2, 3, -4, 5, -6]
    weights = [5, 5, 3, 3, 1, 1]
    groups = [[l] for l in lits]
    first = encode(lits, weights, groups, 8)
    assert first == encode(lits, weights, groups, 8)
    with Solver(name='g4', bootstrap_with=first[0]) as solver:
        for bits in itertools.product([False, True], repeat=6):
            total = sum(w for l,w in zip(lits,weights) if bits[abs(l)-1] == (l>0))
            assert solver.solve(assumptions=[i if b else -i for i,b in enumerate(bits,1)]) == (total<=8)


def propagate(clauses, assumptions):
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
            return {l for l in known if abs(l) <= 6}


@pytest.mark.parametrize('seed', range(12))
def test_reduced_mdd_retains_gac_on_original_variables(seed):
    rng = random.Random(0x4DD00 + seed)
    lits = [i*rng.choice([-1, 1]) for i in range(1, 7)]
    weights = [rng.randint(1, 15) for _ in lits]
    width = rng.choice([1, 2, 3])
    groups = [lits[i:i+width] for i in range(0, 6, width)]
    bound = rng.randint(0, sum(weights))
    clauses, _ = encode(lits, weights, groups, bound, bool(seed % 2))
    clauses += [[-a, -b] for g in groups for a, b in itertools.combinations(g, 2)]
    solutions = []
    for bits in itertools.product([False, True], repeat=6):
        active = lambda l: bits[abs(l)-1] == (l > 0)
        if sum(w for l,w in zip(lits, weights) if active(l)) <= bound and all(sum(active(l) for l in g) <= 1 for g in groups):
            solutions.append({i if b else -i for i,b in enumerate(bits,1)})
    for vals in itertools.product([-1, 0, 1], repeat=6):
        assumptions = {i*v for i,v in enumerate(vals,1) if v}
        compatible = [s for s in solutions if assumptions <= s]
        expected = set.intersection(*compatible) if compatible else None
        assert propagate(clauses, assumptions) == expected, (lits, weights, groups, bound, assumptions)
