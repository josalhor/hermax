import pytest

from hermax.portfolio import PortfolioSolver
from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.portfolio._test_solvers import BadModelCostSolver, NonIntegerCostSolver
from hermax.internal.maxsat_cli_parse import parse_maxsat_cli_output


def test_portfolio_rejects_out_of_range_model_literals():
    solver = PortfolioSolver(
        [BadModelCostSolver],
        max_workers=1,
        per_solver_time_limit_s=3.0,
        overall_time_limit_s=5.0,
        validate_model=True,
        invalid_result_policy="drop",
        verbose_invalid=False,
    )

    try:
        assert not solver.solve()
        assert solver.get_status().name in {"ERROR", "INTERRUPTED"}
        assert any(d.get("status") == "INVALID" for d in solver.last_run_details)
    finally:
        solver.close()


@pytest.mark.parametrize("worker_entry", [None, object(), 1])
def test_portfolio_rejects_non_class_worker_entries(worker_entry):
    with pytest.raises((TypeError, ValueError), match="class|solver"):
        solver = PortfolioSolver([worker_entry])
        try:
            solver.signature()
        finally:
            solver.close()


def test_portfolio_add_clause_validation_is_atomic():
    solver = PortfolioSolver([BadModelCostSolver], max_workers=1)

    with pytest.raises((TypeError, ValueError), match="literal|integer|zero"):
        solver.add_clause([3, 0])

    assert solver._num_vars == 0
    assert solver._ops == []
    assert solver._hard_clauses == []
    solver.close()


@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_portfolio_add_soft_relaxed_rejects_non_integer_literals(raw_literal):
    solver = PortfolioSolver([BadModelCostSolver], max_workers=1)

    with pytest.raises((TypeError, ValueError), match="literal|integer"):
        solver.add_soft_relaxed([raw_literal, 2], 3, relax_var=4)

    solver.close()


@pytest.mark.parametrize("relax_var", [True, 1.5, "4"])
def test_portfolio_add_soft_relaxed_rejects_non_integer_relaxation_variables(relax_var):
    solver = PortfolioSolver([BadModelCostSolver], max_workers=1)

    with pytest.raises((TypeError, ValueError), match="relax|literal|integer"):
        solver.add_soft_relaxed([1, 2], 3, relax_var=relax_var)

    solver.close()


def test_portfolio_add_soft_relaxed_validation_is_atomic():
    solver = PortfolioSolver([BadModelCostSolver], max_workers=1)

    with pytest.raises((TypeError, ValueError), match="literal|integer|zero"):
        solver.add_soft_relaxed([3, 0], 3, relax_var=4)

    assert solver._num_vars == 0
    assert solver._ops == []
    assert solver._hard_clauses == []
    assert solver._softs == []
    solver.close()


@pytest.mark.parametrize("raw_assumption", [1.5, True, "1"])
def test_portfolio_solve_rejects_non_integer_assumptions(raw_assumption, monkeypatch):
    solver = PortfolioSolver([BadModelCostSolver], max_workers=1)

    def no_worker(pending, *_args):
        pending.pop(0)
        return None

    monkeypatch.setattr(solver, "_spawn_next_available_worker", no_worker)

    with pytest.raises((TypeError, ValueError), match="assumption|integer"):
        solver.solve(assumptions=[raw_assumption])

    assert solver._num_vars == 0
    solver.close()


def test_portfolio_rejects_non_numeric_worker_costs():
    solver = PortfolioSolver(
        [NonIntegerCostSolver],
        max_workers=1,
        invalid_result_policy="raise",
    )

    try:
        solver.set_soft(1, 1)
        with pytest.raises((TypeError, ValueError)):
            solver.solve()
    finally:
        solver.close()


def test_portfolio_compares_fractional_candidate_costs_exactly():
    solver = PortfolioSolver([BadModelCostSolver], max_workers=1)
    try:
        better = {"status": SolveStatus.OPTIMUM, "cost": 0.1, "model": [1], "solver": "better"}
        worse = {"status": SolveStatus.OPTIMUM, "cost": 0.9, "model": [-1], "solver": "worse"}
        assert solver._choose_best(better, worse) is better
        assert solver._choose_best(worse, better) is better
    finally:
        solver.close()


def test_portfolio_cli_parser_preserves_fractional_objectives():
    status, cost, model = parse_maxsat_cli_output("s OPTIMUM FOUND\no 0.125\nv 1 0", num_vars=1)
    assert status is SolveStatus.OPTIMUM
    assert cost == 0.125
    assert model == [1]
