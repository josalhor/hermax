import types

import pytest

import hermax.model as hm
from hermax.model import Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable model, got status={r.status}"
    return r


def _patch_card_methods(monkeypatch, calls):
    real_atmost = hm.CardEnc.atmost
    real_atleast = hm.CardEnc.atleast
    real_equals = hm.CardEnc.equals

    def atmost(*args, **kwargs):
        lits = kwargs.get("lits", args[0] if len(args) > 0 else None)
        bound = kwargs.get("bound", args[1] if len(args) > 1 else None)
        top_id = kwargs.get("top_id", args[2] if len(args) > 2 else None)
        calls.append(("card.atmost", list(lits), int(bound), int(top_id)))
        return real_atmost(*args, **kwargs)

    def atleast(*args, **kwargs):
        lits = kwargs.get("lits", args[0] if len(args) > 0 else None)
        bound = kwargs.get("bound", args[1] if len(args) > 1 else None)
        top_id = kwargs.get("top_id", args[2] if len(args) > 2 else None)
        calls.append(("card.atleast", list(lits), int(bound), int(top_id)))
        return real_atleast(*args, **kwargs)

    def equals(*args, **kwargs):
        lits = kwargs.get("lits", args[0] if len(args) > 0 else None)
        bound = kwargs.get("bound", args[1] if len(args) > 1 else None)
        top_id = kwargs.get("top_id", args[2] if len(args) > 2 else None)
        calls.append(("card.equals", list(lits), int(bound), int(top_id)))
        return real_equals(*args, **kwargs)

    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(atmost))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(atleast))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(equals))


def _patch_pb_methods(monkeypatch, calls):
    real_leq = hm.PBEnc.leq
    real_geq = hm.PBEnc.geq
    real_equals = hm.PBEnc.equals

    def leq(*args, **kwargs):
        lits = kwargs.get("lits", args[0] if len(args) > 0 else None)
        weights = kwargs.get("weights", args[1] if len(args) > 1 else None)
        bound = kwargs.get("bound", args[2] if len(args) > 2 else None)
        top_id = kwargs.get("top_id", args[3] if len(args) > 3 else None)
        calls.append(("pb.leq", list(lits), list(weights), int(bound), int(top_id)))
        return real_leq(*args, **kwargs)

    def geq(*args, **kwargs):
        lits = kwargs.get("lits", args[0] if len(args) > 0 else None)
        weights = kwargs.get("weights", args[1] if len(args) > 1 else None)
        bound = kwargs.get("bound", args[2] if len(args) > 2 else None)
        top_id = kwargs.get("top_id", args[3] if len(args) > 3 else None)
        calls.append(("pb.geq", list(lits), list(weights), int(bound), int(top_id)))
        return real_geq(*args, **kwargs)

    def equals(*args, **kwargs):
        lits = kwargs.get("lits", args[0] if len(args) > 0 else None)
        weights = kwargs.get("weights", args[1] if len(args) > 1 else None)
        bound = kwargs.get("bound", args[2] if len(args) > 2 else None)
        top_id = kwargs.get("top_id", args[3] if len(args) > 3 else None)
        calls.append(("pb.equals", list(lits), list(weights), int(bound), int(top_id)))
        return real_equals(*args, **kwargs)

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(leq))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(geq))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(equals))


def test_unit_coefficients_use_cardinality_atmost(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (a + b <= 1)
    r = _solve_ok(m)

    assert r[a] is True
    assert r[b] is False
    assert [c[0] for c in calls] == ["card.atmost"]
    kind, lits, bound, _top = calls[0]
    assert kind == "card.atmost"
    assert sorted(abs(x) for x in lits) == sorted([a.id, b.id])
    assert bound == 1


def test_weighted_coefficients_use_pb_leq(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (2 * a + 3 * b <= 2)
    r = _solve_ok(m)

    assert r[a] is True
    assert r[b] is False
    assert [c[0] for c in calls] == ["pb.leq"]
    kind, lits, weights, bound, _top = calls[0]
    assert kind == "pb.leq"
    assert sorted(weights) == [2, 3]
    assert sorted(abs(x) for x in lits) == sorted([a.id, b.id])
    assert bound == 2


def test_unit_coefficients_use_cardinality_equals(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (a + b == 1)
    r = _solve_ok(m)

    assert r[a] is True
    assert r[b] is False
    kinds = [c[0] for c in calls]
    assert kinds[0] == "card.equals"
    assert "card.atleast" in kinds
    assert "card.atmost" in kinds
    assert all(not k.startswith("pb.") for k in kinds)
    assert calls[0][2] == 1


def test_weighted_coefficients_use_pb_equals(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (2 * a + 3 * b == 2)
    r = _solve_ok(m)

    assert r[a] is True
    assert r[b] is False
    assert [c[0] for c in calls] == ["pb.equals"]
    assert calls[0][3] == 2  # bound


def test_strict_operators_map_to_adjusted_cardinality_bounds(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    d = m.bool("d")

    # < 2  => atmost bound 1
    m &= (a + b < 2)
    # > 1  => atleast bound 2
    m &= (c + d > 1)
    r = _solve_ok(m)

    assert r[c] is True and r[d] is True
    kinds = [c0 for c0, *_ in calls]
    assert kinds == ["card.atmost", "card.atleast"]
    assert calls[0][2] == 1
    assert calls[1][2] == 2


def test_negative_coefficients_normalize_by_flipping_literal_and_shifting_bound(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # a - b <= 0  is equivalent to a <= b.
    m &= a
    m &= (a - b <= 0)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True

    assert [c[0] for c in calls] == ["card.atmost"]
    _kind, lits, bound, _top = calls[0]
    # Normalization should produce unit-cardinality over [a, ~b] with bound 1.
    assert bound == 1
    assert a.id in [abs(x) for x in lits]
    assert b.id in [abs(x) for x in lits]
    assert any(x < 0 and abs(x) == b.id for x in lits)


def test_expr_vs_expr_with_unit_coeffs_still_uses_cardinality_dispatch(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # a + b <= c + a  => b <= c
    m &= b
    m &= (a + b <= c + a)
    r = _solve_ok(m)
    assert r[b] is True
    assert r[c] is True
    assert [c0 for c0, *_ in calls] == ["card.atmost"]


def test_expr_vs_expr_with_nonunit_coeffs_uses_pb_dispatch(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # 2a + 3b >= a + 2c  => a + 3b >= 2c ; with c=true and a=false forces b=true.
    m &= ~a
    m &= c
    m &= (2 * a + 3 * b >= a + 2 * c)
    r = _solve_ok(m)
    assert r[a] is False
    assert r[c] is True
    assert r[b] is True
    assert [c0 for c0, *_ in calls] == ["pb.geq"]


def test_gcd_reduction_unlocks_cardinality_for_uniform_weighted_leq(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # 2a + 2b <= 3  <=> a + b <= 1  (cardinality after gcd reduction)
    m &= (2 * a + 2 * b <= 3)
    _solve_ok(m)

    kinds = [c0 for c0, *_ in calls]
    assert kinds == ["card.atmost"]
    _kind, _lits, bound, _top = calls[0]
    assert bound == 1


def test_gcd_reduction_uses_ceil_for_geq_bounds(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # 2a + 2b >= 3  <=> a + b >= 2 (ceil(3/2) = 2)
    m &= (2 * a + 2 * b >= 3)
    r = _solve_ok(m)
    assert r[a] is True and r[b] is True

    kinds = [c0 for c0, *_ in calls]
    assert kinds == ["card.atleast"]
    _kind, _lits, bound, _top = calls[0]
    assert bound == 2


def test_gcd_reduction_equality_nondivisible_bound_becomes_contradiction(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (2 * a + 2 * b == 3)
    r = m.solve()
    assert r.status == "unsat"
    # No encoder call should be needed for this contradiction.
    assert calls == []


def test_gcd_reduction_applies_before_cardinality_fastpath_on_expr_vs_expr(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    d = m.bool("d")

    # 2a + 2b <= 2c + 2d  => a + b <= c + d (unit after gcd)
    m &= a
    m &= b
    m &= ~c
    m &= ~d
    m &= (2 * a + 2 * b <= 2 * c + 2 * d)
    r = m.solve()
    assert r.status == "unsat"
    # Depending on earlier fastpaths this may compile without encoders, but it
    # must not fall through to weighted PB after gcd normalization.
    assert all(not k.startswith("pb.") for k, *_ in calls)


def test_encoder_generated_aux_ids_are_imported_into_model_registry(monkeypatch):
    calls = []

    class _FakeCNF:
        def __init__(self, clauses):
            self.clauses = clauses

    def fake_atmost(*, lits, bound, top_id, **kwargs):
        calls.append(("card.atmost", list(lits), int(bound), int(top_id)))
        # Force introduction of a fresh auxiliary var id (top_id + 1).
        return _FakeCNF([[top_id + 1]])

    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fake_atmost))

    # PB path should not be touched.
    def fail_pb(*args, **kwargs):  # pragma: no cover - sanity guard
        raise AssertionError("PB encoder should not be called in unit-coeff test")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    top_before = max(a.id, b.id)

    m &= (a + b <= 1)
    x = m.bool("x")

    # The fake encoder introduced top_before+1 as aux. User var should come after.
    assert x.id >= top_before + 2
    assert calls and calls[0][0] == "card.atmost"

    # The fake clause [aux] should make the instance satisfiable.
    _solve_ok(m)
