"""Direct weighted thresholds: full truth tables, EO shifts and size bounds."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.encoder._weighted_sum.sorting import plan_sorting, encode_sorting
from hermax.encoder._weighted_sum.grouped import plan_grouped, encode_grouped
from hermax.encoder._weighted_sum import plan_by_estimate, encode_candidate, plan_candidates, encode_best


@pytest.mark.parametrize('seed', range(24))
@pytest.mark.parametrize('construction', ['sorting', 'buckets', 'refined', 'best'])
def test_all_assignments_and_values(seed, construction):
    rng = random.Random(seed)
    size = rng.randint(2, 5)
    weights = [rng.randint(1, 3) for _ in range(size)]
    lits = [(-1 if rng.randrange(2) else 1)*(i+1) for i in range(size)]
    groups = (tuple(lits[:2]),) if seed % 3 == 0 else ()
    upper = sum(weights)+seed % 4
    thresholds = list(range(size+1, size+upper+1))
    planner, encoder = dict(sorting=(plan_sorting, encode_sorting),
                            buckets=(plan_grouped, encode_grouped),
                            refined=(plan_by_estimate, encode_candidate),
                            best=(plan_candidates, encode_best))[construction]
    plan = planner(lits, weights, upper, groups)
    if plan is None:
        assert construction in ('buckets', 'refined')
        return
    cnf = encoder(plan, thresholds, thresholds[-1])
    assert cnf == encoder(plan, thresholds, thresholds[-1])
    clauses = list(cnf.clauses)+[[-b, a] for a,b in zip(thresholds, thresholds[1:])]
    for group in groups:
        clauses.append(list(group))
        clauses.extend([[-a, -b] for a,b in itertools.combinations(group, 2)])
    with Solver(name='g4', bootstrap_with=clauses) as solver:
        for bits in itertools.product((False, True), repeat=size):
            valid = not groups or sum(bits[:2]) == 1
            expected = sum(w*b for w,b in zip(weights, bits))
            inputs = [lit if bit else -lit for lit,bit in zip(lits,bits)]
            for value in range(upper+1):
                cuts = [lit if i <= value else -lit for i,lit in enumerate(thresholds, 1)]
                assert solver.solve(assumptions=inputs+cuts) == (valid and value == expected)


def test_large_coefficients_are_planned_without_expanding_them():
    plan = plan_sorting([1, 2], [2**30, 2**30+1], 2**31+1)
    assert plan is not None
    assert plan.tokens == 2**31+1


def test_interchangeable_choices_can_reduce_to_a_constant():
    plan = plan_sorting([1, 2], [5, 5], 10, [(1, 2)])
    assert plan.tokens == 0
    assert plan.shift == 5
