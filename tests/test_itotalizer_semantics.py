import pytest

from hermax.encoder.card import ITotalizer
from pysat.solvers import Solver


def test_itotalizer_extend_preserves_existing_atmost_bound():
    totalizer = ITotalizer(lits=[1, 2], ubound=0)
    try:
        totalizer.extend(lits=[3], ubound=1)

        # rhs[1] represents that at least two inputs are true.  Its negation
        # therefore enforces the valid at-most-one assignment below.
        assumptions = [-1, -2, 3, -totalizer.rhs[1]]
        with Solver(name="g3", bootstrap_with=totalizer.cnf.clauses) as solver:
            assert solver.solve(assumptions=assumptions)
    finally:
        totalizer.delete()
