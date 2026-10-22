"""Full reification of integer comparisons, including constant results."""

import itertools
import operator

import pytest

from hermax.model import Model


@pytest.mark.parametrize("domains", [((0, 3), (0, 3)), ((-2, 1), (0, 2)),
                                  ((0, 1), (3, 4)), ((1, 1), (1, 1))])
@pytest.mark.parametrize("negated", [False, True])
def test_int_disequality_iff_truth_table(domains, negated):
    (lo_x, hi_x), (lo_y, hi_y) = domains
    for xv, yv, bv in itertools.product(range(lo_x, hi_x + 1), range(lo_y, hi_y + 1), (False, True)):
        m = Model()
        x, y = m.int("x", lo_x, hi_x), m.int("y", lo_y, hi_y)
        b = m.bool("b")
        top = m._next_id
        relation = x != y
        reified = relation.iff(~b if negated else b)
        assert m._next_id == top
        m &= reified
        m &= x == xv
        m &= y == yv
        m &= b if bv else ~b
        assert m.solve().ok is ((not bv if negated else bv) == (xv != yv))


@pytest.mark.parametrize("op", [operator.eq, operator.ne], ids=["eq", "ne"])
@pytest.mark.parametrize("value", [-1, 7])
def test_out_of_domain_comparison_iff(op, value):
    for xv, bv in itertools.product(range(4), (False, True)):
        m = Model()
        x, b = m.int("x", 0, 3), m.bool("b")
        top = m._next_id
        relation = op(x, value)
        constraint = relation.iff(b)
        assert m._next_id == top
        assert m._const_lits == {}
        m &= constraint
        assert m._next_id == top
        assert m._const_lits == {}
        m &= x == xv
        m &= b if bv else ~b
        assert m.solve().ok is (bv == op(xv, value))


@pytest.mark.parametrize("kind", ["disequality", "constant"])
def test_int_comparison_iff_validates_indicator(kind):
    m = Model()
    x, y = m.int("x", 0, 2), m.int("y", 0, 2)
    relation = x != y if kind == "disequality" else x == 7
    top = m._next_id
    with pytest.raises(TypeError):
        relation.iff(1)
    with pytest.raises(ValueError, match="different models"):
        relation.iff(Model().bool("other"))
    assert m._next_id == top


def test_int_disequality_self_and_incremental_solving():
    m = Model()
    x, b = m.int("x", 0, 2), m.bool("b")
    m &= (x != x).iff(b)
    assert m.solve().ok
    m &= b
    assert m.solve().status == "unsat"


@pytest.mark.parametrize("negated", [False, True])
def test_literal_comparison_with_int_disequality(negated):
    for xv, yv, bv in itertools.product(range(2), range(2), (False, True)):
        m = Model()
        x, y, b = m.int("x", 0, 1), m.int("y", 0, 1), m.bool("b")
        m &= (b != (x != y)) if negated else (b == (x != y))
        m &= x == xv
        m &= y == yv
        m &= b if bv else ~b
        assert m.solve().ok is ((bv != (xv != yv)) if negated else (bv == (xv != yv)))


@pytest.mark.parametrize("op", [operator.eq, operator.ne, operator.le])
@pytest.mark.parametrize("pending", [False, True])
def test_mutated_integer_relation_rejects_reification(op, pending):
    m = Model()
    x, y, b, extra = m.int("x", 0, 2), m.int("y", 0, 2), m.bool("b"), m.bool("extra")
    relation = op(x, y)
    connected = relation.iff(b) if pending else None
    relation.extend(extra, inplace=True)
    with pytest.raises(TypeError, match="in-place extension"):
        m &= connected if pending else relation.iff(b)
