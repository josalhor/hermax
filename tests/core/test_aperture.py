import pytest

from hermax.core.aperture_py import ApertureSolver
from hermax.core.ipamir_solver_interface import SolveStatus


pytestmark = pytest.mark.skipif(
    not ApertureSolver.is_available(),
    reason="ApertureSolver is not available in this build.",
)


def test_aperture_incremental_weighted_maxsat():
    solver = ApertureSolver()
    try:
        solver.add_clause([1, 2])
        solver.add_clause([-1, -2])
        solver.set_soft(-1, 10)
        solver.set_soft(-2, 5)

        assert solver.solve()
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert solver.get_cost() == 5
        assert solver.get_model() == [-1, 2]

        assert solver.solve([1])
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert solver.get_cost() == 10
        assert solver.get_model() == [1, -2]

        assert solver.solve()
        assert solver.get_cost() == 5

        solver.set_soft(-2, 0)
        assert solver.solve()
        assert solver.get_cost() == 0
    finally:
        solver.close()


def test_aperture_unsat_and_explicit_variables():
    solver = ApertureSolver()
    try:
        assert solver.new_var() == 1
        assert solver.new_var() == 2
        solver.add_clause([1])
        solver.add_clause([-1])
        assert not solver.solve()
        assert solver.get_status() == SolveStatus.UNSAT
    finally:
        solver.close()
