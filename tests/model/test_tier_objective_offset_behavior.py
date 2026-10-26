from __future__ import annotations

from hermax.model import Model


def test_tier_objective_tracks_negative_constant_offset_branch():
    m = Model()
    a = m.bool("a")
    # Negative constant in tier expression should flow through negative-offset path.
    m.tier_obj.add(a - 3, weight=2, tier=0)
    r = m.solve(backend="maxsat")
    assert r.ok
