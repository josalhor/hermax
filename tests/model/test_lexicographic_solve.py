from __future__ import annotations

import pytest

from hermax.model import Model


def _solve_ok(m: Model, **kwargs):
    r = m.solve(**kwargs)
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def _build_two_tier_conflict_model() -> tuple[Model, object]:
    m = Model()
    a = m.bool("a")
    # Tier 0 prefers a=True (pay if false).
    m.tier_obj[0, 1] += a
    # Tier 1 prefers a=False (pay if true), conflicting with tier 0.
    m.tier_obj[1, 100] += ~a
    return m, a


def test_lex_incremental_honors_tier_priority_over_later_tier_weight():
    m, a = _build_two_tier_conflict_model()
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.status == "optimum"
    assert r[a] is True
    assert r.tier_costs == [0, 100]
    assert r.cost == 100


def test_lex_stratified_honors_tier_priority_over_later_tier_weight():
    m, a = _build_two_tier_conflict_model()
    r = _solve_ok(m, lex_strategy="stratified")
    assert r.status == "optimum"
    assert r[a] is True
    assert r.tier_costs == [0, 100]
    assert r.cost is not None


def test_lex_incremental_and_stratified_return_same_tier_costs():
    m1, a1 = _build_two_tier_conflict_model()
    r1 = _solve_ok(m1, lex_strategy="incremental")

    m2, a2 = _build_two_tier_conflict_model()
    r2 = _solve_ok(m2, lex_strategy="stratified")

    assert r1.tier_costs == r2.tier_costs
    assert r1[a1] is True
    assert r2[a2] is True
    assert r1.tier_costs == [0, 100]


def test_lex_three_tiers_returns_three_cost_entries():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    m.tier_obj[0, 2] += a
    m.tier_obj[1, 3] += b
    m.tier_obj[2, 4] += c
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.tier_costs is not None
    assert len(r.tier_costs) == 3
    assert r.tier_costs == [0, 0, 0]


def test_lex_incremental_assumptions_apply_to_all_tiers():
    m, a = _build_two_tier_conflict_model()
    # Force a=False with assumption; all tiers must see this.
    r = _solve_ok(m, lex_strategy="incremental", assumptions=[-a.id])
    assert r[a] is False
    assert r.tier_costs == [1, 0]
    assert r.cost == 0


def test_lex_stratified_assumptions_apply_to_solve():
    m, a = _build_two_tier_conflict_model()
    r = _solve_ok(m, lex_strategy="stratified", assumptions=[-a.id])
    assert r[a] is False
    assert r.tier_costs == [1, 0]
    assert r.cost is not None


def test_lex_incremental_hardening_preserves_earlier_tier_optimum():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    # Tier 0: force a=True in optimum.
    m.tier_obj[0, 1] += a
    # Tier 1: try to prefer a=False and b=False.
    m.tier_obj[1, 50] += ~a
    m.tier_obj[1, 1] += ~b
    r = _solve_ok(m, lex_strategy="incremental")
    assert r[a] is True
    assert r[b] is False
    # Tier0 optimum must remain fixed after tier1 optimization.
    assert r.tier_costs is not None
    assert r.tier_costs[0] == 0
    assert r.tier_costs[1] == 50


def test_lex_stratified_decodes_human_tier_costs():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.tier_obj[0, 1] += a
    m.tier_obj[1, 7] += ~b
    r = _solve_ok(m, lex_strategy="stratified")
    assert isinstance(r.tier_costs, list)
    assert len(r.tier_costs) == 2
    assert all(isinstance(x, (int, float)) for x in r.tier_costs)
    assert r.tier_costs == [0, 0]


def test_lex_incremental_collects_tier_models():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.tier_obj[0, 1] += a
    m.tier_obj[1, 1] += b
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.tier_models is not None
    assert len(r.tier_models) == 2
    assert all(isinstance(v, list) for v in r.tier_models)
    assert r.tier_costs == [0, 0]


def test_lex_stratified_tier_models_optional_none():
    m = Model()
    a = m.bool("a")
    m.tier_obj[0, 1] += a
    r = _solve_ok(m, lex_strategy="stratified")
    assert r.tier_models is None


def test_lex_incremental_with_pb_bucket_has_same_semantics_as_manual_tiers():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    # Tier 0: minimize violation of (a+b<=1)
    m.tier_obj[0, 3] += (a + b <= 1).clauses()
    # Tier 1: prefer a=true
    m.tier_obj[1, 1] += a
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.tier_costs is not None
    assert len(r.tier_costs) == 2
    assert r.tier_costs[0] == 0


def test_lex_incremental_with_intvar_bucket_is_supported():
    m = Model()
    x = m.int("x", 0, 4)
    m.tier_obj[0, 2] += x
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.tier_costs == [0]
    assert r[x] == 0
    assert r.cost == 0


def test_lex_incremental_handles_constant_offset_in_tier_objective():
    m = Model()
    a = m.bool("a")
    m.tier_obj[0, 1] += (a + 5)
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.tier_costs is not None
    # constant offset reflected at tier level
    assert r.tier_costs[0] == 5
    assert r[a] is False


def test_lex_stratified_handles_constant_offset_in_tier_objective():
    m = Model()
    a = m.bool("a")
    m.tier_obj[0, 1] += (a + 5)
    r = _solve_ok(m, lex_strategy="stratified")
    assert r.tier_costs is not None
    assert r.tier_costs[0] == 5
    assert r[a] is False


def test_lex_incremental_precision_returns_float_tier_costs_when_enabled():
    m = Model()
    m.set_objective_precision(decimals=2)
    a = m.bool("a")
    m &= ~a
    m.tier_obj[0, 1.25] += a
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.tier_costs is not None
    assert r.tier_costs[0] == pytest.approx(1.25)
    assert r.cost == pytest.approx(1.25)


def test_lex_stratified_precision_returns_float_tier_costs_when_enabled():
    m = Model()
    m.set_objective_precision(decimals=2)
    a = m.bool("a")
    m &= ~a
    m.tier_obj[0, 1.25] += a
    r = _solve_ok(m, lex_strategy="stratified")
    assert r.tier_costs is not None
    assert r.tier_costs[0] == pytest.approx(1.25)
    assert r.cost is not None


def test_lex_incremental_empty_tier_is_ignored_or_zero_cost():
    m = Model()
    a = m.bool("a")
    m.tier_obj[1, 2] += a
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.tier_costs is not None
    # Either compacts empty tier or keeps it as zero.
    assert len(r.tier_costs) in {1, 2}
    assert sum(float(x) for x in r.tier_costs) == pytest.approx(0.0)
    assert r[a] is True


def test_lex_strategy_requires_tier_obj_usage_for_tier_fields():
    m = Model()
    a = m.bool("a")
    m.obj[1] += a
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.tier_costs is None
    assert r.tier_models is None


def test_lex_stratified_raises_on_overflow_risk():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    huge = 2**62
    m.tier_obj[0, huge] += a
    m.tier_obj[1, huge] += b
    with pytest.raises((OverflowError, ValueError)):
        m.solve(lex_strategy="stratified")


def test_lex_incremental_does_not_require_stratification_scaling():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    huge = 2**62
    m.tier_obj[0, huge] += a
    m.tier_obj[1, huge] += b
    r = _solve_ok(m, lex_strategy="incremental")
    assert r.tier_costs is not None
    assert len(r.tier_costs) == 2


def test_lex_incremental_unsat_hard_constraints_short_circuit():
    m = Model()
    a = m.bool("a")
    m &= a
    m &= ~a
    m.tier_obj[0, 1] += a
    r = m.solve(lex_strategy="incremental")
    assert r.status == "unsat"
    assert r.tier_costs is None or all(c is None for c in r.tier_costs)


def test_lex_stratified_unsat_hard_constraints_short_circuit():
    m = Model()
    a = m.bool("a")
    m &= a
    m &= ~a
    m.tier_obj[0, 1] += a
    r = m.solve(lex_strategy="stratified")
    assert r.status == "unsat"
    assert r.tier_costs is None or all(c is None for c in r.tier_costs)


def test_lex_incremental_matches_reference_manual_hardening_small_case():
    # Lex reference: Tier0 minimize a; then Tier1 minimize ~a.
    m1, a1 = _build_two_tier_conflict_model()
    r1 = _solve_ok(m1, lex_strategy="incremental")

    # Manual 2-step reference.
    m2 = Model()
    a2 = m2.bool("a")
    m2.obj[1] += a2
    r2_0 = _solve_ok(m2)
    assert r2_0.cost == 0
    m2 &= a2  # harden tier0 optimum (a must remain true)
    m2.obj.clear()
    m2.obj[100] += ~a2
    r2_1 = _solve_ok(m2)

    assert r1[a1] == r2_1[a2]
    assert r1.tier_costs == [r2_0.cost, r2_1.cost]
    assert r1.tier_costs == [0, 100]


def test_lex_incremental_respects_assumptions_across_multiple_tiers_complex():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    m.tier_obj[0, 5] += a
    m.tier_obj[1, 4] += b
    m.tier_obj[2, 3] += c
    r = _solve_ok(m, lex_strategy="incremental", assumptions=[-a.id, b.id])
    assert r[a] is False
    assert r[b] is True
    assert r[c] is True
    assert r.tier_costs == [5, 0, 0]
    assert r.cost == 0


def test_lex_stratified_respects_assumptions_across_multiple_tiers_complex():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    m.tier_obj[0, 5] += a
    m.tier_obj[1, 4] += b
    m.tier_obj[2, 3] += c
    r = _solve_ok(m, lex_strategy="stratified", assumptions=[-a.id, b.id])
    assert r[a] is False
    assert r[b] is True
    assert r[c] is True
    assert r.tier_costs == [5, 0, 0]
    assert r.cost is not None


def test_lex_counterexample_tier_order_changes_solution_incremental():
    # Requested canonical case:
    # Tier 0: minimize ~a (prefer a=False)
    # Tier 1: minimize (50*a + b)
    # Hard: a -> ~b and b -> ~a
    # Tier1-only optimum would be a=True,b=False (cost 0),
    # but lex order must keep tier0 optimum: a=False,b=True.
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= a.implies(~b)
    m &= b.implies(~a)
    m.tier_obj[0, 1] += ~a
    m.tier_obj[1, 50] += a
    m.tier_obj[1, 1] += b
    r = _solve_ok(m, lex_strategy="incremental")
    assert r[a] is False
    assert r[b] is True
    assert r.tier_costs == [0, 50]
    assert r.cost == 50


def test_lex_counterexample_tier_order_changes_solution_stratified():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= a.implies(~b)
    m &= b.implies(~a)
    m.tier_obj[0, 1] += ~a
    m.tier_obj[1, 50] += a
    m.tier_obj[1, 1] += b
    r = _solve_ok(m, lex_strategy="stratified")
    assert r[a] is False
    assert r[b] is True
    assert r.tier_costs == [0, 50]


def test_flat_objective_prefers_tier1_only_solution_for_counterexample():
    # This test pins the "independent tier-1" behavior for comparison.
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= a.implies(~b)
    m &= b.implies(~a)
    m.obj[50] += a
    m.obj[1] += b
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is False
    assert r.cost == 1


def test_lex_two_tiers_with_unique_optimum_has_exact_assignment_incremental():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a | b)
    m.tier_obj[0, 10] += ~a
    m.tier_obj[1, 3] += ~b
    r = _solve_ok(m, lex_strategy="incremental")
    assert r[a] is False
    assert r[b] is True
    assert r.tier_costs == [0, 3]


def test_lex_two_tiers_with_unique_optimum_has_exact_assignment_stratified():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a | b)
    m.tier_obj[0, 10] += ~a
    m.tier_obj[1, 3] += ~b
    r = _solve_ok(m, lex_strategy="stratified")
    assert r[a] is False
    assert r[b] is True
    assert r.tier_costs == [0, 3]


def test_lex_incremental_tie_in_tier0_is_broken_by_tier1():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    # Tier0 always 0 regardless of assignment.
    m.tier_obj[0, 1] += True
    # Tier1 forces preference.
    m.tier_obj[1, 5] += a
    m.tier_obj[1, 1] += ~b
    r = _solve_ok(m, lex_strategy="incremental")
    assert r[a] is True
    assert r[b] is False
    assert r.tier_costs == [0, 0]


def test_lex_stratified_tie_in_tier0_is_broken_by_tier1():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.tier_obj[0, 1] += True
    m.tier_obj[1, 5] += a
    m.tier_obj[1, 1] += ~b
    r = _solve_ok(m, lex_strategy="stratified")
    assert r[a] is True
    assert r[b] is False
    assert r.tier_costs == [0, 0]


def test_lex_incremental_with_hard_forced_assignment_reports_exact_tier_costs():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= ~a
    m &= b
    m.tier_obj[0, 7] += a
    m.tier_obj[1, 4] += ~b
    r = _solve_ok(m, lex_strategy="incremental")
    assert r[a] is False
    assert r[b] is True
    assert r.tier_costs == [7, 4]
    assert r.cost == 4


def test_lex_stratified_with_hard_forced_assignment_reports_exact_tier_costs():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= ~a
    m &= b
    m.tier_obj[0, 7] += a
    m.tier_obj[1, 4] += ~b
    r = _solve_ok(m, lex_strategy="stratified")
    assert r[a] is False
    assert r[b] is True
    assert r.tier_costs == [7, 4]


def test_lex_strategies_use_different_number_of_solver_calls(monkeypatch):
    calls = {"n": 0}
    original = Model._solve_with_hermax_solver

    def wrapped(self, *args, **kwargs):
        calls["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Model, "_solve_with_hermax_solver", wrapped)

    m_inc = Model()
    a_inc = m_inc.bool("a")
    b_inc = m_inc.bool("b")
    c_inc = m_inc.bool("c")
    m_inc.tier_obj[0, 1] += a_inc
    m_inc.tier_obj[1, 1] += b_inc
    m_inc.tier_obj[2, 1] += c_inc
    _ = _solve_ok(m_inc, lex_strategy="incremental")
    assert calls["n"] == 3

    calls["n"] = 0
    m_str = Model()
    a_str = m_str.bool("a")
    b_str = m_str.bool("b")
    c_str = m_str.bool("c")
    m_str.tier_obj[0, 1] += a_str
    m_str.tier_obj[1, 1] += b_str
    m_str.tier_obj[2, 1] += c_str
    _ = _solve_ok(m_str, lex_strategy="stratified")
    assert calls["n"] == 1


def test_lex_strategies_have_different_cost_field_semantics():
    # Force both tiers to incur non-zero penalties:
    # incremental.cost == last tier cost
    # stratified.cost == flattened weighted cost
    m1 = Model()
    a1 = m1.bool("a")
    b1 = m1.bool("b")
    m1 &= ~a1
    m1 &= ~b1
    m1.tier_obj[0, 5] += a1
    m1.tier_obj[1, 2] += b1
    r_inc = _solve_ok(m1, lex_strategy="incremental")
    assert r_inc.tier_costs == [5, 2]
    assert r_inc.cost == 2

    m2 = Model()
    a2 = m2.bool("a")
    b2 = m2.bool("b")
    m2 &= ~a2
    m2 &= ~b2
    m2.tier_obj[0, 5] += a2
    m2.tier_obj[1, 2] += b2
    r_str = _solve_ok(m2, lex_strategy="stratified")
    assert r_str.tier_costs == [5, 2]
    # base for tier0 is max_tier1 + 1 = 3 => flattened = 5*3 + 2
    assert r_str.cost == 17
