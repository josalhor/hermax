import itertools

import pytest
from pysat.solvers import Solver


@pytest.mark.parametrize("encoder", ["mdd", "ggpw", "glpw", "gmto", "rggt"])
@pytest.mark.parametrize("bound,weights", [
    ((1 << 64) - 1, [(1 << 64) - 1, 1]),
    ((1 << 64) - 2, [(1 << 63) + 1, (1 << 63) - 1]),
])
def test_unsigned_boundary_matches_integer_oracle(pbamo_module, encoder, bound, weights):
    from hermax.internal import _pbamo

    clauses, _ = _pbamo.encode_leq(list(zip([1, 2], weights)), [[1], [2]], bound, 0, encoder, True)
    with Solver(bootstrap_with=clauses) as solver:
        for values in itertools.product([False, True], repeat=2):
            assumptions = [i if value else -i for i, value in enumerate(values, 1)]
            assert solver.solve(assumptions=assumptions) == (sum(w for w, v in zip(weights, values) if v) <= bound)


def test_gmto_ignores_large_infeasible_coefficient(pbamo_module):
    from hermax.internal import _pbamo

    clauses, _ = _pbamo.encode_leq([(1, (1 << 64) - 59), (2, 2), (3, 3)], [[1], [2], [3]], 4, 0, "gmto", True)
    with Solver(bootstrap_with=clauses) as solver:
        assert not solver.solve(assumptions=[1])
        assert not solver.solve(assumptions=[2, 3])
        assert solver.solve(assumptions=[-1, 2, -3])
