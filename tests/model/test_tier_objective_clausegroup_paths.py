from __future__ import annotations

from hermax.model import Clause, ClauseGroup, Model


def test_tier_objective_accepts_multiclause_group_via_reification_path():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    group = ClauseGroup(m, [Clause(m, [a]), Clause(m, [b])])
    m.tier_obj[0, 3] += group

    r = m.solve(backend="maxsat")
    assert r.ok


def test_tier_objective_multiliteral_clause_violation_penalty_soundness():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= ~b

    # Higher weight soft clause (a | b): should be satisfied over ~a if relaxation polarity is sound.
    m.tier_obj[0, 10] += (a | b)
    # Lower weight soft clause ~a: penalizes setting a=True with cost 4.
    m.tier_obj[0, 4] += ~a

    r = m.solve(backend="maxsat")
    assert r.ok
    assert r[a] is True
    assert r.cost == 4
    assert r.tier_costs == [4]

