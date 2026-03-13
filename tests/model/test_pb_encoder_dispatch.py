import types

import pytest

import hermax.model as hm
import hermax.internal.structuredpb as structuredpb_mod
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


def _patch_structured_auto(monkeypatch, calls):
    real_auto_leq = structuredpb_mod.StructuredPBEnc.auto_leq

    def wrapped_auto_leq(*args, **kwargs):
        calls.append(
            (
                "structured.auto_leq",
                list(kwargs["lits"]),
                list(kwargs["weights"]),
                int(kwargs["bound"]),
                [list(group) for group in kwargs.get("amo_groups", [])],
                [list(group) for group in kwargs.get("eo_groups", [])],
            )
        )
        return real_auto_leq(*args, **kwargs)

    monkeypatch.setattr(
        structuredpb_mod.StructuredPBEnc,
        "auto_leq",
        classmethod(lambda cls, *a, **kw: wrapped_auto_leq(*a, **kw)),
    )


def test_unit_coefficients_use_cardinality_atmost(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (a + b <= 1)
    r = _solve_ok(m)

    assert r[a] is True
    assert r[b] is False
    assert [c[0] for c in calls] == ["structured.auto_leq", "card.atmost"]
    kind, lits, weights, bound, _amo_groups, _eo_groups = calls[0]
    assert kind == "structured.auto_leq"
    assert sorted(abs(x) for x in lits) == sorted([a.id, b.id])
    assert weights == [1, 1]
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
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (a + b == 1)
    r = _solve_ok(m)

    assert r[a] is True
    assert r[b] is False
    kinds = [c[0] for c in calls]
    assert kinds == ["card.equals", "card.atleast", "card.atmost"]
    assert calls[0][1] == [a.id, b.id]
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
    _patch_structured_auto(monkeypatch, calls)

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
    assert kinds == ["structured.auto_leq", "card.atmost", "card.atleast"]
    assert calls[0][3] == 1
    assert calls[2][2] == 2


def test_negative_coefficients_normalize_by_flipping_literal_and_shifting_bound(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

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
    _patch_structured_auto(monkeypatch, calls)

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
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # 2a + 2b <= 3  <=> a + b <= 1  (cardinality after gcd reduction)
    m &= (2 * a + 2 * b <= 3)
    _solve_ok(m)

    kinds = [c0 for c0, *_ in calls]
    assert kinds == ["structured.auto_leq", "card.atmost"]
    _kind, _lits, _weights, bound, _amo_groups, _eo_groups = calls[0]
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
            self.nv = max((abs(x) for cl in clauses for x in cl), default=0)

    def fake_auto_leq(*args, **kwargs):
        calls.append(("structured.auto_leq", list(kwargs["lits"]), list(kwargs["weights"]), int(kwargs["bound"])))
        # Force introduction of a fresh auxiliary var id (top_id + 1).
        top_id = int(kwargs["top_id"])
        return _FakeCNF([[top_id + 1]])

    monkeypatch.setattr(
        structuredpb_mod.StructuredPBEnc,
        "auto_leq",
        classmethod(lambda cls, *a, **kw: fake_auto_leq(*a, **kw)),
    )

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

    # PB/Card compilation is deferred until commit/solve, so user allocation
    # happens before encoder auxiliaries are introduced.
    assert x.id == top_before + 1
    assert calls == []

    # The fake clause [aux] should make the instance satisfiable.
    _solve_ok(m)
    assert calls and calls[0][0] == "structured.auto_leq"


def test_pb_is_deferred_until_commit(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= (2 * a + 3 * b <= 3)
    assert calls == []

    m._commit_pb()
    assert [c[0] for c in calls] == ["pb.leq"]


def test_commit_pb_is_idempotent(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= (a + b <= 1)
    m._commit_pb()
    m._commit_pb()

    assert [c[0] for c in calls] == ["structured.auto_leq", "card.atmost"]


def test_soft_pb_is_deferred_until_commit(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    ref = m.add_soft(2 * a + 3 * b <= 3, weight=5)

    assert len(ref.soft_ids) == 1
    assert len(m._soft) == 1
    assert calls == []

    m._commit_pb()

    assert [c[0] for c in calls] == ["pb.leq"]


def test_auto_pb_commit_triggers_immediate_hard_compile(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    m.set_auto_pb_commit(True)
    a = m.bool("a")
    b = m.bool("b")

    m &= (a + b <= 1)

    assert [c[0] for c in calls] == ["structured.auto_leq", "card.atmost"]


def test_auto_pb_commit_triggers_immediate_soft_compile(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    m = Model()
    m.set_auto_pb_commit(True)
    a = m.bool("a")
    b = m.bool("b")

    m.add_soft(2 * a + 3 * b <= 3, weight=5)

    assert [c[0] for c in calls] == ["pb.leq"]


def test_commit_pb_prioritizes_cardinality_before_structured_pb(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    d = m.bool("d")

    m &= (a + b <= 1)         # AMO candidate
    m &= (b + c == 1)         # EO candidate
    m &= (2 * a + 3 * b + 5 * d <= 6)  # weighted PB should see both groups

    assert calls == []
    m._commit_pb()

    kinds = [c0 for c0, *_ in calls]
    assert kinds[:3] == ["structured.auto_leq", "card.atmost", "card.equals"]
    weighted_call = next(entry for entry in calls if entry[0] == "structured.auto_leq" and any(w != 1 for w in entry[2]))
    _kind, lits, weights, bound, amo_groups, eo_groups = weighted_call
    assert sorted(abs(x) for x in lits) == sorted([a.id, b.id, d.id])
    assert sorted(weights) == [2, 3, 5]
    assert bound == 6
    assert amo_groups == [[a.id, b.id]]
    assert eo_groups == []


def test_commit_pb_routes_zero_amo_branch_to_plain_pblib(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)

    def bomb_auto_leq(*args, **kwargs):  # pragma: no cover - sanity guard
        raise AssertionError("StructuredPB auto router should not be used for zero-AMO branch")

    monkeypatch.setattr(structuredpb_mod.StructuredPBEnc, "auto_leq", classmethod(lambda cls, *a, **kw: bomb_auto_leq(*a, **kw)))

    m = Model()
    lits = [m.bool(f"x{i}") for i in range(5)]

    m &= (2 * lits[0] + 3 * lits[1] + 4 * lits[2] + 5 * lits[3] + 6 * lits[4] <= 7)
    m._commit_pb()

    assert [c0 for c0, *_ in calls] == ["pb.leq"]


def test_commit_pb_uses_structured_auto_for_nontrivial_amo_branch(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    lits = [m.bool(f"x{i}") for i in range(12)]

    # Create overlap candidates, but not enough to trivially reconstruct a single partition.
    m &= (lits[0] + lits[1] + lits[2] <= 1)
    m &= (lits[1] + lits[2] + lits[3] <= 1)
    m &= (lits[4] + lits[5] == 1)
    m &= (lits[6] + lits[7] + lits[8] <= 1)
    m &= (lits[7] + lits[8] + lits[9] <= 1)
    m &= (
        5 * lits[0]
        + 7 * lits[1]
        + 4 * lits[2]
        + 8 * lits[3]
        + 3 * lits[4]
        + 9 * lits[5]
        + 6 * lits[6]
        + 10 * lits[7]
        + 7 * lits[8]
        + 11 * lits[9]
        + 8 * lits[10]
        + 12 * lits[11]
        <= 35
    )

    m._commit_pb()

    kinds = [c0 for c0, *_ in calls]
    assert "structured.auto_leq" in kinds
    assert not any(k == "pb.leq" for k in kinds)
    structured_call = next(entry for entry in calls if entry[0] == "structured.auto_leq" and any(w != 1 for w in entry[2]))
    _kind, _lits, _weights, _bound, amo_groups, eo_groups = structured_call
    assert amo_groups == [
        [lits[0].id, lits[1].id, lits[2].id],
        [lits[1].id, lits[2].id, lits[3].id],
        [lits[6].id, lits[7].id, lits[8].id],
        [lits[7].id, lits[8].id, lits[9].id],
    ]
    assert eo_groups == [[lits[4].id, lits[5].id]]


def test_commit_pb_prioritizes_cardinality_harvesting_even_if_pb_was_added_first(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    d = m.bool("d")
    e = m.bool("e")
    f = m.bool("f")
    g = m.bool("g")
    h = m.bool("h")
    i = m.bool("i")
    j = m.bool("j")
    k = m.bool("k")
    l = m.bool("l")

    m &= (5 * a + 7 * b + 4 * c + 8 * d + 3 * e + 9 * f + 6 * g + 10 * h + 7 * i + 11 * j + 8 * k + 12 * l <= 35)
    m &= (a + b + c <= 1)
    m &= (b + c + d <= 1)
    m &= (e + f == 1)
    m &= (g + h + i <= 1)
    m &= (h + i + j <= 1)

    m._commit_pb()

    structured = next(entry for entry in calls if entry[0] == "structured.auto_leq" and any(w != 1 for w in entry[2]))
    _kind, _lits, _weights, _bound, amo_groups, eo_groups = structured
    assert amo_groups == [
        [a.id, b.id, c.id],
        [b.id, c.id, d.id],
        [g.id, h.id, i.id],
        [h.id, i.id, j.id],
    ]
    assert eo_groups == [[e.id, f.id]]


def test_commit_pb_demotes_partial_eo_overlap_to_amo(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    lits = [m.bool(f"x{i}") for i in range(12)]
    m &= (lits[0] + lits[1] + lits[2] == 1)
    m &= (
        5 * lits[0]
        + 7 * lits[1]
        + 4 * lits[3]
        + 8 * lits[4]
        + 3 * lits[5]
        + 9 * lits[6]
        + 6 * lits[7]
        + 10 * lits[8]
        + 7 * lits[9]
        + 11 * lits[10]
        + 8 * lits[11]
        <= 35
    )

    m._commit_pb()

    structured = next(entry for entry in calls if entry[0] == "structured.auto_leq" and any(w != 1 for w in entry[2]))
    _kind, _lits, _weights, _bound, amo_groups, eo_groups = structured
    assert [lits[0].id, lits[1].id] in amo_groups
    assert [lits[0].id, lits[1].id, lits[2].id] not in eo_groups


def test_commit_pb_uses_nonnullable_enum_domains_as_eo_candidates(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    enums = [m.enum(f"c{i}", choices=["r", "g", "b"], nullable=False) for i in range(4)]
    lits = []
    weights = []
    for i, enum in enumerate(enums):
        lits.extend([enum._choice_lits["r"], enum._choice_lits["g"], enum._choice_lits["b"]])
        weights.extend([10 + i, 20 + i, 30 + i])

    m &= (sum(w * lit for w, lit in zip(weights, lits)) <= 70)
    m._commit_pb()

    structured = next(entry for entry in calls if entry[0] == "structured.auto_leq" and any(w != 1 for w in entry[2]))
    _kind, _lits, _weights, _bound, amo_groups, eo_groups = structured
    assert amo_groups == []
    assert eo_groups == [
        [enums[0]._choice_lits["r"].id, enums[0]._choice_lits["g"].id, enums[0]._choice_lits["b"].id],
        [enums[1]._choice_lits["r"].id, enums[1]._choice_lits["g"].id, enums[1]._choice_lits["b"].id],
        [enums[2]._choice_lits["r"].id, enums[2]._choice_lits["g"].id, enums[2]._choice_lits["b"].id],
        [enums[3]._choice_lits["r"].id, enums[3]._choice_lits["g"].id, enums[3]._choice_lits["b"].id],
    ]


def test_commit_pb_uses_nullable_enum_domains_as_amo_candidates(monkeypatch):
    calls = []
    _patch_card_methods(monkeypatch, calls)
    _patch_pb_methods(monkeypatch, calls)
    _patch_structured_auto(monkeypatch, calls)

    m = Model()
    enums = [m.enum(f"c{i}", choices=["r", "g", "b"], nullable=True) for i in range(4)]
    lits = []
    weights = []
    for i, enum in enumerate(enums):
        lits.extend([enum._choice_lits["r"], enum._choice_lits["g"], enum._choice_lits["b"]])
        weights.extend([10 + i, 20 + i, 30 + i])

    m &= (sum(w * lit for w, lit in zip(weights, lits)) <= 70)
    m._commit_pb()

    structured = next(entry for entry in calls if entry[0] == "structured.auto_leq" and any(w != 1 for w in entry[2]))
    _kind, _lits, _weights, _bound, amo_groups, eo_groups = structured
    assert amo_groups == [
        [enums[0]._choice_lits["r"].id, enums[0]._choice_lits["g"].id, enums[0]._choice_lits["b"].id],
        [enums[1]._choice_lits["r"].id, enums[1]._choice_lits["g"].id, enums[1]._choice_lits["b"].id],
        [enums[2]._choice_lits["r"].id, enums[2]._choice_lits["g"].id, enums[2]._choice_lits["b"].id],
        [enums[3]._choice_lits["r"].id, enums[3]._choice_lits["g"].id, enums[3]._choice_lits["b"].id],
    ]
    assert eo_groups == []
