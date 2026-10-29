import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import Model


@pytest.mark.parametrize(
    "left,right,compare,clauses",
    [((0, 1000), (0, 10), operator.le, 11),
     ((1000, 2000), (0, 1000), operator.le, 2),
     ((500, 1500), (0, 1000), operator.le, 502),
     ((0, 1000), (0, 10), operator.eq, 21),
     ((1000, 2000), (0, 1000), operator.eq, 2)],
)
def test_integer_comparisons_keep_only_necessary_boundary_clauses(left, right, compare, clauses):
    m = Model()
    x, y = m.int("x", *left), m.int("y", *right)
    before = m._top_id(), len(m._hard)
    m &= compare(x, y)
    assert m._top_id() == before[0]
    assert len(m._hard) - before[1] == clauses


@pytest.mark.parametrize("left,right", [((-3, 2), (0, 1)), ((1, 4), (-2, 2)),
                                        ((0, 2), (2, 4)), ((-2, -2), (-3, 1)),
                                        ((-2, 3), (1, 1)), ((0, 1), (3, 4))])
@pytest.mark.parametrize("compare", [operator.le, operator.lt, operator.ge,
                                    operator.gt, operator.eq, operator.ne])
@pytest.mark.parametrize("mode", ["post", "only_if", "iff"])
def test_integer_comparison_boundaries_preserve_truth_tables(left, right, compare, mode):
    m = Model()
    x, y = m.int("x", *left), m.int("y", *right)
    flag = m.bool("flag")
    condition = compare(x, y)
    m &= condition if mode == "post" else getattr(condition, mode)(flag)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, enabled in itertools.product(range(x.lb, x.ub + 1),
                                                range(y.lb, y.ub + 1), (False, True)):
            fixed = [m._lit_to_dimacs(lit) for var, value in [(x, a), (y, b)]
                     for lit in var._exact_value_atoms(value)]
            fixed.append(flag.id if enabled else -flag.id)
            expected = compare(a, b)
            if mode == "only_if":
                expected = not enabled or expected
            elif mode == "iff":
                expected = enabled == expected
            assert solver.solve(assumptions=fixed) is expected, (a, b, enabled)


@pytest.mark.parametrize("shift", [-3, 0, 3])
def test_shifted_integer_comparison_boundaries(shift):
    m = Model()
    x, y = m.int("x", -2, 3), m.int("y", 0, 2)
    m &= x._relop_intvar(y, "<=", offset=-shift)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b in itertools.product(range(-2, 4), range(3)):
            fixed = [m._lit_to_dimacs(lit) for var, value in [(x, a), (y, b)]
                     for lit in var._exact_value_atoms(value)]
            assert solver.solve(assumptions=fixed) is (a <= b + shift)


def test_compressed_boundaries_still_propagate_all_redundant_units_when_enabled():
    m = Model()
    x, y = m.int("x", 20, 40), m.int("y", 0, 20)
    flag = m.bool("flag")
    m &= (x <= y).only_if(flag)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        ok, propagated = solver.propagate(assumptions=[flag.id])
        assert ok
        expected = {-lit.id for lit in x._threshold_lits} | {lit.id for lit in y._threshold_lits}
        assert expected <= set(propagated)
        assert solver.solve(assumptions=[-flag.id, (x >= 40).id, -(y >= 1).id])
