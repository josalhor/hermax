import itertools

import pytest

from hermax.model import Clause, ClauseGroup, Model


APIS = ("model", "obj", "tier")


def _add(m, api, condition, weight):
    objective = m.tier_obj if api == "tier" else m.obj
    with pytest.warns(FutureWarning):
        term = (
            m.add_soft(condition, weight)
            if api == "model"
            else objective.add_soft(condition, weight)
        )
    return objective, term


def _encoding_state(m):
    return (
        m._next_id,
        tuple(m._hard),
        tuple(m._soft),
        m._next_soft_group_id,
        len(m._pending_pb_constraints),
        dict(m.tier_obj._tiers),
    )


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("kind", ["literal", "pb"])
def test_positive_preference_weight_rounding_to_zero_is_rejected_before_encoding(api, kind):
    m = Model()
    m.set_objective_precision(decimals=2)
    flags = m.bool_vector("b", 20)
    condition = flags[0] if kind == "literal" else sum(
        (i + 1) * flag for i, flag in enumerate(flags)
    ) <= 100
    before = _encoding_state(m)
    with pytest.raises(ValueError, match="rounds to zero"):
        _add(m, api, condition, .001)
    assert _encoding_state(m) == before


@pytest.mark.parametrize("api", APIS)
def test_rounded_zero_weight_update_preserves_the_registered_preference(api):
    m = Model()
    m.set_objective_precision(decimals=2)
    flag = m.bool("flag")
    m &= ~flag
    objective, term = _add(m, api, flag, 2.5)
    before = _encoding_state(m)
    with pytest.raises(ValueError, match="rounds to zero"):
        objective.update(term, weight=.001)
    assert term.weight == 2.5
    assert _encoding_state(m) == before
    assert m.solve().cost == 2.5


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("kind", ["clause", "group", "pb", "deferred", "lookup", "cumulative"])
@pytest.mark.parametrize("satisfied", [False, True])
def test_initially_zero_compound_preference_can_be_activated(api, kind, satisfied):
    m = Model()
    flags = m.bool_vector("b", 20)
    x = m.int("x", 0, 3)
    for flag in flags:
        m &= flag if satisfied else ~flag
    m &= x == 1
    objective = m.tier_obj if api == "tier" else m.obj
    objective.add(1)
    condition = {
        "clause": lambda: flags[0] | flags[1],
        "group": lambda: ClauseGroup(m, [Clause(m, [flags[0]])]),
        "pb": lambda: sum((i + 1) * flag for i, flag in enumerate(flags)) >= 100,
        "deferred": lambda: x != 7 if satisfied else x == 7,
        "lookup": lambda: flags[x],
        "cumulative": lambda: m.cumulative([x], [2], [1], int(satisfied)),
    }[kind]()
    objective, term = _add(m, api, condition, 0)
    assert m.solve().cost == 1
    for weight in (3, 0, 5):
        objective.update(term, weight=weight)
        assert m.solve().cost == 1 + weight * (not satisfied)


@pytest.mark.parametrize("api", APIS)
def test_zero_literal_preference_does_not_realize_definitions(api):
    m = Model()
    x = m.int("x", 0, 3)
    condition = x == 1
    before = m._next_id, tuple(m._hard), tuple(m._soft)
    _add(m, api, condition, 0)
    assert (m._next_id, tuple(m._hard), tuple(m._soft)) == before


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("value", [False, True])
@pytest.mark.parametrize("incremental", [False, True])
def test_literal_preferences_can_be_enabled_disabled_and_reenabled(api, value, incremental):
    m = Model()
    flag = m.bool("flag")
    m &= flag if value else ~flag
    objective = m.tier_obj if api == "tier" else m.obj
    objective.add(1)
    objective, term = _add(m, api, flag, 0)
    for weight in (3, 0, 5, 0, 2):
        objective.update(term, weight=weight)
        assert m.solve(incremental=incremental).cost == 1 + weight * (not value)


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("value", [False, True])
def test_zero_boolean_constant_preference_can_be_activated(api, value):
    m = Model()
    objective = m.tier_obj if api == "tier" else m.obj
    objective.add(1)
    objective, term = _add(m, api, value, 0)
    for weight in (3, 0, 5):
        objective.update(term, weight=weight)
        assert m.solve().cost == 1 + weight * (not value)


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("initially_true", [False, True])
@pytest.mark.parametrize("initial_weight", [0, 1])
def test_registered_compound_preference_keeps_its_original_meaning(api, initially_true, initial_weight):
    m = Model()
    flag = m.bool("flag")
    m &= flag
    objective = m.tier_obj if api == "tier" else m.obj
    objective.add(1)
    condition = ClauseGroup(m, [] if initially_true else [Clause(m, [flag])])
    objective, term = _add(m, api, condition, initial_weight)
    condition.extend(~flag, inplace=True)
    groups_before = len(m._soft_group_to_ids)
    for weight in (0, 5):
        objective.update(term, weight=weight)
        assert m.solve().cost == 1
    assert len(m._soft_group_to_ids) == groups_before


@pytest.mark.parametrize("api", APIS)
def test_zero_compound_preference_compiles_before_its_expression_can_change(api):
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    m &= a
    m &= b
    expr = 2 * a + 3 * b
    objective, term = _add(m, api, expr <= 1, 0)
    expr.terms.clear()
    objective.update(term, weight=5)
    assert m.solve().cost == 5


@pytest.mark.parametrize("api", ["model", "obj"])
def test_zero_compound_can_be_registered_and_enabled_after_sat_solve(api):
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    m &= a
    m &= b
    assert m.solve(backend="sat").ok
    objective, term = _add(m, api, a + b <= 1, 0)
    objective.update(term, weight=5)
    assert m.solve().cost == 5


@pytest.mark.parametrize("api", ["model", "obj"])
@pytest.mark.parametrize("initial_weight", [0, 2])
def test_zero_compound_duplicate_does_not_change_an_existing_preference(api, initial_weight):
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    m &= ~a
    m &= ~b
    objective, first = _add(m, api, a | b, initial_weight)
    _, second = _add(m, api, a | b, 0)
    assert m.solve(backend="maxsat").cost == initial_weight
    for left, right in [(0, 0), (3, 0), (3, 5), (0, 5)]:
        objective.update(first, weight=left)
        objective.update(second, weight=right)
        assert m.solve().cost == left + right


@pytest.mark.parametrize("api", APIS)
@pytest.mark.parametrize("kind", ["clause", "group", "deferred"])
@pytest.mark.parametrize("initial_weight", [0, 2])
def test_always_false_compound_preferences_have_updateable_costs(api, kind, initial_weight):
    m = Model()
    condition = (
        Clause(m, []) if kind == "clause"
        else ClauseGroup(m, [Clause(m, [])]) if kind == "group"
        else m.int("x", 0, 1) == 3
    )
    objective = m.tier_obj if api == "tier" else m.obj
    objective.add(1)
    objective, term = _add(m, api, condition, initial_weight)
    assert m.solve().cost == 1 + initial_weight
    for weight in (3, 0, 7):
        objective.update(term, weight=weight)
        assert m.solve().cost == 1 + weight


@pytest.mark.parametrize("api", APIS)
def test_zero_compound_preference_supports_decimal_weight_updates(api):
    m = Model()
    m.set_objective_precision(decimals=2)
    a, b = m.bool("a"), m.bool("b")
    m &= a
    m &= b
    objective = m.tier_obj if api == "tier" else m.obj
    objective.add(1)
    objective, term = _add(m, api, a + b <= 1, 0)
    for weight in (0.25, 0, 1.5):
        objective.update(term, weight=weight)
        assert m.solve().cost == 1 + weight


@pytest.mark.parametrize("api", ["model", "obj"])
@pytest.mark.parametrize("initial_precision", [None, 2])
@pytest.mark.parametrize("source", ["numeric", "legacy"])
def test_precision_does_not_revive_cleared_weights(api, initial_precision, source):
    m = Model()
    if initial_precision is not None:
        m.set_objective_precision(decimals=initial_precision)
    flag = m.bool("flag")
    m &= flag
    if source == "numeric":
        m.obj.add(flag, weight=3)
    else:
        _add(m, api, ~flag, 3)
    m.obj.clear()
    _add(m, api, ~flag, 2)
    assert m.solve().cost == 2
    m.set_objective_precision(decimals=1)
    assert m.solve().cost == 2.0


def test_shared_preferences_keep_only_live_raw_weights_after_clear_and_updates():
    m = Model()
    m.set_objective_precision(decimals=2)
    flag = m.bool("flag")
    m &= ~flag
    m.obj.add(~flag, weight=7)
    m.obj.clear()
    objective, first = _add(m, "obj", flag, 2.35)
    _, second = _add(m, "obj", flag, 1.25)
    for left, right in itertools.product((0, 1.5), (0, 2.5)):
        objective.update(first, weight=left)
        objective.update(second, weight=right)
        assert sum(w for w, _ in m._soft) == round(100 * (left + right))
    m.set_objective_precision(decimals=1)
    assert m.solve().cost == 4.0


def test_reused_soft_unit_precision_change_reaches_the_incremental_solver():
    m = Model()
    flag = m.bool("flag")
    m &= flag
    m.obj.add(flag, weight=7)
    assert m.solve(backend="maxsat").cost == 7
    m.obj.clear()
    _add(m, "obj", ~flag, 2)
    assert m.solve(backend="maxsat").cost == 2
    m.set_objective_precision(decimals=1)
    assert m.solve(backend="maxsat").cost == 2.0


@pytest.mark.parametrize("precision", [None, 2])
@pytest.mark.parametrize("literal_value", [False, True])
@pytest.mark.parametrize("condition_kind", ["literal", "true", "false"])
def test_zero_preference_can_be_activated_after_sat_solve(
    precision, literal_value, condition_kind
):
    m = Model()
    if precision is not None:
        m.set_objective_precision(decimals=precision)
    flag = m.bool("flag")
    m &= flag if literal_value else ~flag
    condition = flag if condition_kind == "literal" else condition_kind == "true"
    objective, term = _add(m, "obj", condition, 0)
    assert m.solve(backend="sat", incremental=True).ok

    objective.update(term, weight=5)

    assert term.weight == 5
    satisfied = literal_value if condition_kind == "literal" else condition_kind == "true"
    assert (m.solve().cost or 0) == (0 if satisfied else 5)
