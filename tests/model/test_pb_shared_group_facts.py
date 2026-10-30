"""Model facts stay shared while standalone PB encodings remain self-contained."""
import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.model.expressions import sum_expr


@pytest.mark.parametrize("kind", ["at_most_one", "exactly_one"])
def test_weighted_bounds_do_not_reencode_model_group(kind):
    m = Model()
    bits = m.bool_vector("b", 512)
    m &= getattr(bits, kind)()
    rng = random.Random(78)
    for _ in range(100):
        costs = [1] + [rng.randint(1, 99) for _ in range(511)]
        m &= sum_expr([cost * bit for cost, bit in zip(costs, bits)]) <= 60
    cnf = m.to_cnf()
    assert cnf.nv < 1500
    assert len(cnf.clauses) < 25000


def test_eager_compilation_reuses_pending_group_facts():
    m = Model()
    bits = m.bool_vector("b", 64)
    m &= bits.at_most_one()
    condition = sum_expr([(i + 1) * bit for i, bit in enumerate(bits)]) <= 20
    group = condition.clauses()
    assert len(group) < 80
    m &= group
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        assert solver.solve(assumptions=[bits[0].id])
        assert not solver.solve(assumptions=[bits[0].id, bits[1].id])
        assert not solver.solve(assumptions=[bits[-1].id])


@pytest.mark.parametrize("flush", [False, True])
@pytest.mark.parametrize("context", ["plain", "only_if", "iff"])
def test_reused_group_facts_preserve_model_semantics(flush, context):
    m = Model()
    bits = m.bool_vector("b", 6)
    switch, gate = m.bool("switch"), m.bool("gate")
    m &= sum_expr(bits[:3]) == 1
    m &= sum_expr(bits[2:5]) <= 1
    m &= (bits[4] + bits[5] <= 1).only_if(switch)
    if flush:
        m.to_cnf()
    weights = [2, 3, 0, 7, 11, 13]
    condition = sum_expr([w * b for w, b in zip(weights, bits) if w]) <= 25
    m &= condition if context == "plain" else getattr(condition, context)(gate)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product([False, True], repeat=8):
            chosen, enabled, indicator = values[:6], values[6], values[7]
            truth = sum(w * b for w, b in zip(weights, chosen)) <= 25
            expected = sum(chosen[:3]) == 1 and sum(chosen[2:5]) <= 1
            expected &= not enabled or sum(chosen[4:]) <= 1
            expected &= truth if context == "plain" else (not indicator or truth) if context == "only_if" else indicator == truth
            literals = [b.id for b in bits] + [switch.id, gate.id]
            assert solver.solve(assumptions=[lit if bit else -lit for lit, bit in zip(literals, values)]) == expected
