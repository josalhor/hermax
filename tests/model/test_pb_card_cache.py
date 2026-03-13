from __future__ import annotations

import pytest

from hermax.model import Model
import hermax.model as model_mod
import hermax.internal.structuredpb as structuredpb_mod
from hermax.internal.structuredpb import StructuredPBEnc


def _count_calls(monkeypatch):
    calls = {
        "structured_auto_leq": 0,
        "card_atmost": 0,
        "card_atleast": 0,
        "card_equals": 0,
        "pb_leq": 0,
        "pb_geq": 0,
        "pb_equals": 0,
    }

    orig_auto_leq = StructuredPBEnc.auto_leq
    orig_atmost = model_mod.CardEnc.atmost
    orig_atleast = model_mod.CardEnc.atleast
    orig_ceq = model_mod.CardEnc.equals
    orig_leq = model_mod.PBEnc.leq
    orig_geq = model_mod.PBEnc.geq
    orig_peq = model_mod.PBEnc.equals

    def auto_leq(*args, **kwargs):
        calls["structured_auto_leq"] += 1
        return orig_auto_leq(*args, **kwargs)

    def atmost(*args, **kwargs):
        calls["card_atmost"] += 1
        return orig_atmost(*args, **kwargs)

    def atleast(*args, **kwargs):
        calls["card_atleast"] += 1
        return orig_atleast(*args, **kwargs)

    def ceq(*args, **kwargs):
        calls["card_equals"] += 1
        return orig_ceq(*args, **kwargs)

    def leq(*args, **kwargs):
        calls["pb_leq"] += 1
        return orig_leq(*args, **kwargs)

    def geq(*args, **kwargs):
        calls["pb_geq"] += 1
        return orig_geq(*args, **kwargs)

    def peq(*args, **kwargs):
        calls["pb_equals"] += 1
        return orig_peq(*args, **kwargs)

    monkeypatch.setattr(StructuredPBEnc, "auto_leq", staticmethod(auto_leq))
    monkeypatch.setattr(model_mod.CardEnc, "atmost", atmost)
    monkeypatch.setattr(model_mod.CardEnc, "atleast", atleast)
    monkeypatch.setattr(model_mod.CardEnc, "equals", ceq)
    monkeypatch.setattr(structuredpb_mod.CardEnc, "atmost", atmost)
    monkeypatch.setattr(structuredpb_mod.CardEnc, "atleast", atleast)
    monkeypatch.setattr(structuredpb_mod.CardEnc, "equals", ceq)
    monkeypatch.setattr(model_mod.PBEnc, "leq", leq)
    monkeypatch.setattr(model_mod.PBEnc, "geq", geq)
    monkeypatch.setattr(model_mod.PBEnc, "equals", peq)

    return calls


def test_card_cache_atmost_reused_for_equivalent_constraints(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a + b <= 1)
    m &= (a + b <= 1)
    m._commit_pb()
    assert calls["structured_auto_leq"] == 1
    assert calls["card_atmost"] == 1


def test_card_cache_equals_reused(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a + b == 1)
    m &= (a + b == 1)
    m._commit_pb()
    assert calls["structured_auto_leq"] == 2
    assert calls["card_atmost"] == 2
    assert calls["card_equals"] == 0


def test_card_cache_atleast_reused(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a + b >= 1)
    m &= (a + b >= 1)
    m._commit_pb()
    assert calls["structured_auto_leq"] == 1
    assert calls["card_atmost"] == 1
    assert calls["card_atleast"] == 0


def test_pb_cache_leq_reused(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (2 * a + 3 * b <= 3)
    m &= (2 * a + 3 * b <= 3)
    m._commit_pb()
    assert calls["pb_leq"] == 1


def test_pb_cache_geq_reused(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (2 * a + 3 * b >= 3)
    m &= (2 * a + 3 * b >= 3)
    m._commit_pb()
    assert calls["pb_geq"] == 1


def test_pb_cache_equals_reused(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (2 * a + 3 * b == 3)
    m &= (2 * a + 3 * b == 3)
    m._commit_pb()
    assert calls["pb_equals"] == 1


def test_cache_key_distinguishes_bound(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a + b <= 1)
    m &= (a + b <= 2)
    m._commit_pb()
    # second one is trivial true (sum<=2 with two unit vars), so no extra call
    assert calls["structured_auto_leq"] == 1
    assert calls["card_atmost"] == 1


def test_cache_key_distinguishes_op(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a + b <= 1)
    m &= (a + b >= 1)
    m._commit_pb()
    assert calls["structured_auto_leq"] == 2
    assert calls["card_atmost"] == 2
    assert calls["card_atleast"] == 0


def test_cache_key_normalizes_literal_order(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a + b <= 1)
    m &= (b + a <= 1)
    m._commit_pb()
    assert calls["structured_auto_leq"] == 1
    assert calls["card_atmost"] == 1


def test_cache_reused_when_model_grows_between_calls(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a + b <= 1)
    m.bool("z")
    m &= (a + b <= 1)
    m._commit_pb()
    assert calls["structured_auto_leq"] == 1
    assert calls["card_atmost"] == 1


def test_cache_applies_for_obj_add_pbconstraint(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj[3] += (2 * a + 3 * b <= 3)
    m.obj[4] += (2 * a + 3 * b <= 3)
    m._commit_pb()
    assert calls["pb_leq"] == 1


def test_cache_disabled_for_trivial_shortcircuit(monkeypatch):
    calls = _count_calls(monkeypatch)
    m = Model()
    a = m.bool("a")
    m &= (1 * a >= 0)
    m &= (1 * a >= 0)
    assert calls["card_atleast"] == 0
    assert calls["pb_geq"] == 0


def test_cache_entry_does_not_change_semantics_small_sat():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a + b <= 1)
    m &= (a + b <= 1)
    r = m.solve(incremental=False)
    assert r.ok
