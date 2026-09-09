import pytest

from hermax.model import Model


def _objective_bookkeeping(model: Model):
    return (
        len(model._hard),
        len(model._soft),
        model._next_soft_group_id,
        dict(model._soft_group_to_ids),
    )


def _expression_objective_state(model: Model):
    proxy = model.obj
    return (
        _objective_bookkeeping(model),
        dict(proxy._lit_to_sid),
        dict(proxy._lit_weights),
        int(proxy._offset),
        int(model._objective_constant),
    )


@pytest.mark.parametrize("bad_objective", ["foreign_literal", "unsupported_object"])
def test_invalid_objective_addition_is_failure_atomic(bad_objective):
    model = Model()
    model.bool("a")

    other = Model()
    bad = other.bool("b") if bad_objective == "foreign_literal" else object()
    before = _objective_bookkeeping(model)

    with pytest.raises((TypeError, ValueError)):
        model.obj.add_soft(bad, 1)

    assert _objective_bookkeeping(model) == before


def test_invalid_objective_replacement_preserves_existing_objective():
    model = Model()
    current = model.bool("current")
    other = Model()
    replacement = other.bool("replacement")
    model.obj.add(current, weight=3)
    before = _expression_objective_state(model)

    with pytest.raises(ValueError, match="different models"):
        model.obj.replace_with(replacement)

    assert _expression_objective_state(model) == before


def test_invalid_lexicographic_objective_preserves_existing_tiers():
    model = Model()
    current = model.bool("current")
    other = Model()
    replacement = other.bool("replacement")
    model.tier_obj[0, 2] += current
    before = {tier: dict(data) for tier, data in model.tier_obj._tiers.items()}

    with pytest.raises(ValueError, match="different models"):
        model.tier_obj.set_lexicographic(current, replacement)

    assert model.tier_obj._tiers == before


def test_invalid_foreign_tier_clause_does_not_create_empty_tier():
    model = Model()
    other = Model()
    foreign = other.bool("foreign")
    group = foreign.implies(foreign)
    before = {tier: dict(data) for tier, data in model.tier_obj._tiers.items()}

    with pytest.raises(ValueError, match="different models"):
        model.tier_obj[4, 1] += group

    assert model.tier_obj._tiers == before
