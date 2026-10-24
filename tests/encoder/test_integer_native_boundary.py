from hermax.encoder.card import pycard
from hermax.internal import _pblib, _integer_sum_native


def test_integer_encoders_and_budgets_belong_to_the_owned_module():
    assert hasattr(_integer_sum_native, "encode_order_sum")
    assert hasattr(_integer_sum_native, "EncodingBudgetExceeded")
    assert not hasattr(pycard, "encode_order_sum")
    assert not hasattr(_pblib, "EncodingBudgetExceeded")
