from __future__ import annotations

import pytest

from hermax.model import Model
from tests.model.test_soft_behavior import FakeIPSoft


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok
    return r


def test_float_weight_is_stored_without_precision_until_solver_selection_add_soft():
    m = Model()
    a = m.bool("a")
    with pytest.warns(FutureWarning, match=r"add_soft\(\) is deprecated"):
        m.obj.add_soft(a, 1.25)  # type: ignore[arg-type]
    assert m._soft[0][0] == 1.25


def test_default_coretrail_preserves_native_float_cost_without_precision():
    m = Model()
    a = m.bool("a")
    m &= a
    m.obj.add(a, weight=0.34545384753412)
    result = m.solve()
    assert result.ok
    assert result.cost == pytest.approx(0.34545384753412)
    assert result[a] is True


def test_float_objective_rejected_by_integer_only_solver_without_precision():
    from hermax.core.openwbo_py import OLLSolver

    m = Model()
    a = m.bool("a")
    m.obj.add(~a, weight=0.375)
    with pytest.raises(ValueError, match="does not support native floating-point weights"):
        m.solve(incremental=False, solver=OLLSolver)


def test_float_weight_stored_without_precision_obj_bucket():
    m = Model()
    a = m.bool("a")
    m.obj += 1.25 * a  # type: ignore[index]
    assert 1.25 in [w for w, _ in m._soft]


def test_integral_float_weight_stored_without_precision():
    m = Model()
    a = m.bool("a")
    m.obj.add(~a, weight=1.0)  # type: ignore[arg-type]
    assert 1.0 in [w for w, _ in m._soft]


def test_precision_allows_float_weights_and_rounds():
    m = Model()
    m.set_objective_precision(decimals=2)
    a = m.bool("a")
    b = m.bool("b")
    m.obj.add(~a, weight=1.25)
    m.obj.add(b, weight=3.50)
    # Stored in scaled integer units.
    assert sorted(w for w, _ in m._soft) == [125, 350]


def test_precision_applies_to_update_soft_weight():
    m = Model()
    m.set_objective_precision(decimals=2)
    a = m.bool("a")
    with pytest.warns(FutureWarning, match=r"add_soft\(\) is deprecated"):
        ref = m.obj.add_soft(a, 1.25)
    with pytest.warns(FutureWarning, match=r"update_soft\(\) is deprecated"):
        m.obj.update_soft(ref, 2.34)
    assert m._soft[0][0] == 234


def test_precision_change_rerounds_from_original_weights():
    m = Model()
    m.set_objective_precision(decimals=2)
    a = m.bool("a")
    with pytest.warns(FutureWarning, match=r"add_soft\(\) is deprecated"):
        m.obj.add_soft(a, 1.25)   # 125
    assert m._soft[0][0] == 125
    m.set_objective_precision(decimals=1)  # re-round 1.25 -> 1.2
    assert m._soft[0][0] == 12
    m.set_objective_precision(decimals=3)  # re-round 1.25 -> 1.250
    assert m._soft[0][0] == 1250


def test_precision_one_shot_solver_cost_is_descaled_float_real_solver():
    m = Model()
    m.set_objective_precision(decimals=2)
    a = m.bool("a")
    b = m.bool("b")
    # Force both softs to be violated.
    m &= ~a
    m &= b
    m.obj.add(~a, weight=1.25)
    m.obj.add(b, weight=3.50)
    # One-shot solve path uses real Hermax RC2-based backend.
    r = m.solve(incremental=False)
    assert isinstance(r.cost, float)
    assert r.cost == pytest.approx(4.75, abs=1e-9)


def test_precision_works_with_incremental_ipamir_updates():
    m = Model()
    m.set_objective_precision(decimals=2)
    a = m.bool("a")
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    with pytest.warns(FutureWarning, match=r"add_soft\(\) is deprecated"):
        ref = m.obj.add_soft(a, 1.25)
    assert s.soft_updates[-1][1] == 125
    m.obj.update(ref, weight=3.50)
    assert s.soft_updates[-1][1] == 350


def test_float_term_builds_but_pb_compare_fails_on_compile():
    m = Model()
    b = m.bool("b")
    x = m.int("x", 0, 5)
    pb = (3.5 * b + x <= 2)
    # Construction should succeed; compile should fail.
    with pytest.raises(ValueError, match="integer coefficients"):
        m &= pb


def test_float_objective_expr_requires_precision_to_lower():
    m = Model()
    b = m.bool("b")
    with pytest.raises(ValueError):
        m.obj = (3.5 * b)

    m2 = Model()
    m2.set_objective_precision(decimals=2)
    b2 = m2.bool("b")
    m2.obj = (3.5 * b2)
    r = _solve_ok(m2)
    assert r[b2] is False
    assert r.cost == pytest.approx(0.0, abs=1e-9)


def test_objective_expression_precision_scaling_soundness():
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= x
    m.obj += 1.25 * x
    res = m.solve()
    assert res.ok
    assert res[x] is True
    assert res.cost == pytest.approx(1.25, abs=1e-9)

