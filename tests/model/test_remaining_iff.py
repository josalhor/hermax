"""Truth tables for reification of composite constraints."""

import itertools
import operator

import pytest

from hermax.model import Clause, ClauseGroup, Model


@pytest.mark.parametrize("kind", ["and", "gated", "distance", "increasing", "lex", "vector_ne", "element"])
def test_integer_and_composite_iff(kind):
    for xv, yv, zv, bv in itertools.product(range(2), range(2), range(2), (False, True)):
        m = Model()
        x, y, z, b = m.int("x", 0, 1), m.int("y", 0, 1), m.int("z", 0, 1), m.bool("b")
        if kind == "and":
            formula = (x == 1) & (y == 1)
            expected = xv == 1 and yv == 1
        elif kind == "gated":
            formula = (x != y).only_if(z == 1)
            expected = zv != 1 or xv != yv
        elif kind == "distance":
            formula = x.distance_at_most(y, 0)
            expected = xv == yv
        elif kind == "increasing":
            values = m.int_vector("v", 2, 0, 1)
            formula = values.increasing()
            m &= values[0] == xv; m &= values[1] == yv
            expected = xv <= yv
        elif kind == "lex":
            left = m.int_vector("l", 2, 0, 1)
            right = m.int_vector("r", 2, 0, 1)
            formula = left.lexicographic_less_than(right)
            m &= left[0] == xv; m &= left[1] == yv
            m &= right[0] == yv; m &= right[1] == zv
            expected = (xv, yv) < (yv, zv)
        elif kind == "vector_ne":
            left = m.int_vector("l", 2, 0, 1)
            right = m.int_vector("r", 2, 0, 1)
            formula = left != right
            m &= left[0] == xv; m &= left[1] == yv
            m &= right[0] == yv; m &= right[1] == zv
            expected = (xv, yv) != (yv, zv)
        else:
            values = m.int_vector("v", 2, 0, 1)
            formula = values[z] == x
            m &= values[0] == xv; m &= values[1] == yv
            expected = (xv, yv)[zv] == xv
        m &= formula.iff(b)
        m &= x == xv; m &= y == yv; m &= z == zv
        m &= b if bv else ~b
        assert m.solve().ok is (bv == expected)


@pytest.mark.parametrize("kind", ["eq", "ne", "subset"])
def test_set_iff(kind):
    for av, cv, bv in itertools.product(range(4), range(4), (False, True)):
        m = Model()
        a, c, flag = m.int_set("a", values=[0, 1]), m.int_set("c", values=[0, 1]), m.bool("b")
        avalue = {i for i in range(2) if av & (1 << i)}
        cvalue = {i for i in range(2) if cv & (1 << i)}
        formula = {"eq": lambda: a == c, "ne": lambda: a != c, "subset": lambda: a.subset_of(c)}[kind]()
        expected = {"eq": avalue == cvalue, "ne": avalue != cvalue, "subset": avalue <= cvalue}[kind]
        m &= formula.iff(flag)
        m &= a == avalue; m &= c == cvalue
        m &= flag if bv else ~flag
        assert m.solve().ok is (bv == expected)


@pytest.mark.parametrize("op", [operator.eq, operator.ne])
def test_nullable_enum_comparison_iff(op):
    for av, cv, bv in itertools.product((None, "r", "g"), (None, "r", "g"), (False, True)):
        m = Model()
        a = m.enum("a", ["r", "g"], nullable=True)
        c = m.enum("c", ["r", "g"], nullable=True)
        flag = m.bool("b")
        m &= op(a, c).iff(flag)
        for enum, value in ((a, av), (c, cv)):
            for choice in ("r", "g"):
                m &= (enum == choice) if choice == value else (enum != choice)
        m &= flag if bv else ~flag
        assert m.solve().ok is (bv == op(av, cv))


@pytest.mark.parametrize("mode", ["gated", "left_and", "right_and"])
def test_composed_global_preserves_semantics(mode):
    for xv, yv, gate, flag in itertools.product(range(2), range(2), (False, True), (False, True)):
        m = Model()
        xs = m.int_vector("xs", 2, 0, 1)
        g, b = m.bool("g"), m.bool("b")
        global_constraint = m.table(xs, allowed=[(0, 1), (1, 0)])
        formula = {"gated": lambda: global_constraint.only_if(g),
                   "left_and": lambda: global_constraint & g,
                   "right_and": lambda: g & global_constraint}[mode]()
        m &= formula.iff(b)
        m &= xs[0] == xv; m &= xs[1] == yv
        m &= g if gate else ~g
        m &= b if flag else ~b
        expected = (not gate or xv != yv) if mode == "gated" else (gate and xv != yv)
        assert m.solve().ok is (flag == expected)


@pytest.mark.parametrize("gated", [False, True])
def test_no_overlap_iff(gated):
    for av, cv, gv, bv in itertools.product(range(3), range(3), (False, True), (False, True)):
        m = Model()
        a = m.interval("a", start=0, duration=1, end=3)
        c = m.interval("c", start=0, duration=1, end=3)
        gate, flag = m.bool("gate"), m.bool("flag")
        constraint = a.no_overlap(c)
        if gated:
            constraint = constraint.only_if(gate)
        m &= constraint.iff(flag)
        m &= a.start == av; m &= c.start == cv
        m &= gate if gv else ~gate
        m &= flag if bv else ~flag
        expected = av != cv
        if gated:
            expected = not gv or expected
        assert m.solve().ok is (bv == expected)


@pytest.mark.parametrize("mode", ["left_and", "right_and"])
def test_composed_set_disequality_iff(mode):
    for av, cv, gv, bv in itertools.product(range(4), range(4), (False, True), (False, True)):
        m = Model()
        a, c = m.int_set("a", values=[0, 1]), m.int_set("c", values=[0, 1])
        gate, flag = m.bool("gate"), m.bool("flag")
        avalue = {i for i in range(2) if av & (1 << i)}
        cvalue = {i for i in range(2) if cv & (1 << i)}
        relation = a != c
        constraint = relation & gate if mode == "left_and" else gate & relation
        m &= constraint.iff(flag)
        m &= a == avalue; m &= c == cvalue
        m &= gate if gv else ~gate
        m &= flag if bv else ~flag
        assert m.solve().ok is (bv == (gv and avalue != cvalue))


def test_set_table_iff():
    for av, cv, bv in itertools.product(range(4), range(4), (False, True)):
        m = Model()
        sets = m.int_set_vector("sets", 2, values=[0, 1])
        flag = m.bool("flag")
        avalue = {i for i in range(2) if av & (1 << i)}
        cvalue = {i for i in range(2) if cv & (1 << i)}
        rows = [(set(), {0}), ({1}, {0, 1})]
        m &= sets.is_in(rows).iff(flag)
        m &= sets[0] == avalue; m &= sets[1] == cvalue
        m &= flag if bv else ~flag
        assert m.solve().ok is (bv == ((avalue, cvalue) in rows))


@pytest.mark.parametrize("method, expected", [("at_most_one", True), ("exactly_one", False), ("at_least_one", False)])
def test_empty_boolean_cardinality_iff(method, expected):
    for value in (False, True):
        m = Model()
        values = m.bool_vector("values", 0)
        b = m.bool("b")
        m &= getattr(values, method)().iff(b)
        m &= b if value else ~b
        assert m.solve().ok is (value == expected)


def test_nested_pb_reification():
    for av, cv, bv, dv in itertools.product((False, True), repeat=4):
        m = Model()
        a, c, b, d = (m.bool(name) for name in ("a", "c", "b", "d"))
        m &= (2 * a + c == 1).iff(b).iff(d)
        for lit, value in ((a, av), (c, cv), (b, bv), (d, dv)):
            m &= lit if value else ~lit
        assert m.solve().ok is (dv == (bv == (2 * int(av) + int(cv) == 1)))


def test_pb_equality_implication_can_be_reified():
    for av, cv, bv, dv in itertools.product((False, True), repeat=4):
        m = Model()
        a, c, b, d = (m.bool(name) for name in ("a", "c", "b", "d"))
        m &= (2 * a + c == 1).implies(b).iff(d)
        for lit, value in ((a, av), (c, cv), (b, bv), (d, dv)):
            m &= lit if value else ~lit
        assert m.solve().ok is (dv == (not (2 * int(av) + int(cv) == 1) or bv))


def test_clause_implication_to_pb_can_be_reified():
    for av, cv, bv, dv in itertools.product((False, True), repeat=4):
        m = Model()
        a, c, b, d = (m.bool(name) for name in ("a", "c", "b", "d"))
        m &= (a | c).implies(2 * a + c == 1).iff(d)
        for lit, value in ((a, av), (c, cv), (b, bv), (d, dv)):
            m &= lit if value else ~lit
        assert m.solve().ok is (dv == (not (av or cv) or 2 * int(av) + int(cv) == 1))


def test_clause_implication_to_larger_pb_can_be_reified():
    for values in itertools.product((False, True), repeat=6):
        m = Model()
        xs = m.bool_vector("xs", 5)
        flag = m.bool("flag")
        constraint = (xs[0] | xs[1]).implies(sum((i + 1) * xs[i] for i in range(5)) == 5)
        m &= constraint.iff(flag)
        for lit, value in zip(xs, values):
            m &= lit if value else ~lit
        m &= flag if values[5] else ~flag
        expected = not (values[0] or values[1]) or sum((i + 1) * values[i] for i in range(5)) == 5
        assert m.solve().ok is (values[5] == expected)


def test_nested_global_reification():
    for av, cv, bv, dv in itertools.product(range(2), range(2), (False, True), (False, True)):
        m = Model()
        values = m.int_vector("v", 2, 0, 1)
        b, d = m.bool("b"), m.bool("d")
        m &= values.all_different().iff(b).iff(d)
        m &= values[0] == av; m &= values[1] == cv
        m &= b if bv else ~b
        m &= d if dv else ~d
        assert m.solve().ok is (dv == (bv == (av != cv)))


@pytest.mark.parametrize("kind", ["empty", "false", "units", "clauses"])
def test_clause_group_iff(kind):
    for av, cv, bv in itertools.product((False, True), repeat=3):
        m = Model()
        a, c, flag = m.bool("a"), m.bool("c"), m.bool("flag")
        clauses = {"empty": [], "false": [Clause(m, [])],
                   "units": [Clause(m, [a]), Clause(m, [~c])],
                   "clauses": [a | c, ~a | c]}[kind]
        expected = {"empty": True, "false": False,
                    "units": av and not cv, "clauses": cv}[kind]
        group = ClauseGroup(m, clauses)
        top = m._next_id
        reified = group.iff(flag)
        assert m._next_id == top
        m &= reified
        if kind != "clauses":
            assert m._next_id == top
        m &= a if av else ~a; m &= c if cv else ~c
        m &= flag if bv else ~flag
        assert m.solve().ok is (bv == expected)


@pytest.mark.parametrize("op", [operator.le, operator.lt, operator.ge, operator.gt, operator.eq, operator.ne])
def test_indexed_constant_array_comparison_iff(op):
    for index, rhs, flag in itertools.product(range(2), range(3), (False, True)):
        m = Model()
        i, x, b = m.int("i", 0, 1), m.int("x", 0, 2), m.bool("b")
        formula = op([2, 0] @ i, x)
        m &= formula.iff(b)
        m &= i == index; m &= x == rhs
        m &= b if flag else ~b
        assert m.solve().ok is (flag == op([2, 0][index], rhs))


def test_nullable_enum_membership_iff():
    for value, flag in itertools.product((None, "r", "g"), (False, True)):
        m = Model()
        enum = m.enum("e", ["r", "g"], nullable=True)
        b = m.bool("b")
        m &= enum.is_in_or_none(["r"]).iff(b)
        for choice in ("r", "g"):
            m &= (enum == choice) if choice == value else (enum != choice)
        m &= b if flag else ~b
        assert m.solve().ok is (flag == (value in (None, "r")))
