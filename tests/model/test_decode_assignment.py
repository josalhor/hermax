import pytest

from hermax.model import Model


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
    speed = m.int("speed", lb=0, ub=4)  # valid values 0..3
    raw = [lit.id for lit in speed._threshold_lits]
    dec = m.decode_model(raw)
    # Invalid raw assignment is clamped by current decode implementation.
    assert dec[speed] == 3


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


def test_decode_rejects_unsupported_target_type():
    m = Model()
    dec = m.decode_model([])
    with pytest.raises(TypeError, match="Unsupported decode target"):
        dec[object()]
