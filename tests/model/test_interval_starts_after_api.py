from __future__ import annotations

import pytest

from hermax.model import Model


def test_interval_starts_after_type_and_model_validation():
    m = Model()
    a = m.interval("a", start=0, duration=2, end=8)
    b = m.interval("b", start=0, duration=2, end=8)
    g = a.starts_after(b)
    m &= g
    assert m.solve().ok

    with pytest.raises(TypeError, match="IntervalVar"):
        a.starts_after(object())

    m2 = Model()
    c = m2.interval("c", start=0, duration=2, end=8)
    with pytest.raises(ValueError, match="different models"):
        a.starts_after(c)
