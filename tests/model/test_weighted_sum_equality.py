"""Weighted equality fast path: routing, semantics, gating and fallback."""
import itertools
import random
from unittest.mock import patch

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.encoder.pb_enc import PBEnc
from hermax.encoder.pbamo import PBAMOEnc
from hermax.encoder import _weighted_sum
from hermax.encoder._weighted_sum.grouped import GroupedPlan
from hermax.encoder._weighted_sum.graph import GraphPlan
from hermax.model.encoders import _EncoderDispatch
from hermax.model.expressions import PBExpr


def assignment():
    model = Model()
    x = model.bool_matrix('x', 4, 4)
    for i in range(4):
        model &= sum(x[i, j] for j in range(4)) == 1
        model &= sum(x[j, i] for j in range(4)) == 1
    rng = random.Random(164)
    weights = [rng.randint(1, 125) for _ in range(16)]
    total = model.int('total', 0, 500)
    expr = sum(weights[4*i+j] * x[i, j] for i in range(4) for j in range(4))
    return model, x, weights, total, expr


def test_assignment_uses_fast_path_without_native_encoding():
    model, x, weights, total, expr = assignment()
    with (patch.object(PBEnc, 'equals', side_effect=AssertionError('PB equality encoded')),
          patch.object(PBEnc, 'leq', side_effect=AssertionError('PB inequality encoded'))):
        model &= total == expr
    cnf = model.to_cnf()
    assert len(cnf.clauses) < 5000
    assert cnf.nv < 2000
    with Solver(name='g4', bootstrap_with=cnf.clauses) as solver:
        for permutation in itertools.permutations(range(4)):
            expected = sum(weights[4*i+permutation[i]] for i in range(4))
            inputs = [x[i,j].id if permutation[i] == j else -x[i,j].id
                      for i in range(4) for j in range(4)]
            thresholds = [lit.id if value <= expected else -lit.id
                          for value, lit in enumerate(total._threshold_lits, 1)]
            assert solver.solve(assumptions=inputs + thresholds)
            wrong = [-lit.id for lit in total._threshold_lits]
            assert not solver.solve(assumptions=inputs + wrong)


def test_both_orientations_and_conditional_equality():
    for reverse, conditional in itertools.product((False, True), repeat=2):
        model, x, weights, total, expr = assignment()
        condition = model.bool('enabled')
        constraint = (expr == total) if reverse else (total == expr)
        with (patch.object(PBEnc, 'equals', side_effect=AssertionError('PB encoded')),
              patch.object(PBEnc, 'leq', side_effect=AssertionError('PB encoded'))):
            model &= constraint.only_if(condition) if conditional else constraint
        inputs = [x[i,j].id if i == j else -x[i,j].id
                  for i in range(4) for j in range(4)]
        expected = sum(weights[5*i] for i in range(4))
        thresholds = [lit.id if value <= expected else -lit.id
                      for value, lit in enumerate(total._threshold_lits, 1)]
        with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
            assert solver.solve(assumptions=inputs + thresholds + [condition.id])
            wrong = [-lit.id for lit in total._threshold_lits]
            assert not solver.solve(assumptions=inputs + wrong + [condition.id])
            if conditional:
                assert solver.solve(assumptions=inputs + wrong + [-condition.id])


def test_unsupported_restricted_domain_is_read_only_and_uses_budgeted_fallback():
    import hermax.model.encoders as encoders
    model = Model()
    bits = [model.bool() for _ in range(3)]
    total = model.int('t', 0, 60)
    expr = sum(w*b for w,b in zip([13, 21, 34], bits))
    before = model._top_id(), tuple(model._hard)
    result = _EncoderDispatch._try_weighted_sum_eq_fastpath(
        model, PBExpr.from_item(total), '==', expr)
    assert result is None
    assert (model._top_id(), tuple(model._hard)) == before
    with patch.object(encoders, 'compile_weighted_sum', wraps=encoders.compile_weighted_sum) as fallback:
        model &= total == expr
    fallback.assert_called_once()


def test_fast_path_is_deterministic():
    formulas = []
    for _ in range(2):
        model, _, _, total, expr = assignment()
        model &= expr == total
        cnf = model.to_cnf()
        formulas.append((cnf.nv, cnf.clauses))
    assert formulas[0] == formulas[1]


def test_public_value_exclusions_propagate_through_the_graph():
    model = Model()
    bits = [model.bool() for _ in range(3)]
    total = model.int('t', 0, 68)
    weights = [13, 21, 34]
    with patch.object(PBEnc, 'equals', side_effect=AssertionError('PB encoded')):
        model &= total == sum(w*b for w,b in zip(weights, bits))
    values = {v: model._lit_to_dimacs(total == v) for v in range(69)}
    assert len(total._eq_lits) == 69
    rng = random.Random(42)
    assignments = list(itertools.product((False, True), repeat=3))
    with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
        for _ in range(300):
            partial = [rng.choice((None, False, True)) for _ in bits]
            allowed = {sum(w*b for w,b in zip(weights, a)) for a in assignments
                       if rng.choice((False, True))}
            feasible = [a for a in assignments
                        if all(p is None or p == b for p,b in zip(partial,a))
                        and sum(w*b for w,b in zip(weights,a)) in allowed]
            assumptions = [bit.id if p else -bit.id for bit,p in zip(bits,partial) if p is not None]
            assumptions += [-lit for v,lit in values.items() if v not in allowed]
            ok, implied = solver.propagate(assumptions=assumptions)
            assert ok == bool(feasible)
            if feasible:
                implied = set(implied) | set(assumptions)
                for i,bit in enumerate(bits):
                    supported = {a[i] for a in feasible}
                    if len(supported) == 1:
                        assert (bit.id if True in supported else -bit.id) in implied


def test_repeated_equality_reuses_the_compiler_cache_and_value_literals():
    model, _, _, total, expression = assignment()
    existing_value = total == 34
    model &= total == expression
    before = model._top_id()
    with patch('hermax.encoder._weighted_sum.encode_best',
               side_effect=AssertionError('cached equality encoded again')):
        model &= total == expression
    assert model._top_id() == before
    assert (total == 34) is existing_value


def test_both_candidates_are_built_but_only_the_winner_is_committed():

    model = Model()
    bits = [model.bool() for _ in range(8)]
    weights = [1, 2]*4
    total = model.int('t', 0, sum(weights))
    expression = sum(w*b for w,b in zip(weights, bits))
    # Create shared public definitions before observing private allocations.
    for value in range(total.ub+1):
        model._lit_to_dimacs(total == value)
    start_top, start_hard = model._top_id(), tuple(model._hard)
    built = []
    original = _weighted_sum.encode_candidate

    def observe(plan, thresholds, top_id, values):
        assert top_id == start_top
        assert model._top_id() == start_top
        cnf = original(plan, thresholds, top_id, values)
        built.append((plan, cnf))
        return cnf

    with patch.object(_weighted_sum, 'encode_candidate', side_effect=observe):
        result = _EncoderDispatch._try_weighted_sum_eq_fastpath(
            model, PBExpr.from_item(total), '==', expression)
    assert {type(plan) for plan, _ in built} == {GraphPlan, GroupedPlan}
    winner = min((cnf for _,cnf in built), key=lambda cnf: (len(cnf.clauses), cnf.nv))
    assert len(result) == len(winner.clauses)
    assert model._top_id() == winner.nv
    assert tuple(model._hard) == start_hard


@pytest.mark.parametrize('reverse,conditional', itertools.product((False, True), repeat=2))
def test_grouped_sum_with_signed_inputs_and_optional_guard(reverse, conditional):
    model = Model()
    bits = [model.bool() for _ in range(3)]
    inputs = [bits[0], ~bits[1], bits[2]]
    weights = [2, 3, 2]
    total = model.int('t', 0, sum(weights))
    enabled = model.bool('enabled')
    expression = sum(w*b for w,b in zip(weights, inputs))
    constraint = expression == total if reverse else total == expression
    with patch.object(PBAMOEnc, 'auto_eq', side_effect=AssertionError('PB fallback used')):
        model &= constraint.only_if(enabled) if conditional else constraint
    with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
        for assignment in itertools.product((False, True), repeat=3):
            expected = 2*assignment[0]+3*(not assignment[1])+2*assignment[2]
            assumptions = [bit.id if value else -bit.id for bit,value in zip(bits, assignment)]
            for value in range(total.ub+1):
                cuts = [lit.id if i <= value else -lit.id
                        for i,lit in enumerate(total._threshold_lits, 1)]
                assert solver.solve(assumptions=assumptions+cuts+[enabled.id]) == (value == expected)
                if conditional:
                    assert solver.solve(assumptions=assumptions+cuts+[-enabled.id])


def test_equal_weights_use_the_counting_fast_path():
    model = Model()
    bits = [model.bool() for _ in range(64)]
    total = model.int('t', 0, 128)
    with patch.object(PBEnc, 'equals', side_effect=AssertionError('PB encoded')):
        model &= total == sum(2 * bit for bit in bits)
    cnf = model.to_cnf()
    assert cnf.nv < 2000
    assert len(cnf.clauses) < 5000
    with Solver(name='g4', bootstrap_with=cnf.clauses) as solver:
        for count in (0, 1, 31, 63, 64):
            inputs = [bit.id if i < count else -bit.id for i,bit in enumerate(bits)]
            expected = [lit.id if i <= 2*count else -lit.id
                        for i,lit in enumerate(total._threshold_lits, 1)]
            assert solver.solve(assumptions=inputs+expected)


def test_count_network_public_value_propagation():
    for size in (8, 16, 32):
        model = Model()
        bits = [model.bool() for _ in range(size)]
        total = model.int('t', 0, 4*size)
        model &= total == sum(4*bit for bit in bits)
        values = {v: model._lit_to_dimacs(total == v) for v in range(4*size+1)}
        rng = random.Random(size)
        with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
            for _ in range(300):
                partial = [rng.choice((None, False, True)) for _ in bits]
                low = sum(p is True for p in partial)
                high = low + partial.count(None)
                allowed = {v for v in range(4*size+1) if rng.randrange(3) == 0}
                possible = {k for k in range(low, high+1) if 4*k in allowed}
                assumptions = [bit.id if p else -bit.id
                               for bit,p in zip(bits,partial) if p is not None]
                assumptions += [-lit for v,lit in values.items() if v not in allowed]
                ok, implied = solver.propagate(assumptions=assumptions)
                assert ok == bool(possible)
                if possible == {low}:
                    assert all(-bit.id in implied for bit,p in zip(bits,partial) if p is None)
                if possible == {high}:
                    assert all(bit.id in implied for bit,p in zip(bits,partial) if p is None)
