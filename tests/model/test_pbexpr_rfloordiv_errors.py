from __future__ import annotations

import pytest

from hermax.model import Model


def test_pbexpr_rfloordiv_with_model_bound_lhs_raises_nonlinear_error():
    m = Model()
    a = m.bool("a")
    expr = 2 * a + 1
    with pytest.raises(TypeError, match="Unsupported arithmetic"):
        _ = a // expr
