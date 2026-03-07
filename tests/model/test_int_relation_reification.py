from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
from hermax.model import Model


def _cmp(a: int, op: str, b: int) -> bool:
    if op == "<=":
        return a <= b
    if op == "<":
        return a < b
    if op == ">=":
        return a >= b
    if op == ">":
        return a > b
    raise ValueError(op)


@pytest.mark.parametrize("op", ["<=", "<", ">=", ">"])
def test_bool_full_reification_of_int_relations_pointwise(op: str):
    xdom = range(0, 4)
    ydom = range(0, 4)
    for xv, yv, bv in itertools.product(xdom, ydom, [False, True]):
        m = Model()
        x = m.int("x", 0, 4)
        y = m.int("y", 0, 4)
        b = m.bool("b")

        rel = {
            "<=": (x <= y),
            "<": (x < y),
            ">=": (x >= y),
            ">": (x > y),
        }[op]
        m &= (b == rel)
        m &= (x == xv)
        m &= (y == yv)
        m &= (b if bv else ~b)
        r = m.solve()
        expected = (bv == _cmp(xv, op, yv))
        assert (r.ok if expected else r.status == "unsat"), (op, xv, yv, bv)


def test_bool_full_reification_of_int_equality_pointwise():
    xdom = range(0, 4)
    ydom = range(0, 4)
    for xv, yv, bv in itertools.product(xdom, ydom, [False, True]):
        m = Model()
        x = m.int("x", 0, 4)
        y = m.int("y", 0, 4)
        b = m.bool("b")

        m &= (b == (x == y))
        m &= (x == xv)
        m &= (y == yv)
        m &= (b if bv else ~b)
        r = m.solve()
        expected = (bv == (xv == yv))
        assert (r.ok if expected else r.status == "unsat"), (xv, yv, bv)


def test_bool_reification_of_int_relations_bypasses_pb_and_card(monkeypatch):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for b == (x <= y)")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for b == (x <= y)")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    b = m.bool("b")
    top_before = m._top_id()
    m &= (b == (x <= y))
    assert m._top_id() == top_before
    m &= (x == 3)
    m &= (y == 7)
    m &= b
    r = m.solve()
    assert r.ok


def test_bool_reification_of_int_equality_bypasses_pb_and_card(monkeypatch):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for b == (x == y)")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for b == (x == y)")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    b = m.bool("b")
    top_before = m._top_id()
    m &= (b == (x == y))
    assert m._top_id() == top_before
    m &= (x == 7)
    m &= (y == 7)
    m &= b
    r = m.solve()
    assert r.ok
