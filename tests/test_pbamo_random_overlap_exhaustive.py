from __future__ import annotations

import itertools
import random

from pysat.formula import CNFPlus
from pysat.solvers import Solver


def _normalize_candidate_groups(groups):
    out = []
    seen = set()
    for group in groups:
        uniq = sorted({int(lit) for lit in group})
        if not uniq:
            continue
        key = tuple(uniq)
        if key in seen:
            continue
        seen.add(key)
        out.append(uniq)
    return out


def _random_overlap_groups(rng: random.Random, lits: list[int], *, count: int) -> list[list[int]]:
    n = len(lits)
    hot = rng.sample(lits, k=max(2, min(n, max(2, n // 2))))
    groups: list[list[int]] = []
    for _ in range(count):
        size = rng.randint(2, min(4, n))
        g = {rng.choice(hot)}
        while len(g) < size:
            pool = hot if rng.random() < 0.7 else lits
            g.add(rng.choice(pool))
        groups.append(sorted(g))

    # Ensure there is actual overlap.
    freq: dict[int, int] = {}
    for group in groups:
        for lit in group:
            freq[lit] = freq.get(lit, 0) + 1
    if not any(v > 1 for v in freq.values()):
        groups.append(sorted([lits[0], lits[1]]))
        groups.append(sorted([lits[0], lits[min(2, len(lits) - 1)]]))
    return _normalize_candidate_groups(groups)


def _build_baseline_overlap_cnf(pb_baseline, *, lits, weights, bound, amo_groups, eo_groups):
    PBEnc, PBEncType = pb_baseline
    cnf = PBEnc.leq(lits=lits, weights=weights, bound=bound, top_id=max(lits, default=0), encoding=PBEncType.bdd)
    for group in amo_groups:
        uniq = sorted({int(lit) for lit in group})
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                cnf.clauses.append([-uniq[i], -uniq[j]])
    for group in eo_groups:
        uniq = sorted({int(lit) for lit in group})
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                cnf.clauses.append([-uniq[i], -uniq[j]])
        if uniq:
            cnf.clauses.append(list(uniq))
    return cnf


def _build_structured_overlap_cnf(
    pbamo_module,
    *,
    lits,
    weights,
    bound,
    amo_groups,
    eo_groups,
    encoding,
):
    groups = pbamo_module.choose_overlap_partition(
        lits,
        weights,
        amo_groups=amo_groups,
        eo_groups=eo_groups,
        policy=pbamo_module.OverlapPolicy.paper_best_fit_dynamic_future,
    )
    cnf = pbamo_module.PBAMOEnc.leq(
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
        encoding=encoding,
        emit_amo=False,
    )
    extra = CNFPlus()
    extra.nv = int(cnf.nv)
    for group in list(amo_groups) + list(eo_groups):
        uniq = sorted({int(lit) for lit in group})
        if len(uniq) > 1:
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    extra.clauses.append([-uniq[i], -uniq[j]])
    for group in eo_groups:
        uniq = sorted({int(lit) for lit in group})
        if uniq:
            extra.clauses.append(list(uniq))
    cnf.clauses.extend(extra.clauses)
    cnf.nv = max(int(cnf.nv), int(extra.nv), max(lits, default=0))
    return cnf


def _all_full_assignment_assumptions(lits: list[int]):
    for mask in range(1 << len(lits)):
        yield [lit if ((mask >> i) & 1) else -lit for i, lit in enumerate(lits)]


def _all_partial_assumptions(lits: list[int]):
    # Ternary space per literal: false / true / unassigned.
    for states in itertools.product((-1, 1, 0), repeat=len(lits)):
        assumps = []
        for lit, st in zip(lits, states):
            if st == 0:
                continue
            assumps.append(int(st) * int(lit))
        yield assumps


def _sat_vector(clauses: list[list[int]], assumptions_space, solver_name: str) -> list[bool]:
    with Solver(name=solver_name, bootstrap_with=clauses) as solver:
        return [bool(solver.solve(assumptions=assumps)) for assumps in assumptions_space]


def _assert_all_encodings_match_baseline(
    *,
    pbamo_module,
    pb_baseline,
    sat_solver_name: str,
    lits: list[int],
    weights: list[int],
    bound: int,
    amo_groups: list[list[int]],
    eo_groups: list[list[int]],
    assumptions_space,
) -> None:
    baseline = _build_baseline_overlap_cnf(
        pb_baseline,
        lits=lits,
        weights=weights,
        bound=bound,
        amo_groups=amo_groups,
        eo_groups=eo_groups,
    )
    expected = _sat_vector(baseline.clauses, assumptions_space, sat_solver_name)

    for enc in pbamo_module.available_encoders():
        cnf = _build_structured_overlap_cnf(
            pbamo_module,
            lits=lits,
            weights=weights,
            bound=bound,
            amo_groups=amo_groups,
            eo_groups=eo_groups,
            encoding=enc,
        )
        got = _sat_vector(cnf.clauses, assumptions_space, sat_solver_name)
        assert got == expected, (
            f"encoding={enc}",
            f"lits={lits}",
            f"weights={weights}",
            f"bound={bound}",
            f"amo_groups={amo_groups}",
            f"eo_groups={eo_groups}",
        )


def test_random_overlap_all_encoders_match_baseline_full_assignments(
    pbamo_module, pb_baseline, sat_solver_name: str
) -> None:
    rng = random.Random(0xA11CE5EED)
    for _ in range(5):
        n = rng.randint(5, 8)
        lits = list(range(1, n + 1))
        weights = [rng.randint(1, 16) for _ in range(n)]
        amo_groups = _random_overlap_groups(rng, lits, count=rng.randint(3, 8))
        eo_groups = _random_overlap_groups(rng, lits, count=rng.randint(1, 4))
        bound = rng.randint(0, sum(weights))
        assumptions = list(_all_full_assignment_assumptions(lits))
        _assert_all_encodings_match_baseline(
            pbamo_module=pbamo_module,
            pb_baseline=pb_baseline,
            sat_solver_name=sat_solver_name,
            lits=lits,
            weights=weights,
            bound=bound,
            amo_groups=amo_groups,
            eo_groups=eo_groups,
            assumptions_space=assumptions,
        )


def test_random_overlap_all_encoders_match_baseline_partial_assumptions(
    pbamo_module, pb_baseline, sat_solver_name: str
) -> None:
    rng = random.Random(0x5EEDBEEF)
    for _ in range(3):
        n = rng.randint(4, 6)
        lits = list(range(1, n + 1))
        weights = [rng.randint(1, 20) for _ in range(n)]
        amo_groups = _random_overlap_groups(rng, lits, count=rng.randint(3, 7))
        eo_groups = _random_overlap_groups(rng, lits, count=rng.randint(1, 4))
        bound = rng.randint(0, sum(weights))
        assumptions = list(_all_partial_assumptions(lits))
        _assert_all_encodings_match_baseline(
            pbamo_module=pbamo_module,
            pb_baseline=pb_baseline,
            sat_solver_name=sat_solver_name,
            lits=lits,
            weights=weights,
            bound=bound,
            amo_groups=amo_groups,
            eo_groups=eo_groups,
            assumptions_space=assumptions,
        )

