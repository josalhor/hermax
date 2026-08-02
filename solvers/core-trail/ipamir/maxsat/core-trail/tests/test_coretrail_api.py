from __future__ import annotations

import os
import signal
import threading
import time

import pytest

from coretrail import CoreTrail


class Formula:
    def __init__(self, *, nv: int, hard: list[list[int]] | None = None, soft: list[list[int]] | None = None, wght: list[int] | None = None):
        self.nv = nv
        self.hard = hard or []
        self.soft = soft or []
        self.wght = wght or []
        self.atms: list[object] = []


def test_coretrail_public_identity_and_hard_sat():
    solver = CoreTrail(Formula(nv=1, hard=[[1]]))
    try:
        assert solver.signature() == "core-trail"
        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_model() == [1]
    finally:
        solver.close()


def test_empty_hard_clause_is_unsat():
    solver = CoreTrail(Formula(nv=1, hard=[[]]))
    try:
        assert solver.solve() is False
        assert solver.get_status() == 20
    finally:
        solver.close()


def test_known_unsat_query_is_not_downgraded_by_a_later_deadline():
    solver = CoreTrail(Formula(nv=1, hard=[[1], [-1]]))
    try:
        assert solver.solve() is False
        assert solver.get_status() == 20

        assert solver.solve(time_limit=1e-12) is False
        assert solver.get_status() == 20
    finally:
        solver.close()


def test_coretrail_soft_update_is_incremental():
    solver = CoreTrail(Formula(nv=1, soft=[[1]], wght=[3]))
    try:
        assert solver.solve() is True
        assert solver.get_cost() == 0

        solver.set_soft(-1, 5)
        assert solver.solve() is True
        assert solver.get_cost() == 3
    finally:
        solver.close()


def test_hard_clause_added_after_solve_is_applied_incrementally():
    solver = CoreTrail(Formula(nv=1, hard=[[1]]))
    try:
        assert solver.solve() is True

        solver.add_clause([-1])
        assert solver.solve() is False
        assert solver.get_status() == 20
    finally:
        solver.close()


def test_duplicate_unit_soft_clauses_accumulate_wcnf_cost():
    solver = CoreTrail(Formula(nv=1, hard=[[-1]], soft=[[1], [1]], wght=[2, 3]))
    try:
        assert solver.solve() is True
        assert solver.get_cost() == 5
    finally:
        solver.close()


def test_set_soft_replaces_a_unit_term_in_the_exact_objective():
    solver = CoreTrail(Formula(nv=1, hard=[[-1]], soft=[[1]], wght=[2]))
    try:
        solver.set_soft(1, 7)
        assert solver.solve() is True
        assert solver.get_cost() == 7
    finally:
        solver.close()


def test_non_unit_soft_cost_uses_the_original_clause_not_its_selector():
    solver = CoreTrail(Formula(nv=2, hard=[[-1], [-2]], soft=[[1, 2]], wght=[11]))
    try:
        assert solver.solve() is True
        assert solver.get_cost() == 11
    finally:
        solver.close()


def test_contradictory_unit_terms_have_the_cost_of_one_term_per_variable():
    solver = CoreTrail(Formula(nv=2, soft=[[1], [2], [-1], [-2]], wght=[1, 1, 1, 1]))
    try:
        assert solver.solve() is True
        assert solver.get_cost() == 2
    finally:
        solver.close()


def test_interrupted_query_resumes_to_optimum():
    variable_count = 500
    solver = CoreTrail(_contradictory_unit_formula(variable_count))
    try:
        assert solver.solve(time_limit=1e-12) is False
        assert solver.get_status() == 0

        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_cost() == variable_count
    finally:
        solver.close()


@pytest.mark.parametrize("limit", [0.0, -1.0, float("inf"), float("nan")])
def test_time_limit_requires_a_finite_positive_value(limit: float):
    solver = CoreTrail(Formula(nv=1, hard=[[1]]))
    try:
        with pytest.raises(ValueError, match="finite positive"):
            solver.solve(time_limit=limit)
    finally:
        solver.close()


def _contradictory_unit_formula(variable_count: int) -> Formula:
    soft = [[var] for var in range(1, variable_count + 1)]
    soft.extend([[-var] for var in range(1, variable_count + 1)])
    return Formula(nv=variable_count, soft=soft, wght=[1] * len(soft))


def test_deadline_after_candidate_reports_exact_incumbent():
    variable_count = 500
    solver = CoreTrail(_contradictory_unit_formula(variable_count))
    try:
        assert solver.solve() is True
        assert solver.get_cost() == variable_count

        # The updated query reaches a new native SAT boundary before its
        # deadline, so it must expose the exact incumbent rather than stale
        # core-guided accounting from the preceding optimum.
        solver.set_soft(1, 2)
        timed = solver.solve(time_limit=0.0001)
        assert solver.get_status() in (10, 30)
        assert solver.get_cost() == variable_count
        assert len(solver.get_model()) == variable_count

        # No formula or assumption change: retain an interrupted incumbent, or
        # retain the already proven optimum if the timed call finished first.
        assert solver.solve(assumptions=[], time_limit=1e-12) is timed
        assert solver.get_status() == (30 if timed else 10)
        assert solver.get_cost() == variable_count

        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_cost() == variable_count
    finally:
        solver.close()


def test_external_stop_is_observed_at_a_core_transition_boundary():
    solver = CoreTrail(_contradictory_unit_formula(1000))
    try:
        stopper = threading.Thread(
            target=lambda: (time.sleep(0.001), solver.request_stop()),
        )
        started = time.monotonic()
        stopper.start()
        assert solver.solve() is False
        stopper.join()

        assert solver.get_status() == 0
        # This is a generous machine-independent bound. The actual response
        # should be near the 1 ms stop delay, not a full preprocessing pass.
        assert time.monotonic() - started < 0.25

        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_cost() == 1000
    finally:
        solver.close()


def test_sigint_interrupts_coretrail_without_leaking_to_the_restored_handler():
    solver = CoreTrail(_contradictory_unit_formula(1000))
    delivered: list[int] = []

    def previous_handler(signum: int, frame: object) -> None:
        del frame
        delivered.append(signum)

    original_handler = signal.signal(signal.SIGINT, previous_handler)
    try:
        interrupter = threading.Thread(
            target=lambda: (time.sleep(0.001), os.kill(os.getpid(), signal.SIGINT)),
        )
        interrupter.start()
        assert solver.solve() is False
        interrupter.join()

        assert solver.get_status() == 0
        assert signal.getsignal(signal.SIGINT) is previous_handler
        assert delivered == []

        assert solver.solve() is True
        assert solver.get_status() == 30
    finally:
        signal.signal(signal.SIGINT, original_handler)
        solver.close()


def test_changed_query_after_interruption_discards_stale_incumbent():
    variable_count = 500
    solver = CoreTrail(_contradictory_unit_formula(variable_count))
    try:
        assert solver.solve(time_limit=1e-12) is False
        assert solver.get_status() == 0

        solver.add_clause([-1])
        solver.set_soft(1, 7)
        assert solver.solve(assumptions=[-2]) is True
        assert solver.get_status() == 30
        # Variable 1 is forced false, so [1] costs 7; variable 2 is forced
        # false, so [-2] costs 1; every other complementary pair costs 1.
        assert solver.get_cost() == variable_count + 6
    finally:
        solver.close()


def test_soft_change_invalidates_an_interrupted_incumbent_before_the_next_solve():
    variable_count = 500
    solver = CoreTrail(_contradictory_unit_formula(variable_count))
    try:
        assert solver.solve() is True
        solver.set_soft(1, 2)
        assert solver.solve(time_limit=0.0001) is False
        assert solver.get_status() == 10
        assert solver.get_cost() == variable_count

        solver.set_soft(-1, 7)
        with pytest.raises(RuntimeError, match="Objective not available"):
            solver.get_cost()
        with pytest.raises(RuntimeError, match="No model available"):
            solver.get_model()

        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_cost() == variable_count + 1
    finally:
        solver.close()


def test_same_soft_weight_is_a_noop_for_query_identity():
    solver = CoreTrail(_contradictory_unit_formula(300))
    try:
        assert solver.solve() is True
        assert solver.get_cost() == 300

        solver.set_soft(1, 1)
        assert solver.solve(time_limit=1e-12) is True
        assert solver.get_status() == 30
        assert solver.get_cost() == 300

        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_cost() == 300
    finally:
        solver.close()


def test_equivalent_assumption_order_is_a_noop_for_query_identity():
    solver = CoreTrail(_contradictory_unit_formula(500))
    try:
        assert solver.solve(assumptions=[-1, -2]) is True
        solver.set_soft(1, 2)
        assert solver.solve(assumptions=[-1, -2]) is True
        assert solver.get_status() == 30
        old_cost = solver.get_cost()

        assert solver.solve(assumptions=[-2, -1, -1], time_limit=1e-12) is True
        assert solver.get_status() == 30
        assert solver.get_cost() == old_cost

        assert solver.solve(assumptions=[-1, -2]) is True
        assert solver.get_status() == 30
        assert solver.get_cost() == 501
    finally:
        solver.close()


def test_changed_assumptions_discard_an_interrupted_incumbent_immediately():
    solver = CoreTrail(_contradictory_unit_formula(500))
    try:
        assert solver.solve() is True
        solver.set_soft(1, 2)
        assert solver.solve(time_limit=0.0001) is False
        assert solver.get_status() == 10
        assert solver.get_cost() == 500

        # The new assumption changes the query before the next solve even
        # though the old incumbent happens to satisfy it.
        assert solver.solve(assumptions=[-1], time_limit=1e-12) is False
        assert solver.get_status() == 0
        with pytest.raises(RuntimeError, match="Objective not available"):
            solver.get_cost()
        with pytest.raises(RuntimeError, match="No model available"):
            solver.get_model()

        assert solver.solve(assumptions=[-1]) is True
        assert solver.get_status() == 30
        assert solver.get_cost() == 501
    finally:
        solver.close()


def test_repeated_deadline_resumes_never_regress_an_incumbent():
    solver = CoreTrail(_contradictory_unit_formula(500))
    try:
        assert solver.solve() is True
        solver.set_soft(1, 2)
        assert solver.solve(time_limit=0.0001) is False
        assert solver.get_status() == 10
        costs = [solver.get_cost()]

        for _ in range(5):
            assert solver.solve(time_limit=1e-12) is False
            assert solver.get_status() == 10
            costs.append(solver.get_cost())

        assert costs == sorted(costs, reverse=True)
        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_cost() == 500
    finally:
        solver.close()


def test_non_full_stratification_remains_usable_across_timed_queries():
    solver = CoreTrail(_contradictory_unit_formula(500), full_stratified=False)
    try:
        assert solver.solve(time_limit=1e-12) is False
        assert solver.get_status() == 0
        assert solver.solve() is True
        assert solver.get_cost() == 500

        solver.set_soft(1, 2)
        timed = solver.solve(time_limit=0.0001)
        assert solver.get_status() in (10, 30)
        assert solver.get_cost() == 500
        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_cost() == 500
    finally:
        solver.close()


def test_interrupted_exhaustion_abandons_the_shortcut_and_finishes_exactly():
    variable_count = 30
    formula = Formula(
        nv=variable_count,
        hard=[[-left, -right] for left in range(1, variable_count + 1) for right in range(left + 1, variable_count + 1)],
        soft=[[var] for var in range(1, variable_count + 1)],
        wght=[1] * variable_count,
    )
    solver = CoreTrail(formula, exhaust=True, adapt=False)
    try:
        assert solver.solve(time_limit=0.0005) is False
        assert solver.get_status() == 10
        assert solver.get_cost() == variable_count

        # The interrupted bound probe is discarded. Its already committed
        # relaxation encoding remains live, and ordinary OLL must still prove
        # the exact optimum on the next call.
        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_cost() == variable_count - 1
    finally:
        solver.close()


def test_changed_query_after_interrupted_exhaustion_keeps_the_live_backend_sound():
    variable_count = 30
    formula = Formula(
        nv=variable_count,
        hard=[[-left, -right] for left in range(1, variable_count + 1) for right in range(left + 1, variable_count + 1)],
        soft=[[var] for var in range(1, variable_count + 1)],
        wght=[1] * variable_count,
    )
    solver = CoreTrail(formula, exhaust=True, adapt=False)
    try:
        assert solver.solve(time_limit=0.0005) is False
        assert solver.get_status() == 10
        assert solver.get_cost() == variable_count

        # The added hard clause changes the query after exhaustion was
        # cancelled. It must adapt the live encoding, not use the old
        # incumbent.
        solver.add_clause([-1])
        with pytest.raises(RuntimeError, match="Objective not available"):
            solver.get_cost()

        assert solver.solve() is True
        assert solver.get_status() == 30
        assert solver.get_cost() == variable_count - 1
    finally:
        solver.close()


def test_soft_and_assumption_change_after_interrupted_exhaustion_is_exact():
    variable_count = 30
    formula = Formula(
        nv=variable_count,
        hard=[[-left, -right] for left in range(1, variable_count + 1) for right in range(left + 1, variable_count + 1)],
        soft=[[var] for var in range(1, variable_count + 1)],
        wght=[1] * variable_count,
    )
    solver = CoreTrail(formula, exhaust=True, adapt=False)
    try:
        assert solver.solve(time_limit=0.0005) is False
        assert solver.get_status() == 10

        solver.set_soft(1, 2)
        assert solver.solve(assumptions=[-1]) is True
        assert solver.get_status() == 30
        # Variable 1 is forced false, its soft term costs 2, one of the other
        # positives is true, and the remaining 28 unit terms cost 1 each.
        assert solver.get_cost() == 30
    finally:
        solver.close()
