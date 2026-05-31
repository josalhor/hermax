from __future__ import annotations

from hermax.model import Model


def test_intvector_lazy_aggregate_exprs_realize_for_all_kinds():
    m = Model()
    v = m.int_vector("v", length=3, lb=0, ub=5)

    e_max = v.max(name="mx")
    e_min = v.min(name="mn")
    e_ub = v.upper_bound(name="ub")
    e_lb = v.lower_bound(name="lb")

    # Force realization of all lazy aggregate kinds via comparisons.
    m &= (e_max <= 4)
    m &= (e_min >= 1)
    m &= (e_ub <= 5)
    m &= (e_lb >= 0)

    # Also exercise bound properties from constructor branches.
    assert e_max.lb == 0 and e_max.ub == 5
    assert e_min.lb == 0 and e_min.ub == 5
    assert e_ub.lb == 0 and e_ub.ub == 5
    assert e_lb.lb == 0 and e_lb.ub == 5

    r = m.solve()
    assert r.ok
