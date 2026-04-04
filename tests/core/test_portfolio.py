from __future__ import annotations

from pathlib import Path

import pytest
from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible
from hermax.incremental import UWrMaxSAT
from hermax.non_incremental import CGSS
from hermax.non_incremental.incomplete import Loandra, OpenWBOInc
from hermax.portfolio import (
    CompletePortfolioSolver,
    IncompletePortfolioSolver,
    PerformancePortfolioSolver,
    PortfolioSolver,
)
from hermax.portfolio.solver import _worker_solver_path_for_class
from hermax.portfolio._test_solvers import BadModelCostSolver


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_small_wcnf(name: str) -> WCNF:
    return WCNF(from_file=str(DATA_DIR / name))


def _pick_available_solver_classes():
    classes = [UWrMaxSAT]
    if CGSS.is_available():
        classes.append(CGSS)
    for cls in (Loandra, OpenWBOInc):
        if cls.is_available():
            classes.append(cls)
    return classes


def test_portfolio_mixed_classes_on_real_data_optimum():
    # Small instance from tests/data to keep runtime stable.
    wcnf = _load_small_wcnf("ram_k3_n9.ra1.wcnf")
    classes = _pick_available_solver_classes()
    p = PortfolioSolver(
        classes,
        formula=wcnf,
        per_solver_timeout_s=5.0,
        overall_timeout_s=8.0,
        selection_policy="first_optimal_or_best_until_timeout",
    )
    ok = p.solve()
    assert ok is True
    assert is_feasible(p.get_status())
    # At least one complete backend should return an optimum on this small instance.
    assert p.get_status() in (SolveStatus.OPTIMUM, SolveStatus.INTERRUPTED_SAT)
    model = p.get_model()
    cost = p.get_cost()
    assert model is not None
    assert isinstance(cost, int)
    p.close()


def test_portfolio_accepts_python_classes_and_handles_invalid_solver_result():
    wcnf = _load_small_wcnf("ram_k3_n9.ra1.wcnf")
    p = PortfolioSolver(
        [BadModelCostSolver, UWrMaxSAT],
        formula=wcnf,
        per_solver_timeout_s=5.0,
        overall_timeout_s=8.0,
        selection_policy="first_optimal_or_best_until_timeout",
        validate_model=True,
        recompute_cost_from_model=True,
        invalid_result_policy="warn_drop",
    )
    ok = p.solve()
    assert ok is True
    assert is_feasible(p.get_status())
    # The fake solver should be dropped, so the selected solver should not be the fake one.
    assert p._last_solver_name != "BadModelCostSolver"
    details = p.last_run_details
    assert any(d.get("solver") == "BadModelCostSolver" and d.get("status") == "INVALID" for d in details)
    p.close()


def test_portfolio_first_valid_policy_can_return_incomplete_result():
    wcnf = _load_small_wcnf("ram_k3_n9.ra1.wcnf")
    if not Loandra.is_available():
        pytest.skip("Loandra not available in this build")
    p = PortfolioSolver(
        [Loandra, UWrMaxSAT],
        formula=wcnf,
        per_solver_timeout_s=5.0,
        overall_timeout_s=8.0,
        selection_policy="first_valid",
    )
    ok = p.solve()
    assert ok is True
    assert is_feasible(p.get_status())
    assert p.get_model() is not None
    assert isinstance(p.get_cost(), int)
    p.close()


def test_portfolio_only_invalid_backends_reports_failure():
    wcnf = _load_small_wcnf("ram_k3_n9.ra1.wcnf")
    p = PortfolioSolver(
        [BadModelCostSolver],
        formula=wcnf,
        per_solver_timeout_s=3.0,
        overall_timeout_s=5.0,
        validate_model=True,
        recompute_cost_from_model=True,
        invalid_result_policy="warn_drop",
        verbose_invalid=False,
    )
    ok = p.solve()
    assert ok is False
    assert p.get_status() in (SolveStatus.ERROR, SolveStatus.INTERRUPTED)
    with pytest.raises(RuntimeError):
        _ = p.get_model()
    with pytest.raises(RuntimeError):
        _ = p.get_cost()
    details = p.last_run_details
    assert any(d.get("solver") == "BadModelCostSolver" and d.get("status") == "INVALID" for d in details)
    p.close()


def test_portfolio_invalid_policy_raise_raises():
    wcnf = _load_small_wcnf("ram_k3_n9.ra1.wcnf")
    p = PortfolioSolver(
        [BadModelCostSolver],
        formula=wcnf,
        per_solver_timeout_s=3.0,
        overall_timeout_s=5.0,
        validate_model=True,
        recompute_cost_from_model=True,
        invalid_result_policy="raise",
        verbose_invalid=False,
    )
    with pytest.raises(RuntimeError):
        p.solve()
    p.close()


def test_preset_discovery_is_deterministic_and_deduplicated():
    for preset in (CompletePortfolioSolver, IncompletePortfolioSolver, PerformancePortfolioSolver):
        classes = preset.discovered_solver_classes()
        assert classes, f"{preset.__name__} discovered no classes"
        keys = [_worker_solver_path_for_class(c) for c in classes]
        assert keys == sorted(keys)
        assert len(keys) == len(set(keys)), f"{preset.__name__} contains duplicate effective workers"


def test_performance_portfolio_max_workers_1_runs_on_real_data():
    wcnf = _load_small_wcnf("ram_k3_n9.ra1.wcnf")
    p = PerformancePortfolioSolver(
        formula=wcnf,
        per_solver_timeout_s=4.0,
        overall_timeout_s=10.0,
        max_workers=1,
        selection_policy="first_optimal_or_best_until_timeout",
        # Keep runtime reasonable in partial/minimal builds.
        exclude=[BadModelCostSolver],
    )
    ok = p.solve()
    assert ok is True
    assert is_feasible(p.get_status())
    assert p.get_model() is not None
    assert isinstance(p.get_cost(), int)
    p.close()
