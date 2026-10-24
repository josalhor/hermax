"""Decision boundaries and arithmetic soundness of the propagation-weighted tree."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.encoder.pbamo import PBAMOEnc, choose_encoding


def grouped(n_groups, non_singletons, weights=(2, 3)):
    n = n_groups + non_singletons
    lits = [(-1 if i % 3 == 0 else 1) * (3*i + 2) for i in range(n)]
    groups = [lits[2*i:2*i+2] for i in range(non_singletons)]
    groups += [[l] for l in lits[2*non_singletons:]]
    ws = [weights[i % len(weights)] for i in range(n)]
    return lits, ws, groups


@pytest.mark.parametrize('groups,non_singletons,weights,bound,expected', [
    (24, 12, (2, 3), 2, 'gswc'),
    (25, 12, (2, 3), 2, 'rggt'),
    (24, 11, (2, 3), 3, 'mdd'),
    (24, 12, (2, 3), 3, 'rggt'),
    (24, 12, (6, 9), 8, 'gswc'),  # floor(8 / gcd(6,9)) == 2
    (24, 12, (6, 9), 9, 'rggt'),
    (25, 0, (2,), 191, 'rggt'),  # reduced bound 95
    (25, 0, (2,), 192, 'mdd'),   # reduced bound 96
    (25, 0, (16,), 1, 'ggpw'),
    (25, 0, (15,), 1, 'rggt'),
])
def test_decision_boundaries(groups, non_singletons, weights, bound, expected):
    lits, ws, partition = grouped(groups, non_singletons, weights)
    assert choose_encoding(lits, ws, partition, bound) == expected


@pytest.mark.parametrize('last_weight,expected', [(26, 'mdd'), (27, 'ggpw')])
def test_exact_mean_weight_threshold(last_weight, expected):
    lits = list(range(1, 65))
    weights = [15]*63 + [last_weight]
    # Sum 971 gives precisely the fitted threshold 971/64 = 15.171875.
    assert choose_encoding(lits, weights, [[l] for l in lits], 100) == expected


@pytest.mark.parametrize('lits,weights,groups', [([], [], []), ([1, -2], [0, 0], [[1, -2]])])
def test_empty_and_zero_weights(lits, weights, groups):
    assert choose_encoding(lits, weights, groups, 0) == 'gswc'
    if not lits:
        assert PBAMOEnc.leq(lits, weights, groups, 0).clauses == []


@pytest.mark.parametrize('n_groups,non_singletons,weights,bound,expected', [
    (4, 4, (2, 3), 8, 'mdd'),
    (8, 8, (2, 3), 2, 'gswc'),
    (13, 13, (2, 3), 20, 'rggt'),
    (25, 25, (20, 21), 300, 'ggpw'),
])
def test_best_encodings_match_independent_arithmetic(n_groups, non_singletons, weights, bound, expected):
    lits, ws, groups = grouped(n_groups, non_singletons, weights)
    assert choose_encoding(lits, ws, groups, bound) == expected
    cnf = PBAMOEnc.leq(lits, ws, groups, bound, encoding='best', emit_amo=True)
    rng = random.Random(0x22B0 + n_groups)
    free = set(map(abs, lits[:4]))
    cap = sum(max(ws[lits.index(l)] for l in g) for g in groups)
    with Solver(name='g4', bootstrap_with=cnf.clauses) as solver:
        for _ in range(12):
            active = set()
            for group in groups:
                if rng.random() < min(.5, bound/max(1, cap)):
                    active.add(rng.choice(group))
            fixed = {abs(l): l in active if l > 0 else l not in active for l in lits if abs(l) not in free}
            for bits in itertools.product([False, True], repeat=len(free)):
                assignment = {**fixed, **dict(zip(sorted(free), bits))}
                truth = lambda l: assignment[abs(l)] == (l > 0)
                expected_sat = sum(w for l,w in zip(lits, ws) if truth(l)) <= bound
                expected_sat &= all(sum(truth(l) for l in group) <= 1 for group in groups)
                assumptions = [v if b else -v for v,b in assignment.items()]
                assert solver.solve(assumptions=assumptions) == expected_sat
