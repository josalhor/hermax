import pytest

from hermax.model import Model


@pytest.mark.parametrize(
    "bad_call,retry_call",
    [
        (
            lambda model: model.bool_vector("item", length=1.5),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.int_set_vector("item", length=1, values=[1, 2.5]),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.bool_matrix("item", rows=1.5, cols=2),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.enum_matrix("item", rows=1, cols=1, choices=["a", "a"]),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.bool_dict("item", keys=1),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.int_dict("item", keys=[1], lb=2, ub=1),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.enum_dict("item", keys=[1], choices=["a", "a"]),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.int_set_dict("item", keys=[1], values=[1, 2.5]),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.interval("item", start=0, duration=0, end=2),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.enum("item", choices=["a", "a"]),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.int("item", lb=2, ub=1),
            lambda model: model.bool("item"),
        ),
        (
            lambda model: model.int_matrix("item", rows=1.5, cols=1, lb=0, ub=1),
            lambda model: model.bool("item"),
        ),
    ],
)
def test_failed_container_constructor_does_not_poison_name(bad_call, retry_call):
    model = Model()
    with pytest.raises((TypeError, ValueError)):
        bad_call(model)

    retry_call(model)


@pytest.mark.parametrize(
    "prepare_collision,construct",
    [
        (
            lambda model: model.bool("item.end"),
            lambda model: model.interval("item", start=0, duration=2, end=5),
        ),
        (
            lambda model: model.bool("item[1]"),
            lambda model: model.int_vector("item", length=3, lb=0, ub=2),
        ),
        (
            lambda model: model.bool("item[1]"),
            lambda model: model.enum_vector("item", length=3, choices=["a", "b"]),
        ),
        (
            lambda model: model.bool("item['b']"),
            lambda model: model.int_dict("item", keys=["a", "b"], lb=0, ub=2),
        ),
    ],
)
def test_generated_child_collision_does_not_partially_mutate_model(prepare_collision, construct):
    model = Model()
    prepare_collision(model)
    before = (
        model._next_id,
        len(model._hard),
        set(model._registry),
        set(model._container_names),
    )

    with pytest.raises(ValueError, match="already registered"):
        construct(model)

    after = (
        model._next_id,
        len(model._hard),
        set(model._registry),
        set(model._container_names),
    )
    assert after == before
