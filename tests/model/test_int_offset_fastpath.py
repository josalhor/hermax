from __future__ import annotations

import pytest

import hermax.model as hm
from hermax.model import Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok
    return r


def _solve_unsat(m: Model):
    r = m.solve()
    assert r.status == "unsat"
    return r


def test_offset_precedence_semantics_sat_and_unsat():
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)

    m &= (x + 5 <= y)
    m &= (x == 4)
    m &= (y == 9)
    r = _solve_ok(m)
    assert r[x] == 4
    assert r[y] == 9

    m2 = Model()
    x2 = m2.int("x", 0, 10)
    y2 = m2.int("y", 0, 10)
    m2 &= (x2 + 5 <= y2)
    m2 &= (x2 == 4)
    m2 &= (y2 == 8)
    _solve_unsat(m2)


def test_offset_precedence_right_offset_form_is_supported():
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    # Use PB syntax explicitly; plain `x <= y + 2` currently dispatches to
    # IntVar.__le__ (integer RHS-only) before PBExpr comparator handling.
    m &= (x + 0 <= y + 2)
    m &= (x == 7)
    m &= (y == 5)
    _solve_ok(m)

    m2 = Model()
    x2 = m2.int("x", 0, 10)
    y2 = m2.int("y", 0, 10)
    m2 &= (x2 + 0 <= y2 + 2)
    m2 &= (x2 == 8)
    m2 &= (y2 == 5)
    _solve_unsat(m2)


def test_offset_precedence_negative_offset_form_is_supported():
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    m &= (x - 3 <= y)
    m &= (x == 7)
    m &= (y == 4)
    _solve_ok(m)

    m2 = Model()
    x2 = m2.int("x", 0, 10)
    y2 = m2.int("y", 0, 10)
    m2 &= (x2 - 3 <= y2)
    m2 &= (x2 == 7)
    m2 &= (y2 == 3)
    _solve_unsat(m2)


def test_offset_equality_fast_path_semantics():
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 20)
    m &= (x + 5 == y)
    m &= (x == 3)
    m &= (y == 8)
    _solve_ok(m)

    m2 = Model()
    x2 = m2.int("x", 0, 10)
    y2 = m2.int("y", 0, 20)
    m2 &= (x2 + 5 == y2)
    m2 &= (x2 == 3)
    m2 &= (y2 == 7)
    _solve_unsat(m2)


def test_offset_fast_path_bypasses_card_and_pb_encoders(monkeypatch):
    calls: list[str] = []

    def fail_card(*args, **kwargs):
        calls.append("card")
        raise AssertionError("CardEnc should not be called for IntVar+offset<=IntVar fast path")

    def fail_pb(*args, **kwargs):
        calls.append("pb")
        raise AssertionError("PBEnc should not be called for IntVar+offset<=IntVar fast path")

    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))
    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))

    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    m &= (x + 4 <= y)
    m &= (x == 2)
    m &= (y == 6)
    _solve_ok(m)
    assert calls == []


def test_non_offset_general_pb_still_uses_pb_encoder(monkeypatch):
    seen = {"pb": 0}
    real_pb_leq = hm.PBEnc.leq

    def wrapped_pb_leq(*args, **kwargs):
        seen["pb"] += 1
        return real_pb_leq(*args, **kwargs)

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(wrapped_pb_leq))

    m = Model()
    x = m.int("x", 0, 8)
    y = m.int("y", 0, 8)
    # Three IntVars force the generic PB path (bivariate fast path does not apply).
    z = m.int("z", 0, 8)
    m &= (2 * x + 3 * y + z <= 20)
    m &= (x == 1)
    m &= (y == 4)
    m &= (z == 2)
    _solve_ok(m)
    assert seen["pb"] >= 1


def test_scaled_fastpath_does_not_allocate_scaled_proxy_intvar():
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 40)
    top_before = m._top_id()
    hard_before = len(m._hard)

    m &= (3 * x <= y)

    assert len(m._hard) > hard_before
    assert m._top_id() == top_before
