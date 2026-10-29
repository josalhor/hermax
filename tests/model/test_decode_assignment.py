import pytest

from hermax.model import Model


def test_decode_assignment_rejects_contradictory_raw_model():
    model = Model()

    with pytest.raises(ValueError, match="contradictory"):
        model.decode_model([1, -1])


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_decode_bool_literals_from_raw_model_respects_polarity():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    dec = m.decode_model([a.id, -b.id])
    assert dec[a] is True
    assert dec[~a] is False
    assert dec[b] is False
    assert dec[~b] is True


def test_decode_boolvector_from_raw_model():
    m = Model()
    v = m.bool_vector("v", length=3)

    dec = m.decode_model([v[0].id, -v[1].id, v[2].id])
    assert dec[v] == [True, False, True]


def test_decode_plain_list_and_tuple_of_supported_targets_recursively():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    iv = m.int_vector("iv", length=2, lb=0, ub=4)
    raw = [a.id, -b.id, (iv[0] == 1).id, (iv[1] == 3).id]

    dec = m.decode_model(raw)
    assert dec[[a, ~b]] == [True, True]
    assert dec[(a, b)] == (True, False)
    assert dec[[iv, [a, b], (~a, ~b)]] == [[1, 3], [True, False], (False, True)]


def test_decode_enum_from_raw_model_selected_choice():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=True)

    green = color._choice_lits["green"]
    red = color._choice_lits["red"]
    blue = color._choice_lits["blue"]
    dec = m.decode_model([green.id, -red.id, -blue.id])
    assert dec[color] == "green"


def test_decode_enum_returns_none_when_no_choice_true():
    m = Model()
    color = m.enum("color", choices=["red", "green"], nullable=True)
    dec = m.decode_model([-color._choice_lits["red"].id, -color._choice_lits["green"].id])
    assert dec[color] is None


def test_decode_int_prefers_exact_equality_literal_when_present():
    m = Model()
    speed = m.int("speed", lb=0, ub=5)

    eq2 = speed == 2
    # Give contradictory threshold hints on purpose; equality literal should win.
    raw = [eq2.id] + [lit.id for lit in speed._threshold_lits]
    dec = m.decode_model(raw)
    assert dec[speed] == 2


def test_decode_int_fallback_uses_threshold_prefix_count():
    m = Model()
    speed = m.int("speed", lb=0, ub=5)  # compact thresholds count = 4
    ts = speed._threshold_lits

    # Prefix true count = 3 => decoded value = lb + 3 = 3
    dec = m.decode_model([ts[0].id, ts[1].id, ts[2].id, -ts[3].id])
    assert dec[speed] == 3


def test_decode_int_fallback_clamps_if_all_thresholds_true():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)  # valid values 0..4
    raw = [lit.id for lit in speed._threshold_lits]
    dec = m.decode_model(raw)
    # Invalid raw assignment is clamped by current decode implementation.
    assert dec[speed] == 4


def test_decode_intvector_enumvector_and_intmatrix_shapes():
    m = Model()
    iv = m.int_vector("iv", length=2, lb=0, ub=4)
    ev = m.enum_vector("ev", length=2, choices=["r", "g"], nullable=True)
    mat = m.int_matrix("mat", rows=2, cols=2, lb=0, ub=3)

    raw = []
    # int vector values via equality literals
    raw.append((iv[0] == 1).id)
    raw.append((iv[1] == 3).id)
    # enum vector values
    raw.append(ev[0]._choice_lits["g"].id)
    raw.append(ev[1]._choice_lits["r"].id)
    # matrix values through threshold prefixes (0,1 / 2,0)
    m00, m01 = mat._grid[0][0], mat._grid[0][1]
    m10, m11 = mat._grid[1][0], mat._grid[1][1]
    raw.extend([-lit.id for lit in m00._threshold_lits])  # 0
    raw.extend([m01._threshold_lits[0].id, -m01._threshold_lits[1].id])  # 1
    raw.extend([lit.id for lit in m10._threshold_lits[:2]])  # 2 (all thresholds true for ub=3)
    raw.extend([-lit.id for lit in m11._threshold_lits])  # 0

    dec = m.decode_model(raw)
    assert dec[iv] == [1, 3]
    assert dec[ev] == ["g", "r"]
    assert dec[mat] == [[0, 1], [2, 0]]


def test_decode_unknown_or_unassigned_bool_defaults_false():
    m = Model()
    a = m.bool("a")
    dec = m.decode_model([])
    assert dec[a] is False
    assert dec[~a] is True


def test_assignment_view_raw_is_copied_and_getitem_delegates_to_val():
    m = Model()
    a = m.bool("a")
    dec = m.decode_model([a.id])
    raw = dec.raw
    raw.append(999999)

    assert dec.raw == [a.id]
    assert dec[a] is dec.val(a) is True


def test_decode_end_to_end_with_model_solve_on_mixed_types():
    m = Model()
    a = m.bool("a")
    color = m.enum("color", choices=["red", "green"], nullable=False)
    speed = m.int("speed", lb=0, ub=4)
    bv = m.bool_vector("bv", length=2)

    # Pin a satisfiable assignment using literals produced by the model layer.
    m &= a
    m &= (color == "green")
    m &= (speed == 2)
    m &= bv[0]
    m &= ~bv[1]

    r = _solve_ok(m)
    assert r[a] is True
    assert r[color] == "green"
    assert r[speed] == 2
    assert r[bv] == [True, False]


def test_decode_lazy_scale_expr_uses_solved_value_without_realizing():
    m = Model()
    x = m.int("x", lb=0, ub=5)
    y = x.scale(2)
    m &= (x == 3)

    hard_before = len(m._hard)
    r = _solve_ok(m)

    assert r[y] == 6
    assert len(m._hard) == hard_before


def test_decode_lazy_floor_div_expr_uses_solved_value_without_realizing():
    m = Model()
    x = m.int("x", lb=0, ub=11)
    q = x // 3
    m &= (x == 10)

    hard_before = len(m._hard)
    r = _solve_ok(m)

    assert r[q] == 3
    assert len(m._hard) == hard_before


def test_decode_lazy_max_expr_uses_solved_values_without_realizing():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=9)
    mx = xs.max()
    mn = xs.min()
    ubv = xs.upper_bound()
    lbv = xs.lower_bound()
    m &= (xs[0] == 2)
    m &= (xs[1] == 7)
    m &= (xs[2] == 4)

    hard_before = len(m._hard)
    r = _solve_ok(m)

    assert r[mx] == 7
    assert r[mn] == 2
    assert r[ubv] == 7
    assert r[lbv] == 2
    assert len(m._hard) == hard_before


def test_decode_multiplexer_int_uses_solved_index_without_realizing():
    m = Model()
    idx = m.int("idx", lb=0, ub=2)
    pick = [10, 20, 30] @ idx
    m &= (idx == 1)

    hard_before = len(m._hard)
    r = _solve_ok(m)

    assert r[pick] == 20
    assert len(m._hard) == hard_before



def test_decode_vector_element_int_uses_solved_index_without_realizing():
    m = Model()
    vals = m.int_vector("v", length=3, lb=0, ub=9)
    idx = m.int("idx", lb=0, ub=2)
    el = vals[idx]
    m &= (vals[0] == 2)
    m &= (vals[1] == 5)
    m &= (vals[2] == 8)
    m &= (idx == 2)

    hard_before = len(m._hard)
    r = _solve_ok(m)

    assert r[el] == 8
    assert len(m._hard) == hard_before


def test_decode_rejects_unsupported_target_type():
    m = Model()
    dec = m.decode_model([])
    with pytest.raises(TypeError, match="Unsupported decode target"):
        dec[object()]


@pytest.mark.parametrize("value", range(-2, 4))
def test_decode_integer_comparisons_created_after_solve(value):
    m = Model()
    x = m.int("x", -2, 3)
    m &= x >= value
    m &= x <= value
    result = _solve_ok(m)
    hard_before = len(m._hard)

    for candidate in range(-2, 4):
        assert result[x == candidate] is (value == candidate)
        assert result[x != candidate] is (value != candidate)
    assert len(m._hard) == hard_before


@pytest.mark.parametrize("bounds", [(4, 4), (4, 5)])
def test_decode_unmentioned_small_integer_comparisons_after_solve(bounds):
    m = Model()
    x = m.int("x", *bounds)
    result = _solve_ok(m)
    value = result[x]
    assert result[x == value] is True
    assert result[x != value] is False
    assert result[x >= x.lb] is True
    assert result[x < x.lb] is False


def test_decode_late_equality_uses_the_saved_assignment():
    m = Model()
    x = m.int("x", 0, 5)
    m &= x >= 2
    m &= x <= 4
    first = _solve_ok(m)
    value = first[x]
    equality = x == value
    m &= ~equality
    second = _solve_ok(m)

    assert first[equality] is True
    assert second[equality] is False
    assert first[x] == value
    assert second[x] != value


@pytest.mark.parametrize("kind,chosen", [("upper_bound", 9), ("lower_bound", 3)])
def test_decode_materialized_one_sided_bound_uses_its_actual_value(kind, chosen):
    m = Model()
    xs = m.int_vector("x", 2, 0, 10)
    m &= xs[0] == 7
    m &= xs[1] == 7
    bound = getattr(xs, kind)()
    m &= bound == chosen
    result = _solve_ok(m)
    before = m._next_id, len(m._hard)

    assert result[bound] == chosen
    assert result[bound] == result[bound._realized]
    assert (m._next_id, len(m._hard)) == before


@pytest.mark.parametrize("kind,chosen", [("upper_bound", 9), ("lower_bound", 3)])
def test_saved_bound_decoding_is_unchanged_by_later_materialization(kind, chosen):
    m = Model()
    xs = m.int_vector("x", 2, 0, 10)
    m &= xs[0] == 7
    m &= xs[1] == 7
    bound = getattr(xs, kind)()
    first = _solve_ok(m)
    assert first[bound] == 7

    m &= bound == chosen
    second = _solve_ok(m)
    assert second[bound] == chosen
    assert first[bound] == 7


@pytest.mark.parametrize("kind", ["range", "membership"])
@pytest.mark.parametrize("value", range(6))
def test_late_predicates_decode_without_posting_or_solving(kind, value):
    m = Model()
    x = m.int("x", 0, 5)
    selected = m.int_set("selected", values=[1, 3, 5])
    m &= selected.contains(3)
    m &= ~selected.contains(1)
    m &= ~selected.contains(5)
    m &= x >= value
    m &= x <= value
    first = _solve_ok(m)
    predicate = x.in_range(2, 4) if kind == "range" else selected.contains(x)
    expected = 2 <= value <= 4 if kind == "range" else value == 3
    before = m._next_id, len(m._hard)

    assert first[predicate] is expected
    assert first[~predicate] is not expected
    assert (m._next_id, len(m._hard)) == before
    second = _solve_ok(m)
    assert second[predicate] is expected
    assert first[predicate] is expected


@pytest.mark.parametrize("kind", ["floor_div", "modulo", "scale", "max", "min", "sum", "card", "union"])
def test_new_materialized_variables_cannot_silently_decode_from_an_older_result(kind):
    m = Model()
    x, y = m.int("x", 0, 10), m.int("y", 0, 10)
    selected = m.int_set("selected", values=[1, 3])
    other = m.int_set("other", values=[1, 3])
    m &= x == 8
    m &= y == 3
    m &= selected == {1}
    m &= other == {3}
    result = _solve_ok(m)
    target = {
        "floor_div": lambda: m.floor_div(x, 3),
        "modulo": lambda: m.modulo(x, 3),
        "scale": lambda: m.scale(y, -1),
        "max": lambda: m.max([x, y]),
        "min": lambda: m.min([x, y]),
        "sum": lambda: m.sum_var([x, y]),
        "card": selected.card,
        "union": lambda: selected | other,
    }[kind]()
    with pytest.raises(ValueError, match="created after"):
        result[target]
    assert result[[x // 3, x % 3, y.scale(-1), x + y]] == [2, 2, -3, 11]


def test_new_boolean_variable_cannot_decode_from_an_older_result():
    m = Model()
    x = m.bool("x")
    m &= x
    result = _solve_ok(m)
    new = m.bool("new")
    with pytest.raises(ValueError, match="created after"):
        result[new]
    assert result[m.as_int(x)] == 1
    assert result[m.as_int(7)] == 7


def test_new_variable_cannot_decode_an_old_backend_auxiliary_with_the_same_id():
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    m &= ~a
    m &= ~b
    with pytest.warns(FutureWarning):
        m.obj.add_soft(a | b, 5)
    result = m.solve(backend="maxsat")
    assert result.ok and result.cost == 5
    m.close_incremental()
    new = m.bool("new")
    with pytest.raises(ValueError, match="created after"):
        result[new]


def test_late_equality_cannot_use_an_old_backend_auxiliary_as_a_decode_hint():
    m = Model()
    x = m.int("x", 0, 4)
    a, b = m.bool("a"), m.bool("b")
    m &= x >= 1
    m &= x <= 3
    m &= ~a
    m &= ~b
    with pytest.warns(FutureWarning):
        m.obj.add_soft(a | b, 5)
    first = m.solve(backend="maxsat")
    value = first[x]
    m.close_incremental()
    equality = x == value
    assert first[x] == value
    assert first[equality] is True
    assert first[~equality] is False
    m &= ~equality
    second = m.solve()
    assert second.ok and second[x] != value
    assert first[x] == value and first[equality] is True
    assert second[equality] is False
