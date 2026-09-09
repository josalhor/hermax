import pytest

from hermax.portfolio import PortfolioSolver
from hermax.portfolio._test_solvers import BadModelCostSolver, NonIntegerCostSolver


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


def test_portfolio_rejects_non_integer_worker_costs():
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
