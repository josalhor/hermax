from __future__ import annotations

import pytest

from hermax.model import ClauseGroup, Literal, MaxExpr, Model


def test_enum_self_equality_returns_tautological_clausegroup():
    m = Model()
    e = m.enum("e", ["red", "green", "blue"])
    g = (e == e)
    assert isinstance(g, ClauseGroup)
    assert len(g.clauses) == 0


def test_intvar_eq_ne_in_domain_return_supported_types():
    m = Model()
    idx = m.int("idx", 0, 5)
    for k in range(idx.lb, idx.ub):
        eq = (idx == k)
        ne = (idx != k)
        assert isinstance(eq, Literal)
        assert isinstance(ne, (Literal, ClauseGroup))


def test_vector_element_paths_rely_on_eq_literal_invariant():
    m = Model()
    vals = m.int_vector("v", length=3, lb=0, ub=10)
    idx = m.int("idx", 0, 3)
    rhs = m.int("rhs", 0, 10)
    m &= (vals[0] == 1)
    m &= (vals[1] == 4)
    m &= (vals[2] == 7)
    m &= (idx == 2)
    m &= (rhs == 7)
    # Hits _VectorElementInt gating and _Multiplexer-style index equality assumptions.
    m &= (vals[idx] == rhs)
    m &= (vals[idx] >= rhs)
    m &= (vals[idx] <= rhs)
    r = m.solve()
    assert r.ok
    assert r[idx] == 2
    assert r[rhs] == 7


def test_internal_aggregate_helpers_reject_unknown_kind_by_assertion():
    m = Model()
    xs = [m.int("x0", 0, 3), m.int("x1", 1, 4)]
    with pytest.raises(AssertionError, match="Unknown extreme kind"):
        m._build_int_aggregate_extreme(xs, "median")  # private invariant test
    with pytest.raises(AssertionError, match="Unknown one-sided bound kind"):
        m._build_int_aggregate_bound(xs, "mid_bound")  # private invariant test


def test_maxexpr_rejects_unknown_kind_by_assertion():
    m = Model()
    xs = [m.int("x0", 0, 3), m.int("x1", 1, 4)]
    with pytest.raises(AssertionError, match="Unknown aggregate kind"):
        MaxExpr(m, xs, "median")
