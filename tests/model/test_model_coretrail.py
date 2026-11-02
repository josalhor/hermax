from __future__ import annotations

import pytest

from hermax.incremental import CoreTrail
from hermax.model import Model


def _require_coretrail() -> None:
    if not CoreTrail.is_available():
        pytest.skip("CoreTrail native module is not available in this build")


def test_model_routes_incremental_objective_updates_to_coretrail():
    _require_coretrail()
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= a | b
    m &= ~a | ~b
    m.obj += 10 * ~a
    m.obj += 5 * b

    first = m.solve(incremental=True, backend="maxsat", solver=CoreTrail)
    assert first.status == "optimum"
    assert first.cost == 0
    assert first[a] is True
    assert first[b] is False

    m &= ~a
    second = m.solve(incremental=True, backend="maxsat")
    assert second.status == "optimum"
    assert second.cost == 15
    assert second[a] is False
    assert second[b] is True


def test_model_exports_one_shot_wcnf_to_coretrail():
    _require_coretrail()
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= a
    m &= b
    penalty_satisfied = m.bool()
    m &= (~a | ~b).iff(penalty_satisfied)
    m.obj += 7 * ~penalty_satisfied

    result = m.solve(incremental=False, solver=CoreTrail)
    assert result.status == "optimum"
    assert result.cost == 7
    assert result[a] is True
    assert result[b] is True


def test_model_coretrail_deadline_can_resume_the_same_incremental_query():
    _require_coretrail()
    m = Model()
    x = m.bool("x")
    m &= x
    m.obj += ~x

    interrupted = m.solve(
        incremental=True,
        backend="maxsat",
        solver=CoreTrail,
        time_limit=1e-12,
    )
    assert interrupted.status in {"interrupted", "interrupted_sat"}

    resumed = m.solve(incremental=True, backend="maxsat")
    assert resumed.status == "optimum"
    assert resumed.cost == 0
    assert resumed[x] is True


def test_default_maxsat_backend_is_coretrail():
    from hermax.model.core import DefaultMaxSATSolver

    assert DefaultMaxSATSolver is CoreTrail


def test_coretrail_default_options_match_rc2_stratified(monkeypatch):
    from hermax.core import coretrail_native
    from hermax.core.coretrail_py import CoreTrailSolver

    captured = {}
    native = coretrail_native.CoreTrail

    def create(formula, **options):
        captured.update(options)
        return native(formula, **options)

    monkeypatch.setattr(coretrail_native, "CoreTrail", create)
    solver = CoreTrailSolver()
    try:
        solver.add_clause([1])
        solver.set_soft(-1, 3)
        assert solver.solve()
        assert solver.get_cost() == 3
    finally:
        solver.close()
    assert captured == dict(solver="g4", adapt=True, exhaust=True, minz=False,
                            blo="div", trim=0, full_stratified=True, nohard=True)


def test_default_maxsat_binding_is_incremental_coretrail():
    m = Model()
    x = m.bool()
    m.obj += x
    assert m.solve().cost == 0
    assert isinstance(m._inc_state.ip_solver, CoreTrail)
    m &= x
    assert m.solve().cost == 1
