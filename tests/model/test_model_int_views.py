import itertools

import pytest

from hermax.model import IntVar, Model


def test_as_int_reuses_bits_and_preserves_ownership():
    m = Model()
    x = m.int("x", 2, 3)
    b = x >= 3
    _ = x == 3
    owners = dict(m._intvar_threshold_owner_by_litid)
    eq_owners = dict(m._intvar_eq_owner_by_litid)
    next_id, hard = m._next_id, len(m._hard)
    positive, negative = m.as_int(b), m.as_int(~b)
    assert isinstance(positive, IntVar)
    assert positive._threshold_lits[0] is b
    assert negative._threshold_lits[0].id == b.id
    assert not negative._threshold_lits[0].polarity
    assert m.as_int(b)._threshold_lits[0] is b
    assert m.as_int(~b)._threshold_lits[0] is ~b
    assert m.as_int(x) is x
    assert m.as_int(True).lb == m.as_int(True).ub == 1
    assert m.as_int(False).lb == m.as_int(False).ub == 0
    for value in (-7, 0, 7):
        constant = m.as_int(value)
        assert constant.lb == constant.ub == value
        assert constant._threshold_lits == []
    assert (positive == 1) is b
    assert (negative == 0) is b
    assert (positive == 0) is ~b
    assert (negative == 1) is ~b
    assert m._next_id == next_id
    assert len(m._hard) == hard
    assert m._intvar_threshold_owner_by_litid == owners
    assert m._intvar_eq_owner_by_litid == eq_owners


@pytest.mark.parametrize("bv,xv", itertools.product((False, True), range(4)))
def test_mixed_all_different(bv, xv):
    m = Model()
    b = m.bool("b")
    x = m.int("x", 0, 3)
    m &= m.vector([x, m.as_int(~b), m.as_int(3)]).all_different()
    m &= b if bv else ~b
    m &= x == xv
    result = m.solve()
    assert (result.status == "sat") == (len({xv, int(not bv), 3}) == 3)
    if result.status == "sat":
        assert result.assignment[m.as_int(~b)] == int(not bv)


@pytest.mark.parametrize("bv,offset", itertools.product((False, True), (0, 1)))
def test_view_arithmetic_preserves_original_integer(bv, offset):
    m = Model()
    x = m.int("x", 2, 3)
    b = x >= 3
    v = m.as_int(~b)
    _ = v == 0
    _ = v == 1
    m &= b if bv else ~b
    m &= x + v == 3 + offset
    m &= m.max(m.vector([v, m.as_int(0)])) == int(not bv)
    assert (m.solve().status == "sat") == (offset == 0)


def test_conversion_validation():
    m = Model()
    other = Model()
    for value in (other.bool("b"), other.int("x", 0, 1)):
        with pytest.raises(ValueError):
            m.as_int(value)
    for value in (1.5, "1", None):
        with pytest.raises(TypeError):
            m.as_int(value)


@pytest.mark.parametrize("bv,cv,offset", itertools.product((False, True), (False, True), (0, 1)))
def test_boolean_views_in_arithmetic_and_tables(bv, cv, offset):
    m = Model()
    b, c = m.bool("b"), m.bool("c")
    v, w = m.as_int(~b), m.as_int(c)
    m &= b if bv else ~b
    m &= c if cv else ~c
    m &= 2 * v + w == 2 * int(not bv) + int(cv) + offset
    m &= m.table([v, w], allowed=[(int(not bv), int(cv))])
    assert (m.solve().status == "sat") == (offset == 0)
    assert not m._intvar_threshold_owner_by_litid
    assert not m._intvar_eq_owner_by_litid
