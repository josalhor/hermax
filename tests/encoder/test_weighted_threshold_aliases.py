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
@pytest.mark.parametrize("binary", [False, True])
def test_aliases_and_complements_preserve_weighted_truth_table(
    chains, coefficients, comparator, compare, binary, monkeypatch
):
    monkeypatch.setattr(policy, "STATE_LIMIT", 0)
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 0)
    for bound in (-3, 0, 2, 5):
        encode = weighted.encode_binary_views if binary else weighted.encode_thresholds
        cnf = encode(chains, coefficients, bound, comparator, 3)
        with Solver(bootstrap_with=cnf.clauses) as solver:
            for values in itertools.product([False, True], repeat=3):
                value = sum(
                    c
                    * sum(
                        (1 << index if binary else 1)
                        * (values[abs(lit) - 1] if lit > 0 else not values[abs(lit) - 1])
                        for index, lit in enumerate(row)
                    )
                    for row, c in zip(chains, coefficients)
                )
                fixed = [i + 1 if v else -(i + 1) for i, v in enumerate(values)]
                assert solver.solve(assumptions=fixed) == compare(value, bound)


@pytest.mark.parametrize("limit", ["states", "clauses"])
def test_binary_bdd_uses_existing_native_limits(monkeypatch, limit):
    monkeypatch.setattr(policy, "STATE_LIMIT", 1 if limit == "states" else 0)
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 1 if limit == "clauses" else 0)
    with pytest.raises(weighted.BudgetExceeded):
        weighted.encode_binary_views([[1, 2], [3, 4], [5, 6]], [2, 3, 5], 7, ">=", 6, _packed=True)
