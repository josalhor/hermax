from __future__ import annotations

import itertools
import random

import pytest
from pysat.solvers import Solver


def _models(lits, weights, groups, bound):
    variables = sorted({abs(lit) for lit in lits})
    for bits in itertools.product((False, True), repeat=len(variables)):
        assignment = dict(zip(variables, bits))
        value = lambda lit: assignment[abs(lit)] == (lit > 0)
        if sum(weight for lit, weight in zip(lits, weights) if value(lit)) <= bound and all(
            sum(value(lit) for lit in group) <= 1 for group in groups
        ):
            yield assignment


def _encode(pbamo_module, lits, weights, groups, bound, emit_amo=True):
    return pbamo_module.PBAMOEnc.leq(
        lits=lits, weights=weights, groups=groups, bound=bound,
        encoding=pbamo_module.EncType.glpw, emit_amo=emit_amo,
    )


def _check_truth_table(pbamo_module, lits, weights, groups, bound, emit_amo=True):
    cnf = _encode(pbamo_module, lits, weights, groups, bound, emit_amo)
    clauses = list(cnf.clauses)
    if not emit_amo:
        clauses += [[-a, -b] for group in groups for a, b in itertools.combinations(group, 2)]
    models = {tuple(m[abs(lit)] for lit in lits) for m in _models(lits, weights, groups, bound)}
    with Solver(bootstrap_with=clauses) as solver:
        for values in itertools.product((False, True), repeat=len(lits)):
            assumptions = [abs(lit) if value else -abs(lit) for lit, value in zip(lits, values)]
            assert solver.solve(assumptions=assumptions) == (values in models)


def test_glpw_is_registered(pbamo_module):
    from hermax.internal import _pbamo
    assert pbamo_module.EncType.glpw == "glpw"
    assert _pbamo.ENC_GLPW == "glpw"
    assert "glpw" in _pbamo.available_encoders()


@pytest.mark.parametrize("emit_amo", [True, False])
def test_glpw_paper_example_and_signed_literals(pbamo_module, emit_amo):
    _check_truth_table(pbamo_module, [1, 2, 3, 4], [2, 3, 4, 7], [[1, 2], [3, 4]], 8, emit_amo)
    _check_truth_table(pbamo_module, [-1, 2, -3, 4], [7, 3, 4, 2], [[-1, 2], [-3], [4]], 6, emit_amo)


def test_glpw_random_small_truth_tables(pbamo_module):
    rng = random.Random(7543)
    for _ in range(120):
        n = rng.randint(1, 6)
        lits = [i * rng.choice([-1, 1]) for i in range(1, n + 1)]
        rng.shuffle(lits)
        groups = []
        for lit in lits:
            if not groups or rng.randrange(3) == 0:
                groups.append([])
            groups[-1].append(lit)
        weights = [rng.randint(1, 30) for _ in lits]
        _check_truth_table(pbamo_module, lits, weights, groups, rng.randint(0, sum(weights)))


def _unit_propagate(clauses, assumptions):
    units = set(assumptions)
    while True:
        if any(-lit in units for lit in units):
            return False, units
        added = set()
        for clause in clauses:
            if any(lit in units for lit in clause):
                continue
            pending = {lit for lit in clause if -lit not in units}
            if not pending:
                return False, units
            if len(pending) == 1:
                added.update(pending)
        if added <= units:
            return True, units
        units.update(added)


def test_glpw_unit_propagation_is_gac_on_small_constraints(pbamo_module):
    rng = random.Random(5342)
    cases = [([1, 2, 3, 4], [2, 3, 4, 7], [[1, 2], [3, 4]], 8)]
    for _ in range(35):
        lits = list(range(1, 6))
        rng.shuffle(lits)
        lits = [lit * rng.choice((-1, 1)) for lit in lits]
        groups = [lits[:2], lits[2:4], lits[4:]]
        cases.append((lits, [rng.randint(1, 12) for _ in lits], groups, rng.randint(0, 25)))
    for lits, weights, groups, bound in cases:
        cnf = _encode(pbamo_module, lits, weights, groups, bound)
        models = list(_models(lits, weights, groups, bound))
        for partial in itertools.product((-1, 0, 1), repeat=len(lits)):
            assumptions = [abs(var) * state for var, state in zip(lits, partial) if state]
            remaining = [m for m in models if all(m[abs(a)] == (a > 0) for a in assumptions)]
            consistent, propagated = _unit_propagate(cnf.clauses, assumptions)
            if not remaining:
                assert not consistent, (lits, weights, groups, bound, assumptions)
                continue
            assert consistent
            implied = set(propagated) | set(assumptions)
            for lit, state in zip(lits, partial):
                var = abs(lit)
                if not state and all(not m[var] for m in remaining):
                    assert -var in implied, (lits, weights, groups, bound, assumptions, var)
                if not state and all(m[var] for m in remaining):
                    assert var in implied, (lits, weights, groups, bound, assumptions, var)


@pytest.mark.parametrize("bound,weights", [
    (0, [1, 2]),
    ((1 << 64) - 1, [(1 << 64) - 1, 1]),
    ((1 << 64) - 2, [(1 << 63) + 1, (1 << 63) - 1]),
    ((1 << 63) + 7, [(1 << 63), 8]),
])
def test_glpw_large_boundaries(pbamo_module, bound, weights):
    _check_truth_table(pbamo_module, [1, 2], weights, [[1], [2]], bound)


def test_glpw_propagates_a_literal_that_ggpw_does_not(pbamo_module):
    from hermax.internal import _pbamo
    weights = [13, 8, 2, 1, 2, 15]
    groups = [[1, 2], [3, 4], [5, 6]]
    clauses = {}
    for encoder in ("ggpw", "glpw"):
        clauses[encoder], _ = _pbamo.encode_leq(
            list(zip(range(1, 7), weights)), groups, 23, 0, encoder, True
        )
    assumptions = [-1, 2, -3, 4, -5]
    assert -6 not in _unit_propagate(clauses["ggpw"], assumptions)[1]
    assert -6 in _unit_propagate(clauses["glpw"], assumptions)[1]


def test_glpw_shares_watchdogs_across_local_constraints(pbamo_module):
    from hermax.internal import _pbamo
    rng = random.Random(83)
    groups = [list(range(3 * i + 1, 3 * i + 4)) for i in range(8)]
    weights = {lit: rng.randint(30, 127) for group in groups for lit in group}
    bound = sum(max(weights[lit] for lit in group) for group in groups) // 2
    shared, top = _pbamo.encode_leq(list(weights.items()), groups, bound, 0, "glpw", False)
    independent_clauses = independent_aux = 0
    for i, group in enumerate(groups):
        remaining_groups = groups[:i] + groups[i + 1:]
        terms = [(lit, weights[lit]) for other in remaining_groups for lit in other]
        for lit in group:
            clauses, nv = _pbamo.encode_leq(
                terms, remaining_groups, bound - weights[lit], len(weights), "ggpw", False
            )
            independent_clauses += len(clauses)
            independent_aux += nv - len(weights)
    assert len(shared) < independent_clauses
    assert top - len(weights) < independent_aux


def test_glpw_complementary_literals_match_original_boolean_variables(pbamo_module):
    from hermax.internal import _pbamo
    lits = [1, -1, 2, -2, 3]
    weights = [7, 3, 5, 8, 2]
    groups = [[1, 2], [-1, -2], [3]]
    clauses, _ = _pbamo.encode_leq(list(zip(lits, weights)), groups, 10, 0, "glpw", True)
    with Solver(bootstrap_with=clauses) as solver:
        for values in itertools.product((False, True), repeat=3):
            def value(lit):
                return values[abs(lit) - 1] == (lit > 0)
            expected = sum(w for lit, w in zip(lits, weights) if value(lit)) <= 10
            expected &= all(sum(value(lit) for lit in group) <= 1 for group in groups)
            assumptions = [i if val else -i for i, val in enumerate(values, 1)]
            assert solver.solve(assumptions=assumptions) == expected


def test_glpw_random_large_unsigned_coefficients(pbamo_module):
    rng = random.Random(1835)
    for _ in range(40):
        lits = [1, 2, 3, 4]
        weights = [rng.randrange(1, 1 << 64) for _ in lits]
        groups = [[1, 2], [3], [4]]
        _check_truth_table(pbamo_module, lits, weights, groups, rng.randrange(1 << 64))


def test_glpw_prunes_unused_watchdog_outputs(pbamo_module):
    from hermax.internal import _pbamo
    lits = [9, 3, -13, -8, 11, 7, 6, 15, 12, 2, 10, 1, 5, 4, 16, 14]
    weights = [3, 1, 2, 1, 3, 1, 5, 2, 3, 5, 1, 3, 3, 1, 4, 5]
    groups = [lits[i:i + 2] for i in range(0, len(lits), 2)]
    clauses, top = _pbamo.encode_leq(list(zip(lits, weights)), groups, 24, 16, "glpw", False)
    # The eager construction used 409 auxiliaries and 1,067 clauses here.
    assert top - 16 <= 212
    assert len(clauses) <= 501


def test_glpw_paper_validation_family_unit_propagation(pbamo_module):
    # Same 16 six-variable families and all 3^6 partial assignments used in
    # the original selector study; arithmetic oracle enumerates completions.
    for seed in range(16):
        rng = random.Random(45510 + seed)
        lits = [i * rng.choice([-1, 1]) for i in range(1, 7)]
        weights = [rng.randint(1, 20) for _ in lits]
        width = [1, 2, 3, 6][seed % 4]
        groups = [lits[i:i + width] for i in range(0, 6, width)]
        by_lit = dict(zip(lits, weights))
        capacity = sum(max(by_lit[lit] for lit in group) for group in groups)
        bound = int(capacity * [.15, .35, .65, .85][seed // 4])
        models = list(_models(lits, weights, groups, bound))
        cnf = _encode(pbamo_module, lits, weights, groups, bound)
        for states in itertools.product((-1, 0, 1), repeat=6):
            assumptions = [i * state for i, state in enumerate(states, 1) if state]
            completions = [m for m in models if all(m[abs(a)] == (a > 0) for a in assumptions)]
            consistent, implied = _unit_propagate(cnf.clauses, assumptions)
            if not completions:
                assert not consistent, (seed, assumptions)
                continue
            assert consistent
            for var in range(1, 7):
                if all(m[var] for m in completions):
                    assert var in implied, (seed, assumptions, var)
                if all(not m[var] for m in completions):
                    assert -var in implied, (seed, assumptions, var)


def test_glpw_random_complementary_literals_are_sound(pbamo_module):
    from hermax.internal import _pbamo
    rng = random.Random(8321)
    for _ in range(120):
        lits = [1, -1, 2, -2, 3]
        rng.shuffle(lits)
        weights = [rng.randint(1, 20) for _ in lits]
        groups = [lits[:2], lits[2:4], lits[4:]]
        bound = rng.randint(0, sum(weights))
        clauses, _ = _pbamo.encode_leq(list(zip(lits, weights)), groups, bound, 0, "glpw", True)
        with Solver(bootstrap_with=clauses) as solver:
            for values in itertools.product((False, True), repeat=3):
                def value(lit):
                    return values[abs(lit) - 1] == (lit > 0)
                expected = sum(w for lit, w in zip(lits, weights) if value(lit)) <= bound
                expected &= all(sum(value(lit) for lit in group) <= 1 for group in groups)
                assumptions = [i if val else -i for i, val in enumerate(values, 1)]
                assert solver.solve(assumptions=assumptions) == expected
