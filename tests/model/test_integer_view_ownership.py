import pytest

from hermax.model import Model


@pytest.mark.parametrize("width", [0, 1, 7])
def test_binary_view_is_owned_and_cached_by_integer(width):
    model = Model()
    x = model.int("x", -3, width - 3)
    assert not hasattr(model, "_integer_sum_views")
    assert x._binary_view is None
    view = x._get_binary_view()
    top = model._top_id()
    assert x._get_binary_view() is view
    assert model._top_id() == top
    assert len(view) == width.bit_length()


def test_binary_views_are_not_shared_between_models():
    a, b = Model(), Model()
    x, y = a.int("x", 0, 5), b.int("x", 0, 5)
    assert x._get_binary_view() is not y._get_binary_view()
