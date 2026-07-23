import pytest

from hermax.model import Model, Literal, Clause, ClauseGroup


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
    assert len(g._clauses) == 2
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
    assert len(g._clauses) == 3
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
    assert len(g._clauses) == 3
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
    assert len(g._clauses) == 2
    assert len(g2._clauses) == 3

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
    assert len(g._clauses) == 3

    m &= g
    r = m.solve()
    assert r.ok is True
    assert r[a] and r[b] and r[c]


def test_clausegroup_extend_inplace_switches_to_mutable_storage_once():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    g = a & b
    assert isinstance(g._clauses, tuple)
    g.extend(c, inplace=True)
    assert isinstance(g._clauses, list)
    assert tuple(g) == ((a.id,), (b.id,), (c.id,))
    g.extend(ClauseGroup(m, [Clause(m, [~a])]), inplace=True)
    assert isinstance(g._clauses, list)
    assert tuple(g)[-1] == (-a.id,)


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


def test_clause_from_dimacs_keeps_aux_unmaterialized_until_literals_are_accessed():
    m = Model()
    a = m.bool("a")

    cl = Clause.from_dimacs(m, [a.id, -7])

    assert cl.dimacs == (a.id, -7)
    assert m._top_id() == 7
    assert 7 not in m._lits_by_id

    lits = cl.literals
    assert [lit.id for lit in lits] == [1, 7]
    assert [lit.polarity for lit in lits] == [True, False]
    assert m._top_id() == 7
    assert 7 in m._lits_by_id


def test_cnfplus_import_does_not_materialize_aux_literals_before_semantic_access():
    m = Model()
    a = m.bool("a")

    class _FakeCNF:
        clauses = [[a.id, -5], [5]]
        nv = 5

    g = m._cnfplus_to_clausegroup(_FakeCNF())
    assert len(g._clauses) == 2
    assert m._top_id() == 5
    assert 5 not in m._lits_by_id

    assert tuple(g._clauses[0]) == (1, -5)
    assert tuple(g._clauses[1]) == (5,)

    _ = g.materialize_semantic()[0].literals
    assert m._top_id() == 5
    assert 5 in m._lits_by_id


def test_cnfplus_import_rejects_non_cnf_like_objects():
    m = Model()

    class _Bad:
        pass

    with pytest.raises(TypeError, match="clauses' and 'nv"):
        m._cnfplus_to_clausegroup(_Bad())


def test_clausegroup_and_reuses_existing_dimacs_tuples_for_prefix_clauses():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    g = ClauseGroup(m, [a | b, ~a | c])
    g2 = g & c

    assert g2._clauses[0] is g._clauses[0]
    assert g2._clauses[1] is g._clauses[1]
    assert g2._clauses[2] == (c.id,)


def test_clause_append_inplace_switches_to_mutable_storage_once():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    cl = Clause(m, [a])
    assert isinstance(cl._dimacs, tuple)
    cl.append(b, inplace=True)
    assert isinstance(cl._dimacs, list)
    cl.append(c, inplace=True)
    assert cl.dimacs == (a.id, b.id, c.id)
    assert [lit.id for lit in cl.literals] == [a.id, b.id, c.id]


def test_clause_from_dimacs_trusted_keeps_aux_lazy_until_literals_access():
    m = Model()
    a = m.bool("a")
    m._reserve_literal_ids_up_to(9)

    raw = (a.id, -9)
    cl = Clause._from_dimacs_trusted(m, raw)

    assert cl.dimacs is raw
    assert 9 not in m._lits_by_id
    lits = cl.literals
    assert [lit.id for lit in lits] == [a.id, 9]
    assert [lit.polarity for lit in lits] == [True, False]


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


def test_literal_inequality_parenthesized_rejects_silent_identity_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    with pytest.raises(TypeError, match="Flatten the formula"):
        m &= (a != b)


def test_literal_inequality_unparenthesized_rejects_silent_identity_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    with pytest.raises(TypeError, match="Flatten the formula"):
        m &= a != b


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
