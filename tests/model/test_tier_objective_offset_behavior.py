from __future__ import annotations

import pytest

from hermax.model import Model


def test_tier_objective_tracks_negative_constant_offset_branch():
    m = Model()
    a = m.bool("a")
    # Negative constant in tier expression should flow through negative-offset path.
    m.tier_obj.add(a - 3, weight=2, tier=0)
    r = m.solve(backend="maxsat")
    assert r.ok


@pytest.mark.parametrize("entry", ["add", "set_lexicographic", "add_soft"])
@pytest.mark.parametrize("precision", [None, 2])
def test_negative_flat_constant_cannot_be_silently_replaced_by_tiers(entry, precision):
    m = Model()
    if precision is not None:
        m.set_objective_precision(decimals=precision)
    b = m.bool("b")
    m.obj = -3

    with pytest.raises(ValueError, match="mutually exclusive"):
        if entry == "add":
            m.tier_obj.add(b, weight=2)
        elif entry == "set_lexicographic":
            m.tier_obj.set_lexicographic(b)
        else:
            with pytest.warns(FutureWarning):
                m.tier_obj.add_soft(b, weight=2)

    assert m.solve().cost == -3
    assert not m.tier_obj.is_active()


def test_clearing_negative_flat_constant_allows_tiered_objective():
    m = Model()
    b = m.bool("b")
    m.obj = -3
    m.obj.clear()
    m &= b
    m.tier_obj.add(b, weight=2)

    assert m.solve().tier_costs == [2]
