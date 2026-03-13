from __future__ import annotations

from pysat.solvers import Solver

from tests.structuredpb_test_utils import assert_encoding_matches_oracle_and_baseline


def _unit_simplify_clauses(clauses: list[list[int]]) -> list[list[int]]:
    working = [list(clause) for clause in clauses]
    units = {int(clause[0]) for clause in working if len(clause) == 1}
    changed = True
    while changed:
        changed = False
        next_working: list[list[int]] = []
        for clause in working:
            if any(lit in units for lit in clause):
                changed = True
                continue
            reduced = [lit for lit in clause if -lit not in units]
            if len(reduced) != len(clause):
                changed = True
            if not reduced:
                next_working.append(reduced)
                continue
            next_working.append(reduced)
        working = next_working
        new_units = {int(clause[0]) for clause in working if len(clause) == 1}
        if new_units != units:
            changed = True
            units = new_units
    return [clause for clause in working if clause]


def test_paper_intro_example_mdd_matches_oracle_and_shrinks_formula(
    structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str
) -> None:
    lits = [1, 2, 3, 4, 5, 6]
    weights = [2, 3, 4, 2, 3, 4]
    groups = [[1, 2, 3], [4, 5, 6]]
    bound = 7

    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="mdd",
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
    )

    cnf = structuredpb_module.StructuredPBEnc.leq(
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
        top_id=max(lits),
        encoding=structuredpb_module.EncType.mdd,
        emit_amo=True,
    )
    PBEnc, PBEncType = pb_baseline
    CardEnc, CardEncType = card_baseline
    baseline = PBEnc.leq(lits=lits, weights=weights, bound=bound, top_id=max(lits), encoding=PBEncType.bdd)
    for group in groups:
        amo = CardEnc.atmost(lits=group, bound=1, encoding=CardEncType.pairwise)
        baseline.clauses.extend(amo.clauses)
        baseline.nv = max(baseline.nv, amo.nv)

    assert len(cnf.clauses) == 9
    assert sum(len(c) for c in cnf.clauses) == 18
    assert len(cnf.clauses) < len(baseline.clauses)
    assert sum(len(c) for c in cnf.clauses) < sum(len(c) for c in baseline.clauses)


def test_paper_intro_example_rggt_matches_oracle_and_is_even_smaller(
    structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str
) -> None:
    lits = [1, 2, 3, 4, 5, 6]
    weights = [2, 3, 4, 2, 3, 4]
    groups = [[1, 2, 3], [4, 5, 6]]
    bound = 7

    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="rggt",
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
    )

    cnf = structuredpb_module.StructuredPBEnc.leq(
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
        top_id=max(lits),
        encoding=structuredpb_module.EncType.rggt,
        emit_amo=True,
    )

    assert len(cnf.clauses) == 8
    assert sum(len(c) for c in cnf.clauses) == 16


def test_paper_motivating_example_rggt_pb_side_simplifies_to_one_clause(structuredpb_module) -> None:
    lits = [1, 2, 3, 4, 5, 6]
    weights = [2, 3, 4, 2, 3, 4]
    groups = [[1, 2, 3], [4, 5, 6]]
    bound = 7

    cnf = structuredpb_module.StructuredPBEnc.leq(
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
        top_id=max(lits),
        encoding=structuredpb_module.EncType.rggt,
        emit_amo=False,
    )

    simplified = _unit_simplify_clauses(cnf.clauses)
    assert simplified == [[-3, -6]]


def test_paper_rggt_fig5_x7_is_irrelevant_under_fixed_x1_to_x6(structuredpb_module) -> None:
    lits = [1, 2, 3, 4, 5, 6, 7]
    weights = [20, 30, 20, 40, 10, 20, 1]
    groups = [[1, 2], [3, 4], [5, 6], [7]]
    bound = 55

    cnf = structuredpb_module.StructuredPBEnc.leq(
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
        top_id=max(lits),
        encoding=structuredpb_module.EncType.rggt,
        emit_amo=True,
    )

    for mask in range(1 << 6):
        assumptions_false = []
        assumptions_true = []
        for i, lit in enumerate(lits[:6]):
            val = (mask >> i) & 1
            assumptions_false.append(lit if val else -lit)
            assumptions_true.append(lit if val else -lit)
        assumptions_false.append(-7)
        assumptions_true.append(7)

        with Solver(name="cadical153", bootstrap_with=cnf.clauses) as solver:
            sat_false = bool(solver.solve(assumptions=assumptions_false))
        with Solver(name="cadical153", bootstrap_with=cnf.clauses) as solver:
            sat_true = bool(solver.solve(assumptions=assumptions_true))

        assert sat_false == sat_true


def test_paper_rggt_fig5_matches_removed_x7_instance_size(structuredpb_module) -> None:
    with_x7 = structuredpb_module.StructuredPBEnc.leq(
        lits=[1, 2, 3, 4, 5, 6, 7],
        weights=[20, 30, 20, 40, 10, 20, 1],
        groups=[[1, 2], [3, 4], [5, 6], [7]],
        bound=55,
        top_id=7,
        encoding=structuredpb_module.EncType.rggt,
        emit_amo=True,
    )
    without_x7 = structuredpb_module.StructuredPBEnc.leq(
        lits=[1, 2, 3, 4, 5, 6],
        weights=[20, 30, 20, 40, 10, 20],
        groups=[[1, 2], [3, 4], [5, 6]],
        bound=55,
        top_id=6,
        encoding=structuredpb_module.EncType.rggt,
        emit_amo=True,
    )

    assert len(with_x7.clauses) == len(without_x7.clauses)
    assert sum(len(c) for c in with_x7.clauses) == sum(len(c) for c in without_x7.clauses)
    assert (with_x7.nv - 7) == (without_x7.nv - 6)


def test_paper_example1_mdd_matches_oracle_and_reduces_against_flat_baseline(
    structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str
) -> None:
    lits = [1, 2, 3, 4]
    weights = [2, 3, 3, 7]
    groups = [[1, 2], [3, 4]]
    bound = 8

    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="mdd",
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
    )

    cnf = structuredpb_module.StructuredPBEnc.leq(
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
        top_id=max(lits),
        encoding=structuredpb_module.EncType.mdd,
        emit_amo=True,
    )
    assert len(cnf.clauses) == 7
    assert sum(len(c) for c in cnf.clauses) == 15


def test_paper_example1_rggt_matches_oracle_and_is_smallest_of_tested(
    structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str
) -> None:
    lits = [1, 2, 3, 4]
    weights = [2, 3, 3, 7]
    groups = [[1, 2], [3, 4]]
    bound = 8

    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="rggt",
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
    )

    cnf = structuredpb_module.StructuredPBEnc.leq(
        lits=lits,
        weights=weights,
        groups=groups,
        bound=bound,
        top_id=max(lits),
        encoding=structuredpb_module.EncType.rggt,
        emit_amo=True,
    )
    assert len(cnf.clauses) == 6
    assert sum(len(c) for c in cnf.clauses) == 12
