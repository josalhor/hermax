"""Arithmetic soundness through public APIs, guards, caching and shared literals."""
import itertools
from unittest.mock import patch

import pytest
from pysat.solvers import Solver

from hermax.encoder import _weighted_sum
from hermax.encoder.pbamo import PBAMOEnc
from hermax.model import Model


def cuts(model, total, value):
    return [model._lit_to_dimacs(lit if k <= value else ~lit)
            for k,lit in enumerate(total._threshold_lits, 1)]


@pytest.mark.parametrize('same_expression', [False, True])
@pytest.mark.parametrize('export_between', [False, True])
def test_two_guarded_equalities_sharing_a_total_and_inputs(same_expression, export_between):
    model = Model()
    bits = [model.bool() for _ in range(5)]
    first, second = model.bool(), model.bool()
    weights_a, weights_b = [2, 2, 3, 3, 5], [3, 2, 2, 5, 3]
    signed = [bits[0], ~bits[1], bits[2], bits[3], ~bits[4]]
    total = model.int('total', 0, 15)
    expr_a = sum(w*b for w,b in zip(weights_a, signed))
    expr_b = expr_a if same_expression else sum(w*b for w,b in zip(weights_b, signed))
    with (patch.object(PBAMOEnc, 'auto_eq', side_effect=AssertionError('PB fallback used')),
          patch.object(_weighted_sum, 'encode_best', wraps=_weighted_sum.encode_best) as encode):
        model &= (total == expr_a).only_if(first)
        if export_between:
            model.to_cnf()
        model &= (total == expr_b).only_if(~second)
    assert encode.call_count == (1 if same_expression else 2)
    with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
        for values in itertools.product((False, True), repeat=7):
            raw, enabled_a, disabled_b = values[:5], values[5], values[6]
            signed_values = [raw[0], not raw[1], raw[2], raw[3], not raw[4]]
            a = sum(w*b for w,b in zip(weights_a, signed_values))
            b = a if same_expression else sum(w*b for w,b in zip(weights_b, signed_values))
            assumptions = [lit.id if value else -lit.id
                           for lit,value in zip(bits+[first,second], values)]
            for value in range(total.ub+1):
                expected = (not enabled_a or value == a) and (disabled_b or value == b)
                assert solver.solve(assumptions=assumptions+cuts(model,total,value)) == expected


@pytest.mark.parametrize('guarded_first', [False, True])
def test_cached_equality_can_be_used_with_and_without_a_guard(guarded_first):
    model = Model()
    bits = [model.bool() for _ in range(4)]
    total = model.int('total', 0, 10)
    expr = 2*bits[0]+2*~bits[1]+3*bits[2]+3*bits[3]
    # The guard itself is an input to the sum.
    equality = total == expr
    statements = [equality.only_if(bits[0]), equality]
    if not guarded_first:
        statements.reverse()
    with patch.object(_weighted_sum, 'encode_best', wraps=_weighted_sum.encode_best) as encode:
        for statement in statements:
            model &= statement
    assert encode.call_count == 1
    with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
        for raw in itertools.product((False, True), repeat=4):
            expected = 2*raw[0]+2*(not raw[1])+3*raw[2]+3*raw[3]
            assumptions = [bit.id if value else -bit.id for bit,value in zip(bits,raw)]
            for value in range(total.ub+1):
                assert solver.solve(assumptions=assumptions+cuts(model,total,value)) == (value == expected)


def test_compilation_without_posting_does_not_enforce_the_discarded_equality():
    model = Model()
    bits = [model.bool() for _ in range(4)]
    total = model.int('total', 0, 12)
    discarded = (total == 2*bits[0]+2*bits[1]+3*bits[2]+3*bits[3]).clauses()
    assert discarded
    # Allocate a public variable after the private candidate buffers were freed.
    extra = model.bool()
    model &= total == 3*bits[0]+3*~bits[1]+2*bits[2]+2*bits[3]+2*extra
    with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
        for raw in itertools.product((False, True), repeat=5):
            expected = 3*raw[0]+3*(not raw[1])+2*raw[2]+2*raw[3]+2*raw[4]
            assumptions = [bit.id if value else -bit.id for bit,value in zip(bits+[extra],raw)]
            for value in range(total.ub+1):
                assert solver.solve(assumptions=assumptions+cuts(model,total,value)) == (value == expected)


@pytest.mark.parametrize('conditional_group', [False, True])
def test_conditional_and_overlapping_exactly_one_facts_are_not_misused(conditional_group):
    model = Model()
    bits = [model.bool() for _ in range(5)]
    enabled = model.bool()
    signed = [bits[0], ~bits[1], bits[2], ~bits[3], bits[4]]
    first_group = sum(signed[:3]) == 1
    model &= first_group.only_if(enabled) if conditional_group else first_group
    model &= sum(signed[2:4]) == 1
    weights = [2, 2, 5, 7, 7]
    total = model.int('total', 0, sum(weights))
    with patch.object(PBAMOEnc, 'auto_eq', side_effect=AssertionError('PB fallback used')):
        model &= total == sum(w*b for w,b in zip(weights,signed))
    with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
        for raw in itertools.product((False, True), repeat=6):
            values = [raw[0], not raw[1], raw[2], not raw[3], raw[4]]
            valid = ((conditional_group and not raw[5]) or sum(values[:3]) == 1) and sum(values[2:4]) == 1
            expected = sum(w*b for w,b in zip(weights,values))
            assumptions = [bit.id if value else -bit.id for bit,value in zip(bits+[enabled],raw)]
            for value in range(total.ub+1):
                assert solver.solve(assumptions=assumptions+cuts(model,total,value)) == (valid and value == expected)


@pytest.mark.parametrize('constant_groups', [False, True])
def test_signed_exactly_one_groups_with_equal_contributions(constant_groups):
    model = Model()
    bits = [model.bool() for _ in range(7)]
    signed = [~bit if i % 2 else bit for i,bit in enumerate(bits)]
    groups = ((0,1,2), (3,4), (5,6))
    for group in groups:
        model &= sum(signed[i] for i in group) == 1
    weights = [4, 4 if constant_groups else 6, 4, 2, 2, 7, 7]
    # Exercise a domain tightened using valid EO facts, as in assignment models.
    total = model.int('total', 0, sum(max(weights[i] for i in group) for group in groups))
    with patch.object(PBAMOEnc, 'auto_eq', side_effect=AssertionError('PB fallback used')):
        model &= total == sum(w*b for w,b in zip(weights,signed))
    with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
        for raw in itertools.product((False, True), repeat=7):
            values = [not value if i % 2 else value for i,value in enumerate(raw)]
            valid = all(sum(values[i] for i in group) == 1 for group in groups)
            expected = sum(w*b for w,b in zip(weights,values))
            assumptions = [bit.id if value else -bit.id for bit,value in zip(bits,raw)]
            for value in range(total.ub+1):
                assert solver.solve(assumptions=assumptions+cuts(model,total,value)) == (valid and value == expected)


def test_total_value_predicate_can_also_be_an_input_to_its_equality():
    model = Model()
    bits = [model.bool() for _ in range(2)]
    total = model.int('total', 0, 7)
    is_three = total == 3
    model &= total == 2*is_three+2*bits[0]+3*bits[1]
    with Solver(name='g4', bootstrap_with=model.to_cnf().clauses) as solver:
        for raw in itertools.product((False, True), repeat=2):
            assumptions = [bit.id if value else -bit.id for bit,value in zip(bits,raw)]
            for value in range(total.ub+1):
                expected = value == 2*(value == 3)+2*raw[0]+3*raw[1]
                assert solver.solve(assumptions=assumptions+cuts(model,total,value)) == expected
