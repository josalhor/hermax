from hermax.internal import _encoding_policy as policy
import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.encoder._integer_sum import weighted


@pytest.mark.parametrize(
    "chains,coefficients",
    [
        ([[1, 2, 3], [2]], [5, 1]),
        ([[1, 2], [-1, 2]], [3, -3]),
        ([[1, 2], [1, 2]], [5, -5]),
        ([[1], [-1]], [2, 2]),
        ([[1, 2], [2]], [0, 3]),
    ],
)
@pytest.mark.parametrize(
    "comparator,compare",
    [("<=", operator.le), (">=", operator.ge), ("==", operator.eq)],
)
def test_aliases_and_complements_preserve_weighted_truth_table(
    chains, coefficients, comparator, compare, monkeypatch
):
    monkeypatch.setattr(policy, "STATE_LIMIT", 0)
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 0)
    for bound in (-3, 0, 2, 5):
        cnf = weighted.encode_thresholds(chains, coefficients, bound, comparator, 3)
        with Solver(bootstrap_with=cnf.clauses) as solver:
            for values in itertools.product([False, True], repeat=3):
                value = sum(
                    c
                    * sum(
                        values[abs(lit) - 1] if lit > 0 else not values[abs(lit) - 1]
                        for lit in row
                    )
                    for row, c in zip(chains, coefficients)
                )
                fixed = [i + 1 if v else -(i + 1) for i, v in enumerate(values)]
                assert solver.solve(assumptions=fixed) == compare(value, bound)
