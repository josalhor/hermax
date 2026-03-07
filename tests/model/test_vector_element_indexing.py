from __future__ import annotations

import pytest

import hermax.model as hm
from hermax.model import ClauseGroup, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_intvector_variable_index_equality_with_intvar_rhs():
    m = Model()
    vals = m.int_vector("v", length=3, lb=0, ub=10)
    idx = m.int("idx", 0, 3)
    a = m.int("a", 0, 10)

    m &= (vals[0] == 2)
    m &= (vals[1] == 5)
    m &= (vals[2] == 7)
    m &= (idx == 1)
    m &= (vals[idx] == a)

    r = _solve_ok(m)
    assert r[idx] == 1
    assert r[a] == 5


def test_intvector_variable_index_equality_unsat_on_wrong_fixed_target():
    m = Model()
    vals = m.int_vector("v", length=3, lb=0, ub=10)
    idx = m.int("idx", 0, 3)
    a = m.int("a", 0, 10)

    m &= (vals[0] == 2)
    m &= (vals[1] == 5)
    m &= (vals[2] == 7)
    m &= (idx == 2)
    m &= (vals[idx] == a)
    m &= (a == 5)  # should be 7

    r = m.solve()
    assert r.status == "unsat"


def test_intvector_variable_index_with_int_rhs_and_relops():
    m = Model()
    vals = m.int_vector("v", length=3, lb=0, ub=20)
    idx = m.int("idx", 0, 3)

    m &= (vals[0] == 2)
    m &= (vals[1] == 6)
    m &= (vals[2] == 9)
    m &= (idx == 1)
    m &= (vals[idx] <= 6)
    m &= (vals[idx] < 7)
    m &= (vals[idx] >= 6)
    m &= (vals[idx] > 5)

    r = _solve_ok(m)
    assert r[idx] == 1


def test_intvector_variable_index_returns_clausegroup_and_bypasses_pb_card(monkeypatch):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for V[idx] == a")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for V[idx] == a")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    vals = m.int_vector("v", length=3, lb=0, ub=10)
    idx = m.int("idx", 0, 3)
    a = m.int("a", 0, 10)

    cg = (vals[idx] == a)
    assert isinstance(cg, ClauseGroup)
    m &= cg
    m &= (idx == 0)
    m &= (vals[0] == 4)
    m &= (a == 4)
    r = _solve_ok(m)
    assert r[a] == 4


def test_intvector_variable_index_rejects_out_of_coverage_or_negative_lb():
    m = Model()
    vals = m.int_vector("v", length=2, lb=0, ub=5)
    idx_bad_span = m.int("idx_bad_span", 0, 3)
    with pytest.raises(ValueError, match="does not cover"):
        _ = vals[idx_bad_span]

    m2 = Model()
    vals2 = m2.int_vector("v", length=3, lb=0, ub=5)
    idx_neg = m2.int("idx_neg", -1, 2)
    with pytest.raises(ValueError, match="lb >= 0"):
        _ = vals2[idx_neg]

