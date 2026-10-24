"""BDD and RGGT optimizations preserve independent arithmetic truth tables."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.internal import _pbamo, _pblib


def optimization_cases():
    rng = random.Random(0xBDD)
    for kind in ['bdd', 'rggt']:
        for i in range(8):
            lits = [j*rng.choice([-1, 1]) for j in range(1, 7)]
            weights = [1] + [rng.randint(1, 30) for _ in range(5)]
            width = 1 + i % 3
            yield dict(kind=kind, lits=lits, weights=weights,
                       groups=[lits[j:j+width] for j in range(0, 6, width)],
                       bound=rng.randrange(sum(weights)+1), top_id=12,
                       comparator=[_pblib.LEQ, _pblib.GEQ, _pblib.BOTH][i % 3],
                       conditions=[7] if kind == 'bdd' and i % 2 else [])


@pytest.mark.parametrize("case", list(optimization_cases()))
def test_native_optimization_preserves_all_original_assignments(case):
    terms = list(zip(case["lits"], case["weights"]))
    if case["kind"] == "bdd":
        result = _pblib.encode_pb(
            wlits=terms, comparator=case["comparator"], bound=case["bound"],
            top_id=case["top_id"], pb_encoder=1, conditionals=case["conditions"],
        )
    else:
        result = _pbamo.encode_leq(
            wlits=terms, groups=case["groups"], bound=case["bound"],
            top_id=case["top_id"], encoder="rggt", emit_amo=True,
        )
    clauses, _ = result
    n = max([abs(l) for l in case["lits"]] + [abs(l) for l in case.get("conditions", [])])
    with Solver(name="g4", bootstrap_with=clauses) as solver:
        for bits in itertools.product((False, True), repeat=n):
            def value(lit):
                return bits[abs(lit) - 1] == (lit > 0)
            total = sum(w for l, w in terms if value(l))
            if case["kind"] == "rggt":
                expected = total <= case["bound"] and all(
                    sum(value(l) for l in group) <= 1 for group in case["groups"]
                )
            else:
                expected = {
                    _pblib.LEQ: total <= case["bound"],
                    _pblib.GEQ: total >= case["bound"],
                    _pblib.BOTH: total == case["bound"],
                }[case["comparator"]]
                expected = not all(value(l) for l in case["conditions"]) or expected
            assumptions = [i if b else -i for i, b in enumerate(bits, 1)]
            assert solver.solve(assumptions=assumptions) == expected, (case, assumptions)
