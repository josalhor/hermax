from __future__ import annotations

import pytest

from hermax.model import Model, PBExpr


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok
    return r


def test_obj_iadd_accepts_pbexpr_directly():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj += (3 * a + 2 * b)
    r = _solve_ok(m)
    # Minimization prefers both false.
    assert r[a] is False
    assert r[b] is False
    assert r.cost == 0


def test_obj_iadd_supports_negated_literal_terms():
    m = Model()
    x = m.bool("x")
    m.obj += 3 * ~x
    r = _solve_ok(m)
    # Minimizing 3*~x prefers x=True.
    assert r[x] is True
    assert r.cost == 0


def test_obj_iadd_accepts_sum_of_weighted_literals():
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(4)]
    expr = sum((i + 1) * x for i, x in enumerate(xs))
    m.obj += expr
    r = _solve_ok(m)
    assert all(r[x] is False for x in xs)
    assert r.cost == 0


def test_obj_iadd_rejects_ambiguous_scaled_pbconstraint():
    m = Model()
    x = m.int("x", 0, 6)
    y = m.int("y", 0, 6)
    with pytest.raises(TypeError):
        m.obj += 3 * (x == y * 2)


def test_obj_iadd_and_bucket_semantics_are_additive():
    m = Model()
    a = m.bool("a")
    m.obj += (2 * a)
    m.obj[3] += a
    r = _solve_ok(m)
    assert r[a] is True
    assert r.cost == 2


def test_boolvector_mul_weights_returns_pbexpr():
    m = Model()
    bv = m.bool_vector("x", length=3)
    expr = bv * [1, 2, 3]
    assert isinstance(expr, PBExpr)


def test_boolvector_rmul_weights_returns_pbexpr():
    m = Model()
    bv = m.bool_vector("x", length=3)
    expr = [1, 2, 3] * bv
    assert isinstance(expr, PBExpr)


def test_obj_iadd_with_boolvector_weighted_sum_end_to_end():
    m = Model()
    bv = m.bool_vector("x", length=4)
    m.obj += (bv * [5, 1, 3, 2])
    r = _solve_ok(m)
    assert r.cost == 0
    assert all(v is False for v in r[bv])


def test_obj_iadd_with_sum_of_vector_weighted_terms_end_to_end():
    m = Model()
    bv = m.bool_vector("x", length=4)
    ws = [4, 2, 1, 7]
    m.obj += sum(w * lit for w, lit in zip(ws, bv))
    r = _solve_ok(m)
    assert r.cost == 0
    assert all(v is False for v in r[bv])


def test_boolvector_weighted_sum_with_hard_constraints_changes_solution():
    m = Model()
    bv = m.bool_vector("x", length=3)
    # Must pick at least one true.
    m &= bv.at_least_one()
    m.obj += (bv * [8, 1, 5])
    r = _solve_ok(m)
    vals = r[bv]
    assert sum(1 for v in vals if v) >= 1
    # cheapest bit should be selected in optimum
    assert vals[1] is True
    assert r.cost == 1


def test_boolvector_mul_requires_same_length_weights():
    m = Model()
    bv = m.bool_vector("x", length=3)
    with pytest.raises(ValueError):
        _ = bv * [1, 2]


def test_boolvector_mul_rejects_noninteger_weights():
    m = Model()
    bv = m.bool_vector("x", length=2)
    with pytest.raises(TypeError):
        _ = bv * [1, 1.5]


def test_boolvector_mul_rejects_bool_weights():
    m = Model()
    bv = m.bool_vector("x", length=2)
    with pytest.raises(TypeError):
        _ = bv * [True, 1]


def test_obj_iadd_supports_negative_coefficients_via_pbexpr():
    m = Model()
    a = m.bool("a")
    # Minimize -a => maximize a, best with a=True and cost -1.
    m.obj += (-1 * a)
    r = _solve_ok(m)
    assert r[a] is True
    assert r.cost == -1
