import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import Model, PBExpr


@pytest.mark.parametrize("reverse", [False, True])
def test_zero_integer_product_does_not_materialize_thresholds(reverse):
    m = Model()
    x = m.int("x", -7, 9993)
    before = m._top_id(), len(m._hard)
    expression = 0 * x if reverse else x * 0
    assert isinstance(expression, PBExpr) and expression._model is m
    assert expression.constant == 0 and expression.terms == [] and expression.int_terms == []
    assert not x._threshold_lits._cache
    assert (m._top_id(), len(m._hard)) == before
    m &= x == 13
    result = m.solve()
    assert result.ok and result[x] == 13 and result[expression] == 0
    with pytest.raises(ValueError, match="different models"):
        Model().obj.add(expression, weight=0)


@pytest.mark.parametrize("weighted", [False, True])
def test_zero_bound_integer_sums_use_one_boundary_unit_per_integer(weighted):
    m = Model()
    xs = m.int_vector("x", 6, 0, 1000)
    before = m._top_id(), len(m._hard)
    expression = sum((i + 1 if weighted else 1) * x for i, x in enumerate(xs))
    m &= expression <= 0
    assert m._top_id() == before[0]
    assert len(m._hard) - before[1] == len(xs)
    result = m.solve()
    assert result.ok and result[xs] == [0] * 6


@pytest.mark.parametrize("form", ["plus_zero", "difference"])
def test_arithmetic_comparisons_at_touching_domains_use_only_two_units(form):
    m = Model()
    x, y = m.int("x", 1000, 2000), m.int("y", 0, 1000)
    before = m._top_id(), len(m._hard)
    m &= x + 0 <= y if form == "plus_zero" else x - y <= 0
    assert m._top_id() == before[0]
    assert len(m._hard) - before[1] == 2
    result = m.solve()
    assert result.ok and result[x] == result[y] == 1000


def test_zero_bound_signed_cuts_and_plain_booleans_propagate_when_enabled():
    m = Model()
    x, y = m.int("x", -1, 1), m.int("y", 0, 2)
    a, b, enabled = m.bool("a"), m.bool("b"), m.bool("enabled")
    before = m._top_id(), len(m._hard)
    m &= (3 * (x - x.lb) + 5 * (y.ub - y) + 2 * a + 7 * ~b <= 0).only_if(enabled)
    assert m._top_id() == before[0]
    assert len(m._hard) - before[1] == 4
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        ok, propagated = solver.propagate(assumptions=[enabled.id])
        expected = {-lit.id for lit in x._threshold_lits} | {lit.id for lit in y._threshold_lits}
        expected |= {-a.id, b.id}
        assert ok and expected <= set(propagated)
        fixed = [m._lit_to_dimacs(lit) for var, value in [(x, 1), (y, 0)]
                 for lit in var._exact_value_atoms(value)]
        assert solver.solve(assumptions=fixed + [a.id, -b.id, -enabled.id])


@pytest.mark.parametrize("negative_domains", [False, True])
def test_weighted_comparisons_merge_equivalent_impossible_consequences(negative_domains):
    m = Model()
    if negative_domains:
        x, y = m.int("x", -1500, -500), m.int("y", -1000, 0)
        expression = -3 * x + 2 * y
    else:
        x, y = m.int("x", 500, 1500), m.int("y", 0, 1000)
        expression = 3 * x - 2 * y
    before = m._top_id(), len(m._hard)
    m &= expression <= 0
    assert m._top_id() == before[0]
    assert len(m._hard) - before[1] == 168


@pytest.mark.parametrize("compare", [operator.le, operator.lt, operator.ge,
                                    operator.gt, operator.eq, operator.ne])
@pytest.mark.parametrize("mode", ["post", "only_if", "iff"])
def test_weighted_boundary_reduction_preserves_exact_truth_tables(compare, mode):
    for a, b, bound in itertools.product([3, -3, 2, -2], [-2, 2, 5, -3], [-7, 0, 5]):
        m = Model()
        x, y = m.int("x", -2, 3), m.int("y", 0, 2)
        enabled = m.bool("enabled")
        condition = compare(a * x + b * y, bound)
        m &= condition if mode == "post" else getattr(condition, mode)(enabled)
        with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
            for xv, yv, on in itertools.product(range(-2, 4), range(3), [False, True]):
                truth = compare(a * xv + b * yv, bound)
                if mode == "only_if":
                    truth = not on or truth
                elif mode == "iff":
                    truth = on == truth
                fixed = [m._lit_to_dimacs(lit) for var, value in [(x, xv), (y, yv)]
                         for lit in var._exact_value_atoms(value)]
                fixed.append(enabled.id if on else -enabled.id)
                assert solver.solve(assumptions=fixed) is truth, (a, b, bound, xv, yv, on)
