"""A definitive answer is distinct from an available assignment."""

import pytest

from hermax.model import Model, SolveResult
from hermax.core.ipamir_replay_base import ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.non_incremental.incomplete import NuWLSCIBR


@pytest.mark.parametrize(
    ("status", "ok", "proven"),
    [
        ("sat", True, True),
        ("optimum", True, True),
        ("unsat", False, True),
        ("interrupted_sat", True, False),
        ("interrupted", False, False),
        ("unknown", False, False),
        ("error", False, False),
    ],
)
def test_result_status_proven_and_ok(status, ok, proven):
    result = SolveResult(Model(), status=status, raw_model=None, cost=None, backend="test")
    assert result.ok is ok
    assert result.proven is proven


def test_sat_and_unsat_are_proven():
    model = Model()
    x = model.bool("x")
    model &= x
    sat = model.solve()
    assert sat.status == "sat" and sat.ok and sat.proven
    model &= ~x
    unsat = model.solve()
    assert unsat.status == "unsat" and not unsat.ok and unsat.proven


def test_optimal_solution_is_proven():
    model = Model()
    x = model.bool("x")
    model.obj[1] += x
    result = model.solve()
    assert result.status == "optimum" and result.ok and result.proven


def test_incomplete_solver_feasible_result_is_not_proven(monkeypatch):
    def feasible_only(self, assumptions):
        return ReplaySolveResult(status=SolveStatus.INTERRUPTED_SAT, model=[1], cost=None)

    monkeypatch.setattr(NuWLSCIBR, "_run_replay_solve", feasible_only)
    model = Model()
    x = model.bool("x")
    model &= x
    model.obj[1] += ~x
    solver = NuWLSCIBR(default_time_limit=5)
    try:
        result = model.solve(solver=solver, incremental=False)
    finally:
        solver.close()
    assert result.status == "interrupted_sat"
    assert result.ok and not result.proven
    assert result[x] is True


def test_incomplete_solver_actual_result_respects_its_status():
    if not NuWLSCIBR.is_available():
        pytest.skip("NuWLS-c-IBR is not available in this build")
    model = Model()
    x = model.bool("x")
    model &= x
    model.obj[1] += ~x
    solver = NuWLSCIBR(default_time_limit=5)
    try:
        result = model.solve(solver=solver, incremental=False)
    finally:
        solver.close()
    assert result.status in {"interrupted_sat", "optimum"}
    assert result.ok and result[x] is True
    assert result.proven is (result.status == "optimum")
