import pytest

from hermax.model import Model


@pytest.mark.parametrize(
    "constructor,args",
    [
        ("bool_vector", ("v", -1)),
        ("int_vector", ("v", -1, 0, 2)),
        ("enum_vector", ("v", -1, ["a"])),
        ("int_set_vector", ("v", -1)),
    ],
)
def test_vector_constructors_reject_negative_lengths(constructor, args):
    model = Model()
    with pytest.raises(ValueError, match="length"):
        getattr(model, constructor)(*args)


@pytest.mark.parametrize(
    "constructor,args",
    [
        ("bool_matrix", ("m", -1, 2)),
        ("bool_matrix", ("m", 2, -1)),
        ("int_matrix", ("m", -1, 2, 0, 2)),
        ("enum_matrix", ("m", 2, -1, ["a"])),
    ],
)
def test_matrix_constructors_reject_negative_dimensions(constructor, args):
    model = Model()
    with pytest.raises(ValueError, match="(rows|columns|cols|dimensions)"):
        getattr(model, constructor)(*args)


@pytest.mark.parametrize(
    "constructor,args",
    [
        ("bool_vector", ("v", True)),
        ("int_vector", ("v", False, 0, 2)),
        ("bool_matrix", ("m", True, 2)),
        ("bool_matrix", ("m", 2, False)),
    ],
)
def test_container_constructors_reject_boolean_shape_arguments(constructor, args):
    model = Model()
    with pytest.raises((TypeError, ValueError), match="(integer|length|dimension|rows|cols)"):
        getattr(model, constructor)(*args)
