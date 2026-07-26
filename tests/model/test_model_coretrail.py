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
    m.obj[10] += a
    m.obj[5] += ~b

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
    m.obj[7] += ~a | ~b

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
    m.obj[1] += x

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
