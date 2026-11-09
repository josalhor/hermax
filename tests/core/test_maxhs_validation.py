import pytest

from hermax.core.maxhs_wrapper_py.maxhs_solver import MaxHSSolver


def test_maxhs_rejects_boolean_nonnegative_weights():
    with pytest.raises((TypeError, ValueError)):
        MaxHSSolver._normalize_nonnegative_weight(True)
