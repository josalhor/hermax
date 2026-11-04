"""Bounded BDD selection preserves arithmetic and abandons oversized trials."""
import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.encoder._packed import PBEnc
from hermax.encoder.pb_enc import EncType


@pytest.mark.parametrize('method,compare', [('leq', operator.le), ('geq', operator.ge), ('equals', operator.eq)])
@pytest.mark.parametrize('conditionals', [[], [8, -9]])
def test_bounded_arithmetic_and_guards(method, compare, conditionals):
    weights = [2, 3, 4, 5]
    cnf = getattr(PBEnc, method)(lits=[1, 2, 3, 4], weights=weights, bound=7,
                               top_id=12, conditionals=conditionals, encoding=EncType.bounded)
    with Solver(name='g4', bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product([False, True], repeat=6):
            assignment = dict(zip([1, 2, 3, 4, 8, 9], values))
            enabled = all(assignment[abs(lit)] == (lit > 0) for lit in conditionals)
            expected = not enabled or compare(sum(w * b for w, b in zip(weights, values)), 7)
            assert solver.solve(assumptions=[v if b else -v for v, b in assignment.items()]) == expected


def test_bounded_accepts_small_bdd_without_leaking_trial_ids():
    kwargs = dict(lits=list(range(1, 57)), weights=[1 << j for _ in range(8) for j in range(7)],
                  bound=400, top_id=100)
    bdd = PBEnc.geq(**kwargs, encoding=EncType.bdd)
    bounded = PBEnc.geq(**kwargs, encoding=EncType.bounded)
    assert bounded.nv == bdd.nv
    assert list(bounded.clauses) == list(bdd.clauses)


def test_bounded_abandons_wide_weighted_bdd_and_preserves_adder_ids():
    coefficients = [1, 3, 7, 19, 101, 1009, 10007, 100003]
    kwargs = dict(lits=list(range(1, 241)),
                  weights=[c << j for c in coefficients for j in range(30)],
                  bound=sum(coefficients) * 10**9 // 2, top_id=300)
    adder = PBEnc.geq(**kwargs, encoding=EncType.adder)
    for _ in range(2):
        bounded = PBEnc.geq(**kwargs, encoding=EncType.bounded)
        assert bounded.nv == adder.nv
        assert list(bounded.clauses) == list(adder.clauses)
