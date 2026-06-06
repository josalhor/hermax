from __future__ import annotations

from hermax.model import Model


def test_intset_contains_intvar_edge_branches():
    m = Model()
    s = m.int_set("s", lb=5, ub=6)
    x = m.int("x", lb=0, ub=3)
    b0 = s.contains(x)
    assert b0 is m._get_bool_constant_literal(False)

    m2 = Model()
    s2 = m2.int_set("s2", lb=2, ub=4)
    x2 = m2.int("x2", lb=2, ub=2)  # singleton domain value 2
    b1 = s2.contains(x2)
    assert b1 is (x2 == 2)
    assert s2.contains(x2) is b1
