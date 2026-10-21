"""Check arithmetic meaning, independently of propagation and backend encoders."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.encoder._weighted_sum.grouped import plan_grouped, encode_grouped
from hermax.encoder._weighted_sum.common import CNFBuilder
from hermax.encoder._weighted_sum.graph import plan_graph, encode_graph
from hermax.encoder._weighted_sum.networks import ComparatorNetwork
from hermax.encoder._weighted_sum import plan_candidates, encode_best


ENCODERS = {
    'original': (plan_graph, encode_graph),
    'grouped': (plan_grouped, encode_grouped),
    'best': (plan_candidates, encode_best),
}


def check_assignments(construction, weights, assignments, *, groups=(), slack=0, signed=False):
    """For each input: accept the correct total and reject ALL incorrect totals."""
    size = len(weights)
    inputs = [-(i+1) if signed and i % 3 == 0 else i+1 for i in range(size)]
    # Exercise signed/nonconsecutive threshold IDs, not just contiguous IDs.
    upper = sum(weights)+slack
    thresholds = [(size+3+2*i)*(-1 if signed and i % 2 else 1) for i in range(upper)]
    top = max(map(abs, thresholds))
    eo = tuple(tuple(inputs[i] for i in group) for group in groups)
    planner, encoder = ENCODERS[construction]
    plan = planner(inputs, weights, upper, eo)
    assert plan, (construction, weights, groups)
    cnf = encoder(plan, thresholds, top)
    clauses = list(cnf.clauses)+[[-b,a] for a,b in zip(thresholds, thresholds[1:])]
    for group in eo:
        clauses.append(list(group))
        clauses.extend([-a,-b] for a,b in itertools.combinations(group, 2))
    wrong_total_selectors = {}
    with Solver(name='g4', bootstrap_with=clauses) as solver:
        for bits in assignments:
            # bits describe the truth of each signed source literal.
            assumptions = [lit if value else -lit for lit,value in zip(inputs, bits)]
            valid = all(sum(bits[i] for i in group) == 1 for group in groups)
            expected = sum(weight*value for weight,value in zip(weights,bits))
            correct = [lit if k <= expected else -lit for k,lit in enumerate(thresholds, 1)]
            assert solver.solve(assumptions=assumptions+correct) == valid, (weights, bits, expected)
            if not valid:
                assert not solver.solve(assumptions=assumptions)
                continue
            if expected not in wrong_total_selectors:
                selector = cnf.nv+len(wrong_total_selectors)+1
                wrong_total_selectors[expected] = selector
                # Under the ordered threshold ladder this single clause means
                # total != expected, covering every incorrect value at once.
                wrong = []
                if expected:
                    wrong.append(-thresholds[expected-1])
                if expected < upper:
                    wrong.append(thresholds[expected])
                solver.add_clause([-selector, *wrong])
            assert not solver.solve(assumptions=assumptions+[wrong_total_selectors[expected]]), (weights, bits)


@pytest.mark.parametrize('construction', ENCODERS)
@pytest.mark.parametrize('seed', range(24))
def test_exhaustive_arithmetic_on_small_mixed_sums(construction, seed):
    rng = random.Random(seed)
    size = rng.randint(4 if seed % 4 == 0 else 3, 8)
    weights = [rng.randint(1, 17) for _ in range(size)]
    weights[1] = weights[0]
    groups = ((0, 2),) if seed % 4 == 0 else ()
    if seed % 8 == 0 and size >= 7:
        groups += ((3, 4, 5),)
    if groups:
        # Keep repeated independent inputs outside the EO groups, so every
        # grouped test must exercise that construction rather than skip it.
        weights[-1] = weights[1]
    check_assignments(construction, weights, itertools.product((False, True), repeat=size),
                      groups=groups, slack=seed % 5, signed=bool(seed % 2))


@pytest.mark.parametrize('construction', ENCODERS)
@pytest.mark.parametrize('group_size', [6, 7, 8, 9, 15, 16, 17, 31, 32, 33, 63, 64, 65])
def test_larger_groups_around_sorting_network_boundaries(construction, group_size):
    # One large coefficient group plus two other coefficients exercises the
    # grouped counter AND its connection to the outer graph.
    weights = [2]*group_size+[3, 7]
    rng = random.Random(group_size)
    assignments = [tuple([value]*group_size+[a,b])
                   for value,a,b in itertools.product((False, True), repeat=3)]
    assignments += [tuple(rng.choice((False, True)) for _ in weights) for _ in range(24)]
    check_assignments(construction, weights, assignments, slack=3, signed=True)


@pytest.mark.parametrize('construction', ENCODERS)
@pytest.mark.parametrize('weights', [
    (2,)*9+(3,)*9+(5,)*9,
    (2,)*17+(3,)*9+(5,)*7,
    (4,)*16+(6,)*16+(9,)*17,
])
def test_multiple_large_groups_connected_through_the_same_graph(construction, weights):
    rng = random.Random(sum(weights))
    distinct = sorted(set(weights))
    assignments = [tuple(value[w] for w in weights)
                   for flags in itertools.product((False, True), repeat=len(distinct))
                   for value in [dict(zip(distinct,flags))]]
    assignments += [tuple(rng.choice((False, True)) for _ in weights) for _ in range(48)]
    check_assignments(construction, weights, assignments, slack=5, signed=True)


@pytest.mark.parametrize('construction', ENCODERS)
@pytest.mark.parametrize('weights', [(12, 12, 24, 36), (125, 125, 1, 250), (7,)*9, (1, 1, 2, 4, 8, 16)])
def test_gaps_common_divisors_and_repeated_transition_costs(construction, weights):
    check_assignments(construction, weights, itertools.product((False, True), repeat=len(weights)),
                      slack=5, signed=True)


@pytest.mark.parametrize('inputs', [
    [1], [1, -1], [1, 1, -2, 2, -1],
    [1, -2, 3, -4, 5, -6, 7, -8, 9],
])
def test_sorting_gate_simplifications_preserve_all_output_bits(inputs):
    cnf = CNFBuilder([], max(map(abs, inputs)))
    outputs = ComparatorNetwork(cnf).sort(inputs)
    source_ids = sorted(set(map(abs, inputs)))
    with Solver(name='g4', bootstrap_with=cnf.clauses) as solver:
        for bits in itertools.product((False, True), repeat=len(source_ids)):
            values = dict(zip(source_ids, bits))
            count = sum(values[abs(lit)] if lit > 0 else not values[-lit] for lit in inputs)
            assumptions = [lit if values[lit] else -lit for lit in source_ids]
            assert solver.solve(assumptions=assumptions)
            for position, output in enumerate(outputs):
                expected = position < count
                if type(output) is bool:
                    assert output == expected
                else:
                    assert not solver.solve(assumptions=assumptions+[-output if expected else output])
