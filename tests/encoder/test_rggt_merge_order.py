"""The faster tree selector must preserve RGGT's merge order and encoding."""
import hashlib
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.internal import _pbamo


@pytest.mark.parametrize("n,bound,method,nv,count,digest", [
    (8, 0, "encode_leq", 103, 24, "40f48aa6682024bf081e92ff7e9fb1e473f55db5c09b62f2bbf4e51ebb9a228d"),
    (8, 0, "encode_eq", 100, 20, "2436a8ae70bb56d98edddcc645981115895fa051d5b04fa16a265190f396df47"),
    (16, 9, "encode_leq", 114, 91, "3f1c2ca74b80949db522dd0c2e592d4c83d1fc078f3fbbd0a5ca8b45701b0c49"),
    (16, 9, "encode_eq", 119, 138, "9f21e76ed26e32f0752c8dd82c51c660b43d1f713c8267876afcfdf224c22f27"),
    (64, 23, "encode_leq", 391, 1398, "69006b057a735c8ba5682f92fb8b60b33fa29bd8ab47ceb1e5761620944972b3"),
    (64, 23, "encode_eq", 412, 2594, "b308acb414d64a6c25c948a19353ae520306a47fd284b922f161c817689e83a8"),
])
def test_rggt_tree_selection_preserves_exact_cnf(n, bound, method, nv, count, digest):
    rng = random.Random(n)
    lits = [i * rng.choice([-1, 1]) for i in range(1, n + 1)]
    rng.shuffle(lits)
    weights = [rng.randint(1, 9) for _ in lits]
    groups = [lits[i:i + 4] for i in range(0, n, 4)]
    clauses, actual_nv = getattr(_pbamo, method)(
        wlits=list(zip(lits, weights)), groups=groups, bound=bound,
        top_id=100, encoder="rggt", emit_amo=True,
    )
    result = hashlib.sha256()
    for row in clauses:
        result.update((str(tuple(row)) + "\n").encode())
    assert (actual_nv, len(clauses), result.hexdigest()) == (nv, count, digest)


@pytest.mark.parametrize("method", ["encode_leq", "encode_eq"])
def test_rggt_merged_tree_matches_exhaustive_arithmetic(method):
    rng = random.Random(738)
    for _ in range(20):
        lits = [i * rng.choice([-1, 1]) for i in range(1, 8)]
        weights = [rng.randint(1, 9) for _ in lits]
        groups = [lits[:2], lits[2:5], lits[5:]]
        bound = rng.randint(0, 20)
        clauses, _ = getattr(_pbamo, method)(
            wlits=list(zip(lits, weights)), groups=groups, bound=bound,
            top_id=20, encoder="rggt", emit_amo=True,
        )
        with Solver(bootstrap_with=clauses) as solver:
            for bits in itertools.product([False, True], repeat=7):
                active = dict(zip(lits, bits))
                total = sum(w for w, bit in zip(weights, bits) if bit)
                expected = total <= bound if method == "encode_leq" else total == bound
                expected &= all(sum(active[lit] for lit in group) <= 1 for group in groups)
                assert solver.solve(assumptions=[lit if bit else -lit for lit, bit in zip(lits, bits)]) == expected
