"""RGGT tree-search optimizations preserve arithmetic and auxiliary ID ranges."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.internal import _pbamo


def cases():
    rng = random.Random(0xCA4E)
    for i in range(64):
        lits = [j * rng.choice([-1, 1]) for j in range(1, 8)]
        weights = [rng.randint(1, 30) for _ in lits]
        if i % 4 == 0:
            weights = [rng.choice([1, 2, 4, 8, 16]) for _ in lits]
        if i % 4 == 1:
            weights = [rng.choice([7, 11]) for _ in lits]
        width = 1 + i % 4
        yield dict(lits=lits, weights=weights,
                   groups=[lits[j:j + width] for j in range(0, 7, width)],
                   bound=rng.randrange(sum(weights) + 2), emit_amo=bool(i % 2))


def encode(case):
    return _pbamo.encode_leq(
        wlits=list(zip(case['lits'], case['weights'])), groups=case['groups'],
        bound=case['bound'], top_id=27, encoder='rggt', emit_amo=case['emit_amo'],
    )


@pytest.mark.parametrize('case', list(cases()))
def test_merge_cache_preserves_all_original_assignments(case):
    clauses, nv = encode(case)
    assert all(0 < abs(l) <= nv and (abs(l) <= 7 or abs(l) > 27) for c in clauses for l in c)
    amo = [[-a, -b] for g in case['groups'] for a, b in itertools.combinations(g, 2)]
    with Solver(name='g4', bootstrap_with=clauses + amo) as solver:
        for bits in itertools.product([False, True], repeat=7):
            active = lambda l: bits[abs(l) - 1] == (l > 0)
            expected = sum(w for l, w in zip(case['lits'], case['weights']) if active(l)) <= case['bound']
            expected &= all(sum(active(l) for l in g) <= 1 for g in case['groups'])
            assert solver.solve(assumptions=[i if b else -i for i, b in enumerate(bits, 1)]) == expected
