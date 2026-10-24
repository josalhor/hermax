"""State preflight and bounded clause sink."""
import itertools

import pytest
from pysat.solvers import Solver

from hermax.internal import _integer_sum_native as integer_native
from hermax.internal import _pblib as stock_pblib


def encode(*, state_limit=0, clause_limit=0, encoder=None, conditionals=()):
    return integer_native.encode_pb(
        wlits=[(1, 2), (2, 3), (3, 4), (4, 5)],
        comparator=integer_native.LEQ,
        bound=7,
        top_id=9,
        pb_encoder=integer_native.PB_BDD if encoder is None else encoder,
        conditionals=list(conditionals),
        state_limit=state_limit,
        clause_limit=clause_limit,
    )


def test_state_budget_is_inclusive_and_counts_distinct_nonterminal_subproblems():
    weights = [5, 4, 3, 2]
    suffix = [sum(weights[i:]) for i in range(len(weights) + 1)]
    visited = set()

    def visit(i, total):
        if total > 7 or total + suffix[i] <= 7:
            return
        if (i, total) in visited:
            return
        visited.add((i, total))
        visit(i + 1, total)
        visit(i + 1, total + weights[i])

    visit(0, 0)
    count = len(visited)
    assert count > 1
    assert encode(state_limit=count) == encode()
    with pytest.raises(integer_native.EncodingBudgetExceeded, match="states"):
        encode(state_limit=count - 1)


def test_clause_budget_is_inclusive_and_does_not_change_the_cnf():
    original = encode()
    count = len(original[0])
    assert count > 1
    assert encode(clause_limit=count) == original
    with pytest.raises(integer_native.EncodingBudgetExceeded, match="clauses"):
        encode(clause_limit=count - 1)


def test_default_limits_and_explicit_zero_preserve_existing_calls():
    raw = stock_pblib.encode_pb(
        wlits=[(1, 2), (2, 3), (3, 4), (4, 5)],
        comparator=integer_native.LEQ,
        bound=7,
        top_id=9,
        pb_encoder=integer_native.PB_BDD,
        conditionals=[],
    )
    assert raw == encode()


@pytest.mark.parametrize("limit", ["states", "clauses"])
def test_repeated_abort_does_not_poison_the_next_call_or_conditional_list(limit):
    conditions = [8]
    original = encode(conditionals=conditions)
    for _ in range(40):
        with pytest.raises(integer_native.EncodingBudgetExceeded):
            encode(
                state_limit=1 if limit == "states" else 0,
                clause_limit=1 if limit == "clauses" else 0,
                conditionals=conditions,
            )
        assert conditions == [8]
        assert encode(conditionals=conditions) == original
    with Solver(name="g4", bootstrap_with=original[0]) as solver:
        for bits in itertools.product([False, True], repeat=5):
            value = sum(w * b for w, b in zip([2, 3, 4, 5], bits))
            ass = [i if b else -i for i, b in zip([1, 2, 3, 4, 8], bits)]
            assert solver.solve(assumptions=ass) == (not bits[4] or value <= 7)


def test_clause_budget_also_covers_preprocessing_before_any_bdd_states():
    terms = [(i, 2) for i in range(1, 50_002)]
    with pytest.raises(integer_native.EncodingBudgetExceeded, match="clauses"):
        integer_native.encode_pb(
            wlits=terms,
            comparator=integer_native.LEQ,
            bound=1,
            top_id=50_001,
            pb_encoder=integer_native.PB_BEST,
            conditionals=[],
            state_limit=20_000,
            clause_limit=50_000,
        )


@pytest.mark.parametrize("kw", [{"state_limit": -1}, {"clause_limit": -1}])
def test_negative_budgets_are_rejected(kw):
    with pytest.raises(ValueError):
        encode(**kw)


@pytest.mark.parametrize(
    "encoder",
    [
        integer_native.PB_BEST,
        integer_native.PB_BDD,
        integer_native.PB_SWC,
        integer_native.PB_SORTINGNETWORKS,
        integer_native.PB_ADDER,
        integer_native.PB_BINARY_MERGE,
        integer_native.PB_LPW,
    ],
)
def test_clause_budget_applies_to_every_native_encoder(encoder):
    with pytest.raises(integer_native.EncodingBudgetExceeded, match="clauses"):
        encode(encoder=encoder, clause_limit=1)
    # A later unrestricted call must still be valid after unwinding that encoder.
    clauses, _ = encode(encoder=encoder)
    with Solver(name="g4", bootstrap_with=clauses) as solver:
        for values in itertools.product([False, True], repeat=4):
            assert solver.solve(
                assumptions=[i if v else -i for i, v in enumerate(values, 1)]
            ) == (sum(w * v for w, v in zip([2, 3, 4, 5], values)) <= 7)


def test_external_counter_against_exhaustive_prefix_sums():
    import random

    rng = random.Random(24971)
    for _ in range(120):
        weights = sorted([1] + [rng.randint(1, 9) for _ in range(5)], reverse=True)
        total = sum(weights)
        if total < 2 * max(weights):
            continue
        bound = rng.randint(max(weights), total - max(weights))
        for comparator in [integer_native.LEQ, integer_native.GEQ, integer_native.BOTH]:
            expected = 0
            for i in range(len(weights)):
                sums = {
                    sum(w * b for w, b in zip(weights[:i], bits))
                    for bits in itertools.product([0, 1], repeat=i)
                }
                remaining = sum(weights[i:])
                for value in sums:
                    if comparator == integer_native.LEQ:
                        expected += value <= bound < value + remaining
                    elif comparator == integer_native.GEQ:
                        expected += value < bound <= value + remaining
                    else:
                        expected += value <= bound <= value + remaining
            assert (
                integer_native.count_states(weights, bound, comparator, 0) == expected
            )


def test_counter_normalization_and_large_numeric_ranges():
    weights = [2, 3, 5, 7]
    for cmp in [integer_native.LEQ, integer_native.GEQ, integer_native.BOTH]:
        expected = integer_native.count_states(weights, 8, cmp, 0)
        assert (
            integer_native.count_states(list(reversed(weights)), 8, cmp, 0) == expected
        )
        assert (
            integer_native.count_states([6 * w for w in weights], 48, cmp, 0)
            == expected
        )
    assert (
        integer_native.count_states(
            [6 * w for w in weights], 49, integer_native.BOTH, 0
        )
        == 0
    )
    large = [1 << shift for shift in [0, 10, 20, 30, 40, 50] for _ in range(10)]
    assert (
        integer_native.count_states(large, sum(large) // 2, integer_native.LEQ, 20_000)
        < 20_000
    )


@pytest.mark.parametrize("weights", [[0], [-1], [2**62, 2**62]])
def test_counter_rejects_invalid_native_ranges(weights):
    with pytest.raises((ValueError, OverflowError)):
        integer_native.count_states(weights, 1, integer_native.LEQ, 20_000)
