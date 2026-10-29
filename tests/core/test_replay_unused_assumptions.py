import pytest

from hermax.core.rc2.rc2_reentrant import RC2Reentrant


@pytest.mark.parametrize("time_limit", [None, 2])
@pytest.mark.parametrize("assumed", [3, -3])
def test_rc2_preserves_assumption_values_without_persisting_their_variables(time_limit, assumed):
    solver = RC2Reentrant()
    try:
        solver.add_clause([1])
        solver.add_soft_unit(-1, 3)
        assert solver.solve(assumptions=[assumed], time_limit=time_limit)
        assert assumed in solver.get_model()
        assert solver.get_cost() == 3
        assert solver.new_var() == 2
        assert solver.solve(assumptions=[-assumed])
        assert -assumed in solver.get_model()
    finally:
        solver.close()


def test_timed_rc2_keeps_assumption_variables_separate_from_relaxations():
    solver = RC2Reentrant()
    try:
        solver.add_clause([1, 2], weight=3)
        assert solver.solve(assumptions=[3], time_limit=2)
        assert 3 in solver.get_model()
        assert solver.get_cost() == 0
    finally:
        solver.close()
