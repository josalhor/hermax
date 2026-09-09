import pytest

from hermax.model import Model


def test_enum_rejects_string_choices_argument():
    with pytest.raises(TypeError, match="sequence|choices"):
        Model().enum("letters", choices="ab")


@pytest.mark.parametrize("nullable", [1, 0, "yes", None])
def test_enum_rejects_non_boolean_nullable_argument(nullable):
    with pytest.raises(TypeError, match="bool|nullable"):
        Model().enum("value", choices=["a"], nullable=nullable)


@pytest.mark.parametrize(
    "constructor",
    [
        lambda model: model.bool(1),
        lambda model: model.int(1, lb=0, ub=1),
        lambda model: model.enum(1, choices=["a"]),
    ],
)
def test_scalar_typed_constructors_reject_non_string_names(constructor):
    with pytest.raises(TypeError, match="name|string"):
        constructor(Model())


@pytest.mark.parametrize("method_name", ["max", "min", "upper_bound", "lower_bound"])
def test_single_item_integer_aggregates_validate_type_and_model(method_name):
    model = Model()
    foreign = Model().int("foreign", lb=0, ub=1)

    with pytest.raises(ValueError, match="different models|belong"):
        getattr(model, method_name)([foreign])


@pytest.mark.parametrize("method_name", ["max", "min", "upper_bound", "lower_bound"])
def test_single_item_integer_aggregates_reject_non_int_items(method_name):
    with pytest.raises(TypeError, match="IntVar|integer"):
        getattr(Model(), method_name)([1])


@pytest.mark.parametrize(
    "constructor",
    [
        lambda model: model.enum_vector("v", length=1, choices=["a", "a"]),
        lambda model: model.enum_dict("d", keys=[], choices=["a", "a"]),
        lambda model: model.enum_matrix("m", rows=1, cols=2, choices=["a", "a"]),
        lambda model: model.int_vector("v", length=1, lb=2, ub=1),
        lambda model: model.int_dict("d", keys=[], lb=2, ub=1),
        lambda model: model.int_matrix("m", rows=1, cols=2, lb=2, ub=1),
    ],
)
def test_containers_validate_shared_domain_arguments(constructor):
    with pytest.raises((TypeError, ValueError), match="(choice|unique|domain|lb|bound)"):
        constructor(Model())


@pytest.mark.parametrize(
    "constructor",
    [
        lambda model: model.bool_vector("__user", length=1),
        lambda model: model.int_dict("__user", keys=[], lb=0, ub=1),
        lambda model: model.enum_matrix("__user", rows=1, cols=1, choices=["a"]),
    ],
)
def test_containers_reject_reserved_names(constructor):
    with pytest.raises(ValueError, match="reserved"):
        constructor(Model())


def test_enum_choices_cannot_diverge_from_choice_literals():
    enum = Model().enum("value", choices=["a", "b"])
    try:
        enum.choices.append("c")
    except (AttributeError, TypeError):
        return

    assert set(enum.choices) == set(enum._choice_lits)


@pytest.mark.parametrize(
    "bad_call, retry_call",
    [
        (
            lambda model: model.enum("item", choices=["a", "a"]),
            lambda model: model.enum("item", choices=["a"]),
        ),
        (
            lambda model: model.int("item", lb=2, ub=1),
            lambda model: model.int("item", lb=0, ub=1),
        ),
        (
            lambda model: model.interval("item", start=0, duration=0, end=2),
            lambda model: model.interval("item", start=0, duration=1, end=2),
        ),
        (
            lambda model: model.int_vector("item", length=2, lb=2, ub=1),
            lambda model: model.int_vector("item", length=2, lb=0, ub=1),
        ),
        (
            lambda model: model.enum_vector("item", length=2, choices=["a", "a"]),
            lambda model: model.enum_vector("item", length=2, choices=["a"]),
        ),
        (
            lambda model: model.int_matrix("item", rows=2, cols=2, lb=2, ub=1),
            lambda model: model.int_matrix("item", rows=2, cols=2, lb=0, ub=1),
        ),
    ],
)
def test_failed_typed_constructor_does_not_poison_name(bad_call, retry_call):
    model = Model()
    with pytest.raises((TypeError, ValueError)):
        bad_call(model)

    retry_call(model)
