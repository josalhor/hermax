from __future__ import annotations

import pytest

from hermax.model import Model


def test_cumulative_validation_branches_and_trivial_returns():
    m = Model()
    s = m.int("s", lb=0, ub=3)
    with pytest.raises(TypeError):
        m.cumulative([s], [1], [1], capacity=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        m.cumulative([s], [1], [1], capacity=-1)
    with pytest.raises(ValueError):
        m.cumulative([s], [1], [1], capacity=1, backend="bad")
    with pytest.raises(ValueError):
        m.cumulative([s], [1, 2], [1], capacity=1)
    with pytest.raises(TypeError):
        m.cumulative([1], [1], [1], capacity=1)  # type: ignore[list-item]
    with pytest.raises(TypeError):
        m.cumulative([s], [1.2], [1], capacity=1)  # type: ignore[list-item]
    with pytest.raises(TypeError):
        m.cumulative([s], [1], [1.2], capacity=1)  # type: ignore[list-item]
    with pytest.raises(ValueError):
        m.cumulative([s], [-1], [1], capacity=1)
    with pytest.raises(ValueError):
        m.cumulative([s], [1], [-1], capacity=1)

    m.cumulative([], [], [], capacity=0)
    m.cumulative([s], [0], [1], capacity=1)
    m.cumulative([s], [1], [0], capacity=1)

    m2 = Model()
    s2 = m2.int("s2", lb=0, ub=1)
    m2.cumulative([s2], [1], [1], capacity=0)
    assert m2.solve().status == "unsat"
