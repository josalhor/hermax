import pytest

from hermax.model import Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok
    return r


def test_bool_named_and_anonymous_variables_register_uniquely():
    m = Model()
    a = m.bool("a")
    b = m.bool()
    c = m.bool()

    assert a.name == "a"
    assert b.name != c.name
    assert b.id != c.id
    assert a.id == 1
    assert b.id == 2
    assert c.id == 3
    m &= (a | b | c)
    r = _solve_ok(m)
    assert r[a] or r[b] or r[c]


def test_duplicate_variable_name_rejected():
    m = Model()
    m.bool("x")
    with pytest.raises(ValueError, match="already registered"):
        m.bool("x")


def test_container_name_collision_with_existing_var_rejected():
    m = Model()
    grid = m.bool("grid")
    m &= grid
    r = _solve_ok(m)
    assert r[grid] is True
    with pytest.raises(ValueError, match="already registered"):
        m.int_matrix("grid", rows=2, cols=2, lb=0, ub=3)


def test_variable_name_collision_with_existing_container_rejected():
    m = Model()
    v = m.bool_vector("v", length=3)
    m &= (v[0] | v[1] | v[2])
    r = _solve_ok(m)
    assert any(r[x] for x in v)
    with pytest.raises(ValueError, match="already registered"):
        m.bool("v")


def test_container_name_collision_with_existing_container_rejected():
    m = Model()
    v = m.int_vector("v", length=2, lb=0, ub=3)
    # Use generated comparison literals so decode path is exercised after solve.
    m &= (v[0] <= 1)
    m &= (v[1] >= 0)
    _solve_ok(m)
    with pytest.raises(ValueError, match="already registered"):
        m.enum_vector("v", length=2, choices=["A", "B"])


def test_cross_model_pollution_banned_for_or_and_pb_and_modifiers():
    m1 = Model()
    m2 = Model()
    a = m1.bool("a")
    b = m2.bool("b")

    with pytest.raises(ValueError, match="different models"):
        _ = a | b

    with pytest.raises(ValueError, match="different models"):
        _ = a + b

    with pytest.raises(ValueError, match="different models"):
        _ = (a | a).only_if(b)

    with pytest.raises(ValueError, match="different models"):
        _ = a.implies(b)


def test_cross_model_pollution_banned_for_pb_comparisons():
    m1 = Model()
    m2 = Model()
    a = m1.bool("a")
    b = m2.bool("b")

    with pytest.raises(ValueError, match="different models"):
        _ = (a + a) <= (b + b)


def test_auxiliary_variables_generated_by_encoders_do_not_break_future_user_ids():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # Force encoder-generated auxiliary variables.
    m &= (a + b + c <= 1)

    x = m.bool("x")
    assert x.id >= 4

    # Also ensure a future anonymous var still gets a unique id and name.
    y = m.bool()
    assert y.id > x.id
    assert y.name != x.name
    m &= x
    r = _solve_ok(m)
    assert r[x] is True


def test_registry_integrity_survives_multiple_encoder_calls():
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(6)]

    m &= (xs[0] + xs[1] + xs[2] <= 1)
    m &= (2 * xs[3] + 3 * xs[4] + xs[5] >= 2)
    m &= (xs[0] + xs[5] == 1)

    z = m.bool("z")
    assert isinstance(z.id, int)
    assert z.id > 0
    m &= z
    r = _solve_ok(m)
    assert r[z] is True
