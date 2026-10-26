import itertools

import pytest

from hermax.model import Model
from tests.model.test_soft_behavior import FakeIPSoft


@pytest.mark.parametrize(
    "form", ["literal", "term", "sum", "integer", "signed", "constant"]
)
def test_numeric_handle_reweights_exact_cost(form):
    m = Model()
    x = m.bool("x")
    n = m.int("n", -2, 3)
    m &= x
    m &= n == -1
    expression, value = {
        "literal": (x, 1),
        "term": (1 * x, 1),
        "sum": (2 * x + n + 4, 5),
        "integer": (n, -1),
        "signed": (-3 * x - 2, -5),
        "constant": (4, 4),
    }[form]
    term = m.obj.add(expression, weight=3)
    assert term.weight == 3
    assert m.solve().cost == 3 * value
    m.obj.update(term, weight=7)
    assert term.weight == 7
    assert m.solve().cost == 7 * value


def test_handles_only_update_their_own_contribution():
    m = Model()
    x, y = m.bool("x"), m.bool("y")
    m &= x
    m &= y
    a = m.obj.add(2 * x - y + 3, weight=2)
    b = m.obj.add(x + 4 * y - 2, weight=3)
    m.obj += 5 * x
    for wa, wb in itertools.product((0, 1, 7), repeat=2):
        m.obj.update(a, weight=wa)
        m.obj.update(b, weight=wb)
        assert m.solve().cost == 4 * wa + 3 * wb + 5


@pytest.mark.parametrize("initial", [0, 3])
def test_handle_can_be_disabled_and_reenabled(initial):
    m = Model()
    x = m.bool("x")
    m &= x
    term = m.obj.add(x - 2, weight=initial)
    for weight in [4, 0, 7, 0, 2]:
        m.obj.update(term, weight=weight)
        assert term.weight == weight
        if weight:
            assert m.solve().cost == -weight
        else:
            assert all(w == 0 for w, _ in m._soft)
            assert m._objective_constant == 0


def test_reweight_changes_the_optimum_without_changing_other_costs():
    m = Model()
    x = m.bool("x")
    cost = m.obj.add(x, weight=2)
    preference = m.obj.add(~x, weight=3)
    assert m.solve()[x] is True
    m.obj.update(cost, weight=4)
    result = m.solve()
    assert result[x] is False and result.cost == 3
    m.obj.update(preference, weight=5)
    result = m.solve()
    assert result[x] is True and result.cost == 4


@pytest.mark.parametrize("replacement", ["clear", "assignment", "set", "replace"])
def test_clearing_or_replacing_invalidates_numeric_handles(replacement):
    m = Model()
    x = m.bool("x")
    term = m.obj.add(x, weight=3)
    if replacement == "clear":
        m.obj.clear()
    elif replacement == "assignment":
        m.obj = x
    elif replacement == "set":
        m.obj.set(x)
    else:
        m.obj.replace_with(x)
    with pytest.raises(ValueError, match="cleared|replaced|active"):
        m.obj.update(term, weight=4)


@pytest.mark.parametrize("bad", [-1, True, 1.5, float("nan")])
def test_invalid_weight_update_preserves_cost(bad):
    m = Model()
    x = m.bool("x")
    m &= x
    term = m.obj.add(x + 2, weight=3)
    with pytest.raises((ValueError, TypeError)):
        m.obj.update(term, weight=bad)
    assert term.weight == 3 and m.solve().cost == 9


def test_decimal_reweight_is_scaled_once():
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= x
    term = m.obj.add(2 * x - 3, weight=1.25)
    assert m.solve().cost == -1.25
    m.obj.update(term, weight=2.75)
    assert term.weight == 2.75
    assert m.solve().cost == -2.75


def test_large_integer_handle_weights_remain_exact():
    m = Model()
    x = m.bool("x")
    m &= x
    term = m.obj.add(x, weight=2**55 + 7)
    assert m.solve().cost == 2**55 + 7
    m.obj.update(term, weight=2**55 + 9)
    assert term.weight == 2**55 + 9
    assert m.solve().cost == 2**55 + 9


@pytest.mark.parametrize("value", [False, True])
def test_legacy_literal_preference_warns_and_keeps_its_direction(value):
    m = Model()
    x = m.bool("x")
    m &= x if value else ~x
    with pytest.warns(FutureWarning, match="obj.add"):
        term = m.obj.add_soft(x, weight=3)
    assert m.solve().cost == 3 * (not value)
    with pytest.warns(FutureWarning, match="weight"):
        m.obj.update_soft(term, 7)
    assert term.weight == 7
    assert m.solve().cost == 7 * (not value)
    m.obj.update(term, weight=5)
    assert m.solve().cost == 5 * (not value)


def test_numeric_add_soft_fails_with_migration_guidance():
    m = Model()
    x = m.int("x", 0, 4)
    with pytest.raises(TypeError, match="obj.add"):
        m.obj.add_soft(x, 3)
    assert not m._soft


@pytest.mark.parametrize("weight", [0, 1, -1, 1.25])
def test_retired_flat_indexing_fails_before_mutation(weight):
    m = Model()
    x = m.bool("x")
    with pytest.raises(TypeError, match="obj.*\\+=|obj.add"):
        m.obj[weight] += x
    assert not m._soft


def test_retired_tier_indexing_fails_before_mutation():
    m = Model()
    x = m.bool("x")
    with pytest.raises(TypeError, match="tier_obj.add|set_lexicographic"):
        m.tier_obj[0, 3] += x
    assert not m.tier_obj.is_active()


def test_tier_numeric_handles_reweight_independently():
    m = Model()
    x = m.bool("x")
    a = m.tier_obj.add(x, weight=2, tier=0)
    m.tier_obj.add(~x, weight=3, tier=0)
    m.tier_obj.add(x, weight=5, tier=1)
    assert m.solve()[x] is True
    m.tier_obj.update(a, weight=4)
    result = m.solve()
    assert result[x] is False and result.tier_costs == [3, 0]
    m.tier_obj.clear()
    with pytest.raises(ValueError, match="cleared|replaced|active"):
        m.tier_obj.update(a, weight=2)


def test_incremental_reweight_and_zero_restore():
    m = Model()
    x = m.bool("x")
    m &= x
    term = m.obj.add(x - 2, weight=3)
    assert m.solve(backend="maxsat").cost == -3
    for weight in (7, 0, 2):
        m.obj.update(term, weight=weight)
        assert m.solve(backend="maxsat").cost == -weight


def test_handle_snapshots_the_numeric_expression():
    m = Model()
    x = m.bool("x")
    m &= x
    expr = 2 * x + 3
    term = m.obj.add(expr, weight=2)
    expr.constant = 999
    expr.terms.clear()
    m.obj.update(term, weight=7)
    assert m.solve().cost == 35


def test_zero_weight_defers_lazy_expression_until_activation():
    m = Model()
    x = m.int("x", 0, 6)
    m &= x == 5
    quotient = x // 2
    term = m.obj.add(quotient, weight=0)
    assert quotient._realized is None
    m.obj.update(term, weight=3)
    assert m.solve().cost == 6


def test_numeric_and_legacy_handles_can_share_a_soft_literal():
    m = Model()
    x = m.bool("x")
    m &= ~x
    term = m.obj.add(~x, weight=2)
    with pytest.warns(FutureWarning):
        preference = m.obj.add_soft(x, 3)
    m.obj.update(term, weight=7)
    m.obj.update(preference, weight=4)
    assert m.solve().cost == 11
    m.obj.update(term, weight=0)
    assert m.solve().cost == 4
    m.obj.update(preference, weight=0)
    m.obj.update(term, weight=2)
    assert m.solve().cost == 2


def test_reweight_matches_the_expression_for_every_small_assignment():
    m = Model()
    x, y = m.bool("x"), m.bool("y")
    n = m.int("n", -1, 2)
    term = m.obj.add(2 * x - 3 * y + n + 1, weight=2)
    m.obj += y
    for weight in [1, 0, 3, 2]:
        m.obj.update(term, weight=weight)
        for xv, yv, nv in itertools.product([False, True], [False, True], range(-1, 3)):
            result = m.solve(assumptions=[x if xv else ~x, y if yv else ~y, n == nv])
            assert result.cost == weight * (2 * xv - 3 * yv + nv + 1) + yv


def test_precision_change_with_numeric_cost_is_rejected_without_mutation():
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= x
    term = m.obj.add(2 * x - 3, weight=1.25)
    with pytest.raises(ValueError, match="precision.*before|clear.*objective"):
        m.set_objective_precision(decimals=1)
    assert m.solve().cost == -1.25
    m.obj.update(term, weight=2.5)
    assert m.solve().cost == -2.5
    m.obj.clear()
    m.set_objective_precision(decimals=1)
    assert not any(weight for weight, _ in m._soft)


def test_precision_change_invalidates_legacy_weight_handles():
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= ~x
    with pytest.warns(FutureWarning):
        term = m.obj.add_soft(x, 1.25)
    m.set_objective_precision(decimals=1)
    assert m.solve().cost == 1.2
    with pytest.raises(ValueError, match="precision|Precision"):
        m.obj.update(term, weight=2.5)


def test_reweighted_legacy_cost_rerounds_from_its_updated_weight():
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= ~x
    with pytest.warns(FutureWarning):
        term = m.obj.add_soft(x, 1.25)
    m.obj.update(term, weight=2.34)
    m.set_objective_precision(decimals=1)
    assert m.solve().cost == 2.3


def test_legacy_zero_weight_handle_can_be_enabled_and_rerounded():
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= ~x
    with pytest.warns(FutureWarning):
        term = m.obj.add_soft(x, 0)
    m.obj.update(term, weight=1.25)
    assert m.solve().cost == 1.25
    m.set_objective_precision(decimals=1)
    assert m.solve().cost == 1.2


def test_failed_legacy_precision_change_preserves_weights_and_handles():
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= ~x
    with pytest.warns(FutureWarning):
        term = m.obj.add_soft(x, 0.01)
    with pytest.raises(ValueError, match="rounds"):
        m.set_objective_precision(decimals=1)
    assert m.solve().cost == 0.01
    m.obj.update(term, weight=0.02)
    assert m.solve().cost == 0.02


def test_backend_failure_during_reweight_preserves_the_whole_term():
    class FailingUpdate(FakeIPSoft):
        fail = False
        updates = 0

        def set_soft(self, lit, weight):
            if self.fail:
                self.updates += 1
                if self.updates == 2:
                    raise RuntimeError("injected update failure")
            super().set_soft(lit, weight)

    m = Model()
    x, y = m.bool("x"), m.bool("y")
    m &= x
    m &= y
    term = m.obj.add(x + 2 * y, weight=2)
    solver = FailingUpdate()
    m.solve(backend="maxsat", solver=solver)
    old_weights = list(m._soft)
    solver.fail = True
    with pytest.raises(RuntimeError, match="injected"):
        m.obj.update(term, weight=3)
    assert term.weight == 2
    assert m._soft == old_weights
    assert m.solve().cost == 6


@pytest.mark.parametrize("tiered", [False, True])
def test_small_decimal_multiplier_is_applied_before_rounding(tiered):
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= x
    objective = m.tier_obj if tiered else m.obj
    term = objective.add(1000 * x, weight=0.001)
    assert m.solve().cost == 1.0
    objective.update(term, weight=0.002)
    assert m.solve().cost == 2.0


def test_positive_numeric_weight_rounding_to_zero_does_not_silently_disable_cost():
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= x
    term = m.obj.add(x, weight=1)
    with pytest.raises(ValueError, match="rounds to zero"):
        m.obj.update(term, weight=0.001)
    assert term.weight == 1 and m.solve().cost == 1.0


def test_negative_constant_objective_blocks_precision_change():
    m = Model()
    m.obj = -3
    with pytest.raises(ValueError, match="precision"):
        m.set_objective_precision(decimals=2)
    assert m.solve().cost == -3


@pytest.mark.parametrize("tiered", [False, True])
def test_explicit_update_changes_only_the_selected_term(tiered):
    m = Model()
    x = m.bool("x")
    m &= x
    objective = m.tier_obj if tiered else m.obj
    term = objective.add(x + 2, weight=3)
    objective.add(x, weight=2)
    assert objective.update(term, weight=7) is None
    assert term.weight == 7
    assert m.solve().cost == 23


@pytest.mark.parametrize("legacy", [False, True])
def test_weight_property_is_read_only(legacy):
    m = Model()
    x = m.bool("x")
    m &= x
    if legacy:
        with pytest.warns(FutureWarning):
            term = m.obj.add_soft(~x, 3)
    else:
        term = m.obj.add(x, weight=3)
    with pytest.raises(AttributeError):
        term.weight = 7
    assert term.weight == 3 and m.solve().cost == 3


@pytest.mark.parametrize("tiered", [False, True])
def test_update_rejects_foreign_handles_without_mutation(tiered):
    m = Model()
    other = Model()
    x = other.bool("x")
    objective = m.tier_obj if tiered else m.obj
    foreign_objective = other.tier_obj if tiered else other.obj
    foreign = foreign_objective.add(x, weight=3)
    with pytest.raises(ValueError, match="different objective"):
        objective.update(foreign, weight=7)
    assert foreign.weight == 3
    assert not m._soft and not m.tier_obj.is_active()


@pytest.mark.parametrize("tiered", [False, True])
def test_update_rejects_non_handles(tiered):
    m = Model()
    objective = m.tier_obj if tiered else m.obj
    with pytest.raises(TypeError, match="handle"):
        objective.update(object(), weight=7)


@pytest.mark.parametrize("tiered", [False, True])
def test_update_cannot_activate_a_handle_in_the_other_objective_mode(tiered):
    m = Model()
    x = m.bool("x")
    objective = m.tier_obj if tiered else m.obj
    other = m.obj if tiered else m.tier_obj
    term = objective.add(x, weight=0)
    other.add(x)
    with pytest.raises(ValueError, match="mutually exclusive"):
        objective.update(term, weight=7)
    assert term.weight == 0
