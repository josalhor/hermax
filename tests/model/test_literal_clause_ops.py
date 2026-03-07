import pytest

from hermax.model import Model, Literal, Clause


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok
    return r


def _same_lit_seq(actual, expected):
    assert len(actual) == len(expected)
    for a, e in zip(actual, expected):
        assert a is e


def test_literal_negation_identity_and_polarity():
    m = Model()
    a = m.bool("a")

    na = ~a
    assert isinstance(na, Literal)
    assert na.id == a.id
    assert na.polarity is not a.polarity
    assert ~~a is a
    m &= ~a
    r = _solve_ok(m)
    assert r[a] is False


def test_literal_or_literal_produces_clause():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    c = a | b
    assert isinstance(c, Clause)
    _same_lit_seq(c.literals, [a, b])
    m &= c
    r = _solve_ok(m)
    assert r[a] or r[b]


def test_clause_or_literal_returns_new_clause_and_keeps_original_immutable():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    c1 = a | b
    c2 = c1 | c

    assert c1 is not c2
    _same_lit_seq(c1.literals, [a, b])
    _same_lit_seq(c2.literals, [a, b, c])
    m &= c2
    m &= ~a
    m &= ~b
    r = _solve_ok(m)
    assert r[c] is True


def test_clause_ior_literal_returns_new_clause_and_preserves_original():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    cl = a | b
    before = id(cl)
    cl2 = cl
    cl2 |= c

    assert id(cl) == before
    assert id(cl2) != before
    _same_lit_seq(cl.literals, [a, b])
    _same_lit_seq(cl2.literals, [a, b, c])
    m &= cl2
    m &= ~a
    m &= ~b
    r = _solve_ok(m)
    assert r[c] is True


def test_clause_append_requires_inplace_flag_and_then_mutates():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    cl = a | b
    before = id(cl)
    with pytest.raises(TypeError, match="inplace=True"):
        cl.append(c)

    out = cl.append(c, inplace=True)
    assert out is cl
    assert id(cl) == before
    _same_lit_seq(cl.literals, [a, b, c])

    m &= cl
    m &= ~a
    m &= ~b
    r = _solve_ok(m)
    assert r[c] is True


def test_literal_and_literal_builds_two_unit_clauses_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    g = a & b
    assert len(g.clauses) == 2
    m &= g
    r = m.solve()
    assert r.ok is True
    assert r[a] is True
    assert r[b] is True


def test_chained_literal_conjunction_builds_clausegroup_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    g = a & b & c
    assert len(g.clauses) == 3
    m &= g
    r = m.solve()
    assert r.ok is True
    assert r[a] is True
    assert r[b] is True
    assert r[c] is True


def test_mixed_conjunction_chaining_with_clause_and_clausegroup():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    d = m.bool("d")

    g = (a | b) & c & (d | ~a)
    assert len(g.clauses) == 3
    m &= g
    m &= ~d
    r = m.solve()
    assert r.ok is True
    assert r[c] is True
    assert r[d] is False
    # Since d is false, (d | ~a) forces ~a.
    assert r[a] is False


def test_clausegroup_iand_returns_new_group_and_preserves_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    g = a & b
    gid = id(g)
    g2 = g
    g2 &= c
    assert id(g2) != gid
    assert len(g.clauses) == 2
    assert len(g2.clauses) == 3

    m &= g2
    r = m.solve()
    assert r.ok is True
    assert r[a] is True and r[b] is True and r[c] is True


def test_clausegroup_extend_requires_inplace_flag_and_then_mutates():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    g = a & b
    gid = id(g)
    with pytest.raises(TypeError, match="inplace=True"):
        g.extend(c)

    out = g.extend(c, inplace=True)
    assert out is g
    assert id(g) == gid
    assert len(g.clauses) == 3

    m &= g
    r = m.solve()
    assert r.ok is True
    assert r[a] and r[b] and r[c]


def test_negating_clause_is_banned():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    with pytest.raises(TypeError, match="Cannot directly negate a Clause"):
        _ = ~(a | b)


def test_clause_from_iterable_rejects_empty_iterable():
    with pytest.raises(ValueError, match="at least one literal"):
        Clause.from_iterable([])


def test_clause_from_iterable_rejects_cross_model_literals():
    m1 = Model()
    m2 = Model()
    a = m1.bool("a")
    b = m2.bool("b")

    with pytest.raises(ValueError, match="different models"):
        Clause.from_iterable([a, b])


def test_literal_only_if_and_clause_only_if_append_negated_condition():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    cond = m.bool("cond")

    c1 = a.only_if(cond)
    assert isinstance(c1, Clause)
    _same_lit_seq(c1.literals, [a, ~cond])

    c2 = (a | b).only_if(cond)
    assert isinstance(c2, Clause)
    _same_lit_seq(c2.literals, [a, b, ~cond])

    # If cond is true, target must hold.
    m &= c1
    m &= c2
    m &= cond
    m &= ~b
    r = _solve_ok(m)
    assert r[a] is True


def test_literal_equality_builds_equivalence_constraints_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= (a == b)
    m &= a
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True


def test_literal_equality_detects_conflict_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= (a == b)
    m &= a
    m &= ~b
    r = m.solve()
    assert r.status == "unsat"


def test_literal_equality_works_with_unparenthesized_model_iand_comparison_syntax():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Critical Python precedence edge case: ensure this parses/behaves as
    # model &= (a == b), not something unintended.
    m &= a == b
    m &= a
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True


def test_literal_inequality_parenthesized_pre_evaluates_to_bool_constraint_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Distinct literal objects => current Literal.__ne__ returns True, so this is
    # a no-op hard constraint.
    m &= (a != b)
    m &= a
    r = _solve_ok(m)
    assert r[a] is True


def test_literal_inequality_unparenthesized_pre_evaluates_to_bool_constraint_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a != b
    m &= a
    r = _solve_ok(m)
    assert r[a] is True


def test_boolean_false_constraint_adds_empty_hard_clause_and_makes_model_unsat():
    m = Model()
    a = m.bool("a")

    m &= False
    m &= a
    r = m.solve()
    assert r.status == "unsat"


def test_clause_from_iterable_preserves_order():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    cl = Clause.from_iterable([~a, b, ~c])
    _same_lit_seq(cl.literals, [~a, b, ~c])
    m &= cl
    m &= a
    m &= c
    r = _solve_ok(m)
    assert r[b] is True
