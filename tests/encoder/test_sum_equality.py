"""Arithmetic construction bounds and exhaustive support-graph semantics."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.encoder._weighted_sum.graph import plan_graph, encode_graph


@pytest.mark.parametrize('seed', range(40))
def test_construction_stays_inside_its_size_bounds(seed):
    rng = random.Random(seed)
    size = rng.randint(2, 7)
    weights = [rng.randint(1, 20) for _ in range(size)]
    lits = [i if rng.choice((False, True)) else -i for i in range(1, size + 1)]
    groups = (tuple(lits[:2]),) if seed % 2 else ()
    upper = sum(weights) if not groups else max(weights[:2]) + sum(weights[2:])
    plan = plan_graph(lits, weights, upper, groups)
    if plan is None:
        assert groups and size == 2 and weights[0] == weights[1]
        return
    thresholds = list(range(size + 1, size + upper + 1))
    cnf = encode_graph(plan, thresholds, thresholds[-1])
    assert cnf.nv - thresholds[-1] <= plan.cost.auxiliary_variables
    assert len(cnf.clauses) <= plan.cost.clauses
    assert cnf == encode_graph(plan, thresholds, thresholds[-1])


@pytest.mark.parametrize('weights,groups', [
    ([2, 3, 5], ()), ([2, 2, 2], ()), ([1, 4, 9], ()),
    ([3, 5, 4, 6], ((1, 2),)), ([4, 4, 2, 7], ((1, 2),)),
    ([3, 5, 4, 6], ((1, 2), (3, 4))),
])
def test_all_input_assignments_and_all_integer_values(weights, groups):
    size, upper = len(weights), sum(weights)
    lits = tuple(range(1, size + 1))
    thresholds = tuple(range(size + 1, size + upper + 1))
    plan = plan_graph(lits, weights, upper, groups)
    cnf = encode_graph(plan, thresholds, thresholds[-1])
    clauses = list(cnf.clauses)
    clauses.extend([[-b, a] for a,b in zip(thresholds, thresholds[1:])])
    for group in groups:
        clauses.append(list(group))
        clauses.extend([[-a, -b] for a,b in itertools.combinations(group, 2)])
    with Solver(name='g4', bootstrap_with=clauses) as solver:
        for bits in itertools.product((False, True), repeat=size):
            valid = all(sum(bits[i-1] for i in group) == 1 for group in groups)
            expected = sum(w*b for w,b in zip(weights,bits))
            inputs = [lit if b else -lit for lit,b in zip(lits,bits)]
            for total in range(upper + 1):
                output = [lit if i <= total else -lit for i,lit in enumerate(thresholds,1)]
                assert solver.solve(assumptions=inputs+output) == (valid and total == expected)


def test_no_restricted_domain_assumptions_or_size_based_rejection():
    assert plan_graph([1, 2], [13, 21], 33) is None
    assert plan_graph(list(range(1, 33)), [1 << i for i in range(32)], (1 << 32)-1) is not None
    assert plan_graph([1, 1], [13, 21], 34) is None
    assert plan_graph([1, 2], [13, 21], 34, [(1, 1)]) is None
