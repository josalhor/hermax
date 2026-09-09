import pytest

from hermax.core.maxhs_wrapper_py.maxhs_solver import MaxHSSolver


@pytest.mark.xfail(
    strict=True,
    reason="MaxHSSolver's custom nonnegative-weight validator accepts bool as an integer",
)
def test_maxhs_rejects_boolean_nonnegative_weights():
    with pytest.raises((TypeError, ValueError)):
        MaxHSSolver._normalize_nonnegative_weight(True)
