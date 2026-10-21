"""Full reification of Boolean and pseudo-Boolean formulas."""

import itertools
import operator

import pytest

from hermax.model import Clause, Model


OPS = [operator.le, operator.lt, operator.ge, operator.gt, operator.eq, operator.ne]


@pytest.mark.parametrize("kind", ["literal", "clause", "empty", "tautology"])
@pytest.mark.parametrize("negated_indicator", [False, True])
def test_boolean_iff_truth_table(kind, negated_indicator):
    for av, bv, fv in itertools.product((False, True), repeat=3):
        m = Model()
        a, b, flag = (m.bool(name) for name in ("a", "b", "flag"))
        formula = {"literal": ~a, "clause": a | ~b,
                   "empty": Clause(m, []), "tautology": a | ~a}[kind]
        expected = {"literal": not av, "clause": av or not bv,
                    "empty": False, "tautology": True}[kind]
        top = m._next_id
        m &= formula.iff(~flag if negated_indicator else flag)
        assert m._next_id == top
        m &= a if av else ~a
        m &= b if bv else ~b
        m &= flag if fv else ~flag
        assert m.solve().ok is ((not fv if negated_indicator else fv) == expected)


@pytest.mark.parametrize("op", OPS, ids=lambda op: op.__name__)
@pytest.mark.parametrize("gated", [False, True])
def test_pb_iff_truth_table(op, gated):
    for av, bv, gv, fv in itertools.product((False, True), repeat=4):
        m = Model()
        a, b, gate, flag = (m.bool(name) for name in ("a", "b", "gate", "flag"))
        comparison = op(2 * a - b, 1)
        formula = comparison.only_if(gate) if gated else comparison
        top = m._next_id
        reified = formula.iff(flag)
        assert m._next_id == top
        assert not m._hard
        m &= reified
        for lit, value in ((a, av), (b, bv), (gate, gv), (flag, fv)):
            m &= lit if value else ~lit
        expected = op(2 * int(av) - int(bv), 1)
        if gated:
            expected = not gv or expected
        assert m.solve().ok is (fv == expected)


@pytest.mark.parametrize("kind", ["literal", "clause", "pb"])
def test_iff_validates_indicator_without_allocating(kind):
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    formula = {"literal": a, "clause": a | b, "pb": 2 * a + b <= 1}[kind]
    top = m._next_id
    with pytest.raises(TypeError):
        formula.iff(1)
    with pytest.raises(ValueError, match="different models"):
        formula.iff(Model().bool("other"))
    assert m._next_id == top


def test_pb_iff_multiple_gates_and_repeated_realization():
    for g1, g2, flag in itertools.product((False, True), repeat=3):
        m = Model()
        a, gate1, gate2, indicator = (m.bool(name) for name in ("a", "g1", "g2", "flag"))
        formula = (2 * a == 1).only_if(gate1).only_if(gate2)
        result = formula.iff(indicator)
        m &= result
        top = m._next_id
        m &= result
        assert m._next_id == top
        for lit, value in ((gate1, g1), (gate2, g2), (indicator, flag)):
            m &= lit if value else ~lit
        assert m.solve().ok is (flag == (not (g1 and g2)))


@pytest.mark.parametrize("op", OPS, ids=lambda op: op.__name__)
def test_pb_iff_with_integer_terms_and_expression_rhs(op):
    for xv, yv, av, fv in itertools.product(range(3), range(2), (False, True), (False, True)):
        m = Model()
        x = m.int("x", 0, 2)
        y = m.int("y", 0, 1)
        a, flag = m.bool("a"), m.bool("flag")
        m &= op(x + 2 * a, y + 1).iff(~flag)
        m &= x == xv
        m &= y == yv
        m &= a if av else ~a
        m &= flag if fv else ~flag
        assert m.solve().ok is ((not fv) == op(xv + 2 * int(av), yv + 1))


@pytest.mark.parametrize("kind", ["literal", "clause", "pb", "gated_pb"])
def test_iff_indicator_may_also_appear_in_formula(kind):
    for av, bv in itertools.product((False, True), repeat=2):
        m = Model()
        a, b = m.bool("a"), m.bool("b")
        formulas = {"literal": ~a, "clause": a | b,
                    "pb": 2 * a + b <= 1,
                    "gated_pb": (2 * a + b <= 1).only_if(a)}
        expected = {"literal": not av, "clause": av or bv,
                    "pb": 2 * int(av) + int(bv) <= 1,
                    "gated_pb": not av or 2 * int(av) + int(bv) <= 1}
        m &= formulas[kind].iff(a)
        m &= a if av else ~a
        m &= b if bv else ~b
        assert m.solve().ok is (av == expected[kind])
