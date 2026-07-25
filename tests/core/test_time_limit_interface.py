import inspect

from hermax.core.ipamir_solver_interface import IPAMIRSolver
import hermax.incremental as incremental
import hermax.non_incremental as non_incremental
import hermax.non_incremental.incomplete as incomplete
from hermax.portfolio import PortfolioSolver


def test_all_public_ipamir_solvers_accept_time_limit():
    solver_classes = [PortfolioSolver]
    for module in (incremental, non_incremental, incomplete):
        solver_classes.extend(getattr(module, name) for name in module.__all__)

    for solver_class in solver_classes:
        if not isinstance(solver_class, type) or not issubclass(solver_class, IPAMIRSolver):
            continue
        assert issubclass(solver_class, IPAMIRSolver)
        assert "time_limit" in inspect.signature(solver_class.solve).parameters
