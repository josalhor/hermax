import pytest

from hermax.model import Model


@pytest.mark.parametrize("method_name", ["running_max", "running_min", "running_sum"])
def test_failed_running_aggregate_does_not_partially_mutate_model(method_name):
    model = Model()
    vector = model.vector(
        [
            model.int("a", 0, 2),
            model.int("b", 0, 2),
            model.int("c", 0, 2),
        ],
        name="items",
    )
    # The first generated step (agg[1]) is free, while the second one collides.
    model.bool("agg[2]")
    before = (
        model._next_id,
        len(model._hard),
        set(model._registry),
        set(model._container_names),
    )

    with pytest.raises(ValueError, match="already registered"):
        getattr(vector, method_name)("agg")

    after = (
        model._next_id,
        len(model._hard),
        set(model._registry),
        set(model._container_names),
    )
    assert after == before


def test_failed_sum_var_does_not_partially_mutate_model():
    model = Model()
    items = [model.int(name, 0, 2) for name in ("a", "b", "c")]
    model.bool("agg_step1")
    before = (
        model._next_id,
        len(model._hard),
        set(model._registry),
        set(model._container_names),
    )

    with pytest.raises(ValueError, match="already registered"):
        model.sum_var(items, name="agg")

    after = (
        model._next_id,
        len(model._hard),
        set(model._registry),
        set(model._container_names),
    )
    assert after == before
