import pytest

from hermax.model import Model


@pytest.mark.parametrize("route", ["sat", "maxsat", "incremental", "stratified"])
def test_solve_routes_decode_unreferenced_definitions_consistently(route):
    m = Model()
    x = m.int("x", 0, 5)
    flag = m.bool("flag")
    selected = m.int_set("selected", values=[1])
    other = m.int_set("other", values=[2])
    quotient = m.floor_div(x, 3)
    cardinality = selected.card()
    union = selected | other
    predicate = x.in_range(3, 5)
    m &= x == 5
    m &= selected == {1}
    m &= other == {2}
    if route in {"incremental", "stratified"}:
        m.tier_obj.add(flag, tier=0)
        result = m.solve(lex_strategy=route)
    elif route == "maxsat":
        m.obj += flag
        result = m.solve()
    else:
        result = m.solve()
    assert result.ok
    assert result[[x, quotient, cardinality, union, predicate]] == [5, 1, 1, {1, 2}, True]
    assert result[[x // 3, x % 3, x.scale(-1), x + 2]] == [1, 2, -5, 7]


@pytest.mark.parametrize("route", ["sat", "maxsat", "incremental", "stratified"])
def test_decoding_nested_expressions_does_not_compile_or_change_saved_values(route):
    m = Model()
    xs = m.int_vector("xs", 2, 0, 5)
    flag = m.bool("flag")
    quotient = m.floor_div(xs[0], 3)
    expressions = [xs.max(), xs.min(), xs.upper_bound(), xs.lower_bound(),
                   (xs.max() // 2).scale(-3), xs.min() % 2]
    kwargs = {}
    if route in {"incremental", "stratified"}:
        m.tier_obj.add(flag, tier=0)
        kwargs["lex_strategy"] = route
    elif route == "maxsat":
        m.obj += flag
    first = m.solve(assumptions=[xs[0] == 5, xs[1] == 2], **kwargs)
    second = m.solve(assumptions=[xs[0] == 1, xs[1] == 4], **kwargs)
    before = (m._top_id(), len(m._hard), len(m._pending_literal_defs),
              len(m._pending_pb_constraints))
    for _ in range(2):
        assert first[[quotient, expressions]] == [1, [5, 2, 5, 2, -6, 0]]
        assert second[[quotient, expressions]] == [0, [4, 1, 4, 1, -6, 1]]
    assert (m._top_id(), len(m._hard), len(m._pending_literal_defs),
            len(m._pending_pb_constraints)) == before
    assert all(expression._realized is None for expression in expressions)


@pytest.mark.parametrize("route", ["sat", "maxsat", "incremental", "stratified"])
@pytest.mark.parametrize("coefficient", [1.5, -1.5])
def test_assumptions_reject_fractional_unit_terms(route, coefficient):
    m = Model()
    flag = m.bool("flag")
    kwargs = {}
    if route in {"incremental", "stratified"}:
        m.tier_obj.add(flag, tier=0)
        kwargs["lex_strategy"] = route
    elif route == "maxsat":
        m.obj += flag
    with pytest.raises(TypeError, match="unit term"):
        m.solve(assumptions=[coefficient * flag], **kwargs)


@pytest.mark.parametrize("kind", ["pb", "integer_relation", "table", "cumulative", "singleton_sum", "modulo"])
def test_model_boundaries_reject_foreign_objects_before_posting(kind):
    m, other = Model(), Model()
    local = m.bool("local")
    m &= ~local
    foreign = other.bool("foreign")
    x, y = other.int("x", 0, 2), other.int("y", 0, 2)
    before = m._top_id(), len(m._hard), len(m._pending_pb_constraints)
    with pytest.raises(ValueError, match="different models"):
        if kind == "pb":
            m &= 2 * foreign >= 1
        elif kind == "integer_relation":
            m &= x <= y
        elif kind == "table":
            m &= other.table([x], allowed=[[1]])
        elif kind == "cumulative":
            m &= other.cumulative([x, y], [1, 1], [1, 1], 1)
        elif kind == "singleton_sum":
            m.sum_var([x])
        else:
            m.modulo(x, 1)
    assert (m._top_id(), len(m._hard), len(m._pending_pb_constraints)) == before
    result = m.solve()
    assert result.ok and result[local] is False
