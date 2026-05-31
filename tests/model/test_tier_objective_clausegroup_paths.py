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
