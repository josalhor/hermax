"""Generation optimizations preserve original assignments and normalization."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.encoder.card import CardEnc, EncType as CardType
from hermax.internal import _pbamo, _pblib


STRUCTURED = ["mdd", "gswc", "ggpw", "gmto", "rggt"]


def structured(lits, weights, groups, bound, encoder, emit_amo=True):
    return _pbamo.encode_leq(
        wlits=list(zip(lits, weights)), groups=groups, bound=bound,
        top_id=max(map(abs, lits), default=0) + 19,
        encoder=encoder, emit_amo=emit_amo,
    )


def check_arithmetic(result, lits, weights, groups, bound, op="leq", conditions=()):
    clauses, nv = result
    n = max([abs(l) for l in lits] + [abs(l) for l in conditions])
    assert all(0 < abs(l) <= nv for clause in clauses for l in clause)
    with Solver(name="g4", bootstrap_with=clauses) as solver:
        for bits in itertools.product((False, True), repeat=n):
            def value(lit):
                return bits[abs(lit) - 1] == (lit > 0)
            total = sum(w for l, w in zip(lits, weights) if value(l))
            expected = {"leq": total <= bound, "geq": total >= bound, "eq": total == bound}[op]
            expected &= all(sum(value(l) for l in group) <= 1 for group in groups)
            expected = not all(value(l) for l in conditions) or expected
            assumptions = [i if b else -i for i, b in enumerate(bits, 1)]
            assert solver.solve(assumptions=assumptions) == expected, (
                lits, weights, groups, bound, op, conditions, assumptions,
            )


def generation_cases():
    rng = random.Random(0x6E4)
    for kind in ['card', 'auto', 'gmto', 'rggt']:
        for i in range(20):
            n = rng.randint(3, 8)
            lits = [j*rng.choice([-1, 1]) for j in range(1, n+1)]
            weights = [1] + [rng.randint(1, 50) for _ in range(n-1)]
            width = 1 + i % 3
            op = ['leq', 'geq', 'eq'][i % 3] if kind in ['card', 'auto'] else 'leq'
            yield dict(kind=kind, lits=lits, weights=weights,
                       groups=[lits[j:j+width] for j in range(0, n, width)],
                       bound=rng.randrange((n if kind == 'card' else sum(weights))+1),
                       top_id=n+19, op=op, emit_amo=bool(i % 2),
                       conditions=[-(n+1)] if kind == 'auto' and i % 2 else [])


@pytest.mark.parametrize("case", list(generation_cases()))
def test_generation_preserves_truth_table(case):
    lits, weights, bound = (case[k] for k in ("lits", "weights", "bound"))
    kind, groups, conditions = case["kind"], [], case.get("conditions", [])
    if kind == "card":
        fn = {"leq": CardEnc.atmost, "geq": CardEnc.atleast, "eq": CardEnc.equals}[case["op"]]
        cnf = fn(lits, bound=bound, top_id=case["top_id"], encoding=CardType.seqcounter)
        result = cnf.clauses, cnf.nv
        weights = [1] * len(lits)
    elif kind == "auto":
        result = _pblib.encode_pb(
            wlits=list(zip(lits, weights)), bound=bound,
            comparator={"leq": _pblib.LEQ, "geq": _pblib.GEQ, "eq": _pblib.BOTH}[case["op"]],
            top_id=case["top_id"], pb_encoder=_pblib.PB_BEST, conditionals=conditions,
        )
    else:
        groups = case["groups"]
        result = structured(lits, weights, groups, bound, kind, case["emit_amo"])
    if groups and not case["emit_amo"]:
        # Group implications are preconditions supplied by the caller when the
        # native encoder is asked not to emit them itself.
        result = (result[0] + [[-a, -b] for g in groups for a, b in itertools.combinations(g, 2)], result[1])
    check_arithmetic(result, lits, weights, groups, bound, case["op"], conditions)


@pytest.mark.parametrize("encoder", STRUCTURED)
def test_pbamo_common_factor_matches_reduced_input(encoder):
    lits = [1, -2, 3, 4, -5, 6]
    weights = [1, 2, 3, 5, 7, 11]
    groups = [lits[:3], lits[3:]]
    for bound in (0, 1, 4, 9, 13, 50):
        for emit_amo in (False, True):
            expected = structured(lits, weights, groups, bound, encoder, emit_amo)
            actual = structured(lits, [w * 6 for w in weights], groups, bound * 6 + 5, encoder, emit_amo)
            assert actual == expected


@pytest.mark.parametrize("encoder", STRUCTURED)
def test_pbamo_normalization_exhaustive_random_arithmetic(encoder):
    rng = random.Random(0x6CD6)
    for _ in range(24):
        lits = [i * rng.choice((-1, 1)) for i in range(1, 7)]
        factor = rng.choice((2, 6, 30))
        weights = [rng.randint(1, 12) * factor for _ in lits]
        width = rng.randint(1, 3)
        groups = [lits[i:i + width] for i in range(0, len(lits), width)]
        bound = rng.randrange(sum(weights) + 2)
        result = structured(lits, weights, groups, bound, encoder)
        check_arithmetic(result, lits, weights, groups, bound)


@pytest.mark.parametrize("encoder", STRUCTURED)
def test_pbamo_large_factor_is_reduced_before_narrow_integer_encoders(encoder):
    factor = 1 << 60
    lits, weights, groups = [1, -2, 3], [2 * factor, 3 * factor, 5 * factor], [[1], [-2], [3]]
    for bound in (5 * factor - 1, 5 * factor, 5 * factor + 1):
        result = structured(lits, weights, groups, bound, encoder)
        check_arithmetic(result, lits, weights, groups, bound)
