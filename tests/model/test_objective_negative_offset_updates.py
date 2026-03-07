from __future__ import annotations

import pytest

from hermax.model import Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok
    return r


def test_obj_replace_negative_then_positive_expression_no_stale_state():
    m = Model()
    a = m.bool("a")

    # Minimize -a -> best is a=True with cost -1.
    m.obj = (-1 * a)
    r1 = _solve_ok(m)
    assert r1[a] is True
    assert r1.cost == -1

    # Replace objective completely: minimize +a -> best is a=False with cost 0.
    m.obj = a
    r2 = _solve_ok(m)
    assert r2[a] is False
    assert r2.cost == 0


def test_obj_replace_updates_negative_offset_value_correctly():
    m = Model()
    a = m.bool("a")

    m.obj = (-2 * a) + 7
    r1 = _solve_ok(m)
    # minimum at a=True: -2 + 7 = 5
    assert r1[a] is True
    assert r1.cost == 5

    m.obj = (-3 * a) + 4
    r2 = _solve_ok(m)
    # minimum at a=True: -3 + 4 = 1
    assert r2[a] is True
    assert r2.cost == 1


def test_obj_replace_with_same_symbol_different_scale_is_stable():
    m = Model()
    a = m.bool("a")

    m.obj = (-5 * a) + 2
    r1 = _solve_ok(m)
    assert r1[a] is True
    assert r1.cost == -3

    m.obj = (-1 * a) + 2
    r2 = _solve_ok(m)
    assert r2[a] is True
    assert r2.cost == 1


def test_obj_replace_with_mixed_sign_terms_and_replacement():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m.obj = (-2 * a) + (3 * b) + 1
    r1 = _solve_ok(m)
    # minimize: a=True, b=False => -2 + 0 + 1 = -1
    assert r1[a] is True
    assert r1[b] is False
    assert r1.cost == -1

    m.obj = (2 * a) + (-3 * b) + 1
    r2 = _solve_ok(m)
    # minimize: a=False, b=True => 0 - 3 + 1 = -2
    assert r2[a] is False
    assert r2[b] is True
    assert r2.cost == -2


def test_update_soft_weight_with_negative_offset_objective_keeps_consistent_cost():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Objective side uses negative offset machinery.
    m.obj = (-2 * a) + 3

    # Explicit soft with handle.
    ref = m.add_soft(b, weight=2)

    r1 = _solve_ok(m)
    # minimize (-2*a + 3) + penalty if b is false -> a=True, b=True => 1
    assert r1[a] is True and r1[b] is True
    assert r1.cost == 1

    # Increase explicit soft weight; optimum assignment should stay b=True.
    m.update_soft_weight(ref, 10)
    r2 = _solve_ok(m)
    assert r2[a] is True and r2[b] is True
    assert r2.cost == 1


def test_update_soft_weight_changes_optimum_with_negative_offset_objective():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Hard-force b=False so the explicit soft penalty is unavoidable.
    m &= ~b

    m.obj = (-1 * a) + 2
    ref = m.add_soft(b, weight=1)  # violated because b is forced false

    r1 = _solve_ok(m)
    assert r1[a] is True and r1[b] is False
    assert r1.cost == 2  # (-1+2) + 1

    m.update_soft_weight(ref, 7)
    r2 = _solve_ok(m)
    assert r2[a] is True and r2[b] is False
    assert r2.cost == 8  # (-1+2) + 7


def test_update_soft_weight_rejects_non_positive_even_with_negative_offset_objective():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj = (-1 * a) + 1
    ref = m.add_soft(b, weight=2)

    with pytest.raises(ValueError):
        m.update_soft_weight(ref, 0)
    with pytest.raises(ValueError):
        m.update_soft_weight(ref, -3)


def test_disallow_negative_offset_policy_blocks_negative_objective_replacement():
    m = Model()
    a = m.bool("a")
    m.set_objective_offset_policy(allow_negative=False)

    with pytest.raises(ValueError, match="Negative objective offsets are not supported"):
        m.obj = (-1 * a)


def test_disallow_negative_offset_policy_allows_non_negative_objective():
    m = Model()
    a = m.bool("a")
    m.set_objective_offset_policy(allow_negative=False)
    m.obj = a + 2
    r = _solve_ok(m)
    assert r[a] is False
    assert r.cost == 2

