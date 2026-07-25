import pytest

from hermax.core.ipamir_solver_interface import SolveStatus


def _solver_class():
    from hermax.core.coretrail_py import CoreTrailSolver

    if not CoreTrailSolver.is_available():
        pytest.skip("CoreTrail native module is not available in this build")
    return CoreTrailSolver


def test_coretrail_incremental_weighted_maxsat():
    solver = _solver_class()()
    try:
        solver.add_clause([1, 2])
        solver.add_clause([-1, -2])
        solver.set_soft(-1, 10)
        solver.set_soft(-2, 5)

        assert solver.solve()
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert solver.get_cost() == 5
        assert solver.get_model() == [-1, 2]

        assert solver.solve(assumptions=[1])
        assert solver.get_cost() == 10

        assert solver.solve()
        assert solver.get_cost() == 5

        solver.set_soft(-2, 0)
        assert solver.solve()
        assert solver.get_cost() == 0
    finally:
        solver.close()


def test_coretrail_deadline_requires_explicit_rebuild_and_recovers():
    solver = _solver_class()()
    try:
        solver.add_clause([1])

        with pytest.raises(RuntimeError, match="set_rebuild_on_interrupt"):
            solver.solve(time_limit=1e-12)

        solver.set_rebuild_on_interrupt(True)
        solver.solve(time_limit=1e-12)
        assert solver.get_status() in {SolveStatus.INTERRUPTED, SolveStatus.INTERRUPTED_SAT}

        assert solver.solve()
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert solver.get_model() == [1]
    finally:
        solver.close()


def test_coretrail_public_exports():
    from hermax.core import CoreTrailSolver
    from hermax.incremental import CoreTrail

    assert CoreTrail.__mro__[1] is CoreTrailSolver
