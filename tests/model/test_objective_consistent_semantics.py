import pytest

from hermax.model import Model, Clause, ClauseGroup


STYLES = ["assign", "replace", "set", "add", "iadd", "weighted", "tier", "lex"]


def install(m, style, expression, weight=1):
    weighted = expression if weight == 1 else weight * expression
    if style == "assign":
        m.obj = weighted
    elif style == "replace":
        m.obj.replace_with(weighted)
    elif style == "set":
        m.obj.set(expression, weight=weight)
    elif style == "add":
        m.obj.add(expression, weight=weight)
    elif style == "iadd":
        m.obj += weighted
    elif style == "weighted":
        m.obj += weighted
    elif style == "tier":
        m.tier_obj.add(expression, weight=weight, tier=0)
    else:
        m.tier_obj.set_lexicographic(weighted)


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize(
    "form", ["literal", "term", "sum", "as_int", "negative", "negated"]
)
def test_numeric_forms_have_identical_direction_and_exact_cost(style, form):
    for value in (False, True):
        m = Model()
        x = m.bool("x")
        m &= x if value else ~x
        expr = {
            "literal": lambda: x,
            "term": lambda: 1 * x,
            "sum": lambda: x + 0,
            "as_int": lambda: m.as_int(x),
            "negative": lambda: -2 * x + 3,
            "negated": lambda: ~x,
        }[form]()
        # Bare literals must reach every entry point without an implicit cast.
        install(m, style, expr)
        result = m.solve()
        expected = (
            3 - 2 * value
            if form == "negative"
            else not value
            if form == "negated"
            else value
        )
        assert result.ok and result.cost == expected


@pytest.mark.parametrize("style", STYLES)
def test_numeric_literals_prefer_false(style):
    m = Model()
    x = m.bool("x")
    if style in ("assign", "replace", "iadd", "lex"):
        if style == "assign":
            m.obj = x
        elif style == "replace":
            m.obj.replace_with(x)
        elif style == "iadd":
            m.obj += x
        else:
            m.tier_obj.set_lexicographic(x)
    else:
        install(m, style, x, 3)
    result = m.solve()
    assert result.ok and result[x] is False and result.cost == 0


@pytest.mark.parametrize(
    "style", ["iadd", "weighted", "set", "add", "assign", "replace", "tier", "lex"]
)
@pytest.mark.parametrize("kind", ["clause", "group", "pb"])
def test_numeric_objectives_reject_constraints_without_adding_softs(style, kind):
    m = Model()
    x = m.bool("x")
    y = m.bool("y")
    expression = (
        x | y
        if kind == "clause"
        else ClauseGroup(m, [Clause(m, [x]), Clause(m, [y])])
        if kind == "group"
        else x + y <= 1
    )
    # Do not multiply a constraint: reject at the objective API itself.
    with pytest.raises(TypeError, match="numeric|reif"):
        if style == "assign":
            m.obj = expression
        elif style == "replace":
            m.obj.replace_with(expression)
        elif style == "iadd":
            m.obj += expression
        elif style == "lex":
            m.tier_obj.set_lexicographic(expression)
        else:
            install(m, style, expression)
    assert not any(w for w, _ in m._soft)
    assert not m.tier_obj.is_active()


@pytest.mark.parametrize("api", ["model", "obj", "tier"])
def test_explicit_soft_preferences_keep_satisfaction_direction(api):
    m = Model()
    x = m.bool("x")
    if api == "tier":
        m.tier_obj.add_soft(x, 3, tier=0)
    elif api == "model":
        m.add_soft(x, 3)
    else:
        m.obj.add_soft(x, 3)
    result = m.solve()
    assert result.ok and result[x] is True and result.cost == 0


@pytest.mark.parametrize("api", ["model", "obj", "tier"])
@pytest.mark.parametrize("kind", ["integer", "expression", "term"])
def test_soft_apis_reject_numeric_costs(api, kind):
    m = Model()
    x = m.int("x", 0, 3)
    b = m.bool("b")
    expr = x if kind == "integer" else b + 2 if kind == "expression" else 2 * b
    with pytest.raises(TypeError, match="numeric"):
        if api == "model":
            m.add_soft(expr, 3)
        elif api == "obj":
            m.obj.add_soft(expr, 3)
        else:
            m.tier_obj.add_soft(expr, 3, tier=0)


@pytest.mark.parametrize("method", ["assign", "set", "replace"])
def test_replacement_clears_all_previous_terms_and_invalidates_handles(method):
    m = Model()
    x, y = m.bool("x"), m.bool("y")
    ref = m.obj.add_soft(x, 100)
    m.obj.add(-2 * y + 7)
    if method == "assign":
        m.obj = x + 3
    elif method == "replace":
        m.obj.replace_with(x + 3)
    else:
        m.obj.set(x + 3)
    result = m.solve()
    assert result[x] is False and result.cost == 3
    with pytest.raises(ValueError):
        m.obj.update_soft(ref, 200)


@pytest.mark.parametrize("api", ["flat", "tier"])
def test_decimal_weight_is_scaled_exactly_once(api):
    m = Model()
    m.set_objective_precision(decimals=2)
    x = m.bool("x")
    m &= x
    if api == "flat":
        m.obj += 1.25 * x
    else:
        m.tier_obj.add(x, weight=1.25, tier=0)
    assert m.solve().cost == 1.25


def test_paper_objective_replacement_and_assumptions():
    m = Model()
    xs = m.bool_vector("edge", 3)
    m &= xs.exactly_one()
    weights = [1, 3, 5]

    def cost():
        return sum(w * x for w, x in zip(weights, xs))

    m.obj = cost()
    assert m.solve().cost == 1
    assert m.solve(assumptions=[xs[1]]).cost == 3
    weights[0] = 999
    m.obj.set(cost())
    result = m.solve()
    assert result.cost == 3 and result[xs[0]] is False


@pytest.mark.parametrize("tiered", [False, True])
def test_objective_does_not_expose_soft_namespace(tiered):
    m = Model()
    objective = m.tier_obj if tiered else m.obj
    assert not hasattr(objective, "soft")


@pytest.mark.parametrize("tiered", [False, True])
def test_explicit_soft_preferences_reject_numeric_cost(tiered):
    m = Model()
    x = m.int("x", 0, 3)
    with pytest.raises(TypeError, match="numeric"):
        if tiered:
            m.tier_obj.add_soft(x, 3, tier=0)
        else:
            m.obj.add_soft(x, 3)


def test_explicit_soft_preference_handles_support_weight_updates():
    m = Model()
    x = m.bool("x")
    m &= ~x
    ref = m.obj.add_soft(x, weight=3)
    assert m.solve().cost == 3
    m.obj.update_soft(ref, 5)
    assert m.solve().cost == 5


@pytest.mark.parametrize("style", STYLES)
def test_large_integer_weights_remain_exact(style):
    m = Model()
    x = m.bool("x")
    m &= x
    weight = 2**55 + 7
    install(m, style, x, weight)
    assert m.solve().cost == weight
