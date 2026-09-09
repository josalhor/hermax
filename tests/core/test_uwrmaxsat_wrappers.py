import pytest

from hermax.core import urmaxsat_comp_py, urmaxsat_py
from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.core.uwrmaxsat_comp_py.urmaxsat_solver import UWrMaxSATCompSolver
from hermax.core.uwrmaxsat_py.urmaxsat_solver import UWrMaxSATSolver


class _InterruptedWithIncumbent:
    def __init__(self):
        self.num_vars = 0

    def newVar(self):
        self.num_vars += 1
        return self.num_vars

    def addClause(self, clause, weight):
        return None

    def assume(self, assumptions):
        return None

    def solve(self):
        return int(SolveStatus.INTERRUPTED_SAT)

    def getValue(self, var):
        return var == 1

    def getCost(self):
        return 7

    def signature(self):
        return "fake-uwr"

    def set_terminate(self, callback):
        return None


class _KeyboardInterruptingNative:
    def __init__(self):
        self.num_vars = 0

    def newVar(self):
        self.num_vars += 1
        return self.num_vars

    def addClause(self, clause, weight):
        return None

    def assume(self, assumptions):
        return None

    def solve(self):
        raise KeyboardInterrupt

    def signature(self):
        return "fake-uwr"

    def set_terminate(self, callback):
        return None


@pytest.mark.parametrize(
    ("module", "solver_class", "expected_cost"),
    [
        (urmaxsat_py, UWrMaxSATSolver, 0),
        (urmaxsat_comp_py, UWrMaxSATCompSolver, 7),
    ],
)
def test_interrupted_sat_preserves_incumbent_model_and_cost(
    monkeypatch, module, solver_class, expected_cost
):
    monkeypatch.setattr(module, "UWrMaxSAT", _InterruptedWithIncumbent)
    solver = solver_class()
    solver.set_soft(1, 7)

    assert solver.solve() is True
    assert solver.get_status() == SolveStatus.INTERRUPTED_SAT
    assert solver.get_model() == [1]
    assert solver.get_cost() == expected_cost


@pytest.mark.parametrize("solver_class", [UWrMaxSATSolver, UWrMaxSATCompSolver])
def test_uwr_rejects_boolean_soft_weights(solver_class):
    with pytest.raises((TypeError, ValueError)):
        solver_class._normalize_positive_weight(True)
    with pytest.raises((TypeError, ValueError)):
        solver_class._normalize_nonnegative_weight(False)


def test_uwr_is_discarded_after_ctrl_c_during_solve(monkeypatch):
    monkeypatch.setattr(urmaxsat_py, "UWrMaxSAT", _KeyboardInterruptingNative)
    solver = UWrMaxSATSolver()
    solver.add_clause([1])

    with pytest.raises(KeyboardInterrupt):
        solver.solve()

    assert solver.get_status() == SolveStatus.INTERRUPTED
    with pytest.raises(RuntimeError, match="cannot be used after Ctrl-C"):
        solver.add_clause([2])
    with pytest.raises(RuntimeError, match="cannot be used after Ctrl-C"):
        solver.solve()
    with pytest.raises(RuntimeError, match="cannot be used after Ctrl-C"):
        solver.set_terminate(None)
    with pytest.raises(RuntimeError, match="cannot be used after Ctrl-C"):
        solver.get_model()

    solver.close()
    solver.close()
