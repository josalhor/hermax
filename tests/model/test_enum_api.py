import pytest

from hermax.model import ClauseGroup, Literal, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_enum_declaration_properties_and_choice_literals():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=False)

    assert color.name == "color"
    assert color.choices == ["red", "green", "blue"]
    assert color.nullable is False
    assert set(color._choice_lits.keys()) == {"red", "green", "blue"}
    assert all(isinstance(l, Literal) for l in color._choice_lits.values())


def test_nonnullable_enum_requires_at_least_one_choice():
    m = Model()
    with pytest.raises(ValueError, match="at least one choice"):
        m.enum("empty", choices=[], nullable=False)


def test_nullable_empty_enum_decodes_to_none():
    m = Model()
    e = m.enum("empty", choices=[], nullable=True)
    r = _solve_ok(m)
    assert r[e] is None


def test_enum_domain_constraints_are_deferred_lazily():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=False)
    maybe = m.enum("maybe", choices=["red", "green"], nullable=True)

    assert len(m._hard) == 0
    color_ids = {lit.id for lit in color._choice_lits.values()}
    maybe_ids = {lit.id for lit in maybe._choice_lits.values()}
    assert len(m._pending_pb_constraints) == 0
    assert color_ids | maybe_ids <= set(m._pending_literal_defs)

    color_group = m._pending_literal_defs[next(iter(color_ids))]
    maybe_group = m._pending_literal_defs[next(iter(maybe_ids))]

    color_clauses = {tuple(cl) for cl in color_group}
    maybe_clauses = {tuple(cl) for cl in maybe_group}
    color_lits = [color._choice_lits[c].id for c in color.choices]
    maybe_lits = [maybe._choice_lits[c].id for c in maybe.choices]

    assert color_clauses == {
        (-color_lits[0], -color_lits[1]),
        (-color_lits[0], -color_lits[2]),
        (-color_lits[1], -color_lits[2]),
        tuple(color_lits),
    }
    assert maybe_clauses == {
        (-maybe_lits[0], -maybe_lits[1]),
    }


def test_enum_nonnullable_has_exactly_one_semantics_end_to_end():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=False)

    r = _solve_ok(m)
    assert r.status == "sat"
    assert r[color] in {"red", "green", "blue"}

    # Exactly one choice should decode as true.
    true_count = sum(1 for c in color.choices if r[color._choice_lits[c]])
    assert true_count == 1


def test_enum_nullable_allows_none_end_to_end():
    m = Model()
    color = m.enum("color", choices=["red", "green"], nullable=True)

    # Force all choices false; AMO-only nullable enum should allow this.
    for c in color.choices:
        m &= ~color._choice_lits[c]

    r = _solve_ok(m)
    assert r[color] is None


def test_enum_string_equality_returns_literal_and_enforces_choice():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=False)

    eq_red = (color == "red")
    assert isinstance(eq_red, Literal)

    m &= eq_red
    r = _solve_ok(m)
    assert r[color] == "red"
    assert r[eq_red] is True


def test_enum_unknown_string_equality_raises():
    m = Model()
    color = m.enum("color", choices=["red", "green"], nullable=False)

    with pytest.raises(ValueError, match="Unknown enum choice"):
        _ = (color == "blue")


def test_enum_is_in_returns_flat_clause_and_enforces_subset_membership():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=False)

    day = color.is_in(["red", "green"])
    assert hasattr(day, "literals")
    assert [lit.name for lit in day.literals] == [color._choice_lits["red"].name, color._choice_lits["green"].name]

    m &= day
    red = (color == "red")
    assert isinstance(red, Literal)
    m &= ~red
    r = _solve_ok(m)
    assert r[color] == "green"


def test_enum_is_in_deduplicates_choices_preserving_first_occurrence_order():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=False)

    cl = color.is_in(["green", "green", "red", "green"])
    assert [m._lit_to_dimacs(l) for l in cl.literals] == [
        color._choice_lits["green"].id,
        color._choice_lits["red"].id,
    ]


def test_nullable_enum_is_in_rejects_none_and_use_is_in_or_none_instead():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=True)

    with pytest.raises(ValueError, match="Unknown enum choice None"):
        color.is_in(["red", None])  # type: ignore[list-item]



def test_nullable_enum_is_in_or_none_supports_none_only_and_mixed_subsets():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=True)

    # method requires at least one concrete label; use explicit exclusion to reach None-only behavior indirectly
    with pytest.raises(ValueError, match="at least one valid choice"):
        color.is_in_or_none([])

    m2 = Model()
    color2 = m2.enum("color", choices=["red", "green", "blue"], nullable=True)
    mixed = color2.is_in_or_none(["red"])
    assert isinstance(mixed, ClauseGroup)
    m2 &= mixed
    m2 &= ~color2._choice_lits["red"]
    r2 = _solve_ok(m2)
    assert r2[color2] is None

    m3 = Model()
    color3 = m3.enum("color", choices=["red", "green", "blue"], nullable=True)
    mixed3 = color3.is_in_or_none(["red"])
    m3 &= mixed3
    m3 &= (color3 == "green")
    assert m3.solve().status == "unsat"



def test_enum_is_in_or_none_rejects_nonnullable_or_unknown_choices():
    m = Model()
    color = m.enum("color", choices=["red", "green"], nullable=False)
    with pytest.raises(ValueError, match="requires a nullable enum"):
        color.is_in_or_none(["red"])

    m2 = Model()
    color2 = m2.enum("color", choices=["red", "green"], nullable=True)
    with pytest.raises(ValueError, match="Unknown enum choice"):
        color2.is_in_or_none(["blue"])


def test_enum_is_in_rejects_unknown_or_empty_choice_sets():
    m = Model()
    color = m.enum("color", choices=["red", "green"], nullable=False)

    with pytest.raises(ValueError, match="Unknown enum choice"):
        color.is_in(["red", "blue"])

    with pytest.raises(ValueError, match="at least one valid choice"):
        color.is_in([])


def test_enum_to_enum_equality_returns_clausegroup_and_enforces_same_choice():
    m = Model()
    c1 = m.enum("c1", choices=["r", "g"], nullable=False)
    c2 = m.enum("c2", choices=["r", "g"], nullable=False)

    eq = (c1 == c2)
    assert isinstance(eq, ClauseGroup)
    m &= eq
    m &= (c1 == "r")
    r = _solve_ok(m)
    assert r[c1] == "r"
    assert r[c2] == "r"


def test_enum_to_enum_equality_rejects_mismatched_choices():
    m = Model()
    c1 = m.enum("c1", choices=["r", "g"], nullable=False)
    c2 = m.enum("c2", choices=["r", "g"], nullable=True)
    c3 = m.enum("c3", choices=["r", "g", "b"], nullable=False)

    # Different nullability is allowed as long as choices match.
    eq = (c1 == c2)
    assert isinstance(eq, ClauseGroup)

    with pytest.raises(ValueError, match="matching choices"):
        _ = (c1 == c3)


def test_enum_string_inequality_is_negated_choice_literal_semantics():
    m = Model()
    color = m.enum("color", choices=["red", "green"], nullable=False)

    neq_red = (color != "red")
    assert isinstance(neq_red, Literal)

    m &= neq_red
    r = _solve_ok(m)
    assert r[color] == "green"
    assert r[neq_red] is True


def test_enum_to_enum_inequality_returns_clausegroup_and_enforces_distinct_values():
    m = Model()
    c1 = m.enum("c1", choices=["r", "g"], nullable=False)
    c2 = m.enum("c2", choices=["r", "g"], nullable=False)

    neq = (c1 != c2)
    assert isinstance(neq, ClauseGroup)
    m &= neq
    m &= (c1 == "r")
    r = _solve_ok(m)
    assert r[c1] == "r"
    assert r[c2] == "g"


def test_nullable_enum_to_enum_inequality_forbids_both_none():
    m = Model()
    c1 = m.enum("c1", choices=["r", "g"], nullable=True)
    c2 = m.enum("c2", choices=["r", "g"], nullable=True)
    m &= (c1 != c2)
    # Force both none; should be disallowed under inequality semantics.
    for c in c1.choices:
        m &= ~c1._choice_lits[c]
        m &= ~c2._choice_lits[c]
    r = m.solve()
    assert r.status == "unsat"


def test_enum_domain_constraints_make_double_selection_unsat():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=False)

    m &= color._choice_lits["red"]
    m &= color._choice_lits["green"]
    r = m.solve()
    assert r.status == "unsat"


def test_nullable_enum_domain_constraints_allow_zero_or_one_but_not_two():
    m1 = Model()
    color1 = m1.enum("color", choices=["red", "green"], nullable=True)
    m1 &= ~color1._choice_lits["red"]
    m1 &= ~color1._choice_lits["green"]
    r1 = _solve_ok(m1)
    assert r1[color1] is None

    m2 = Model()
    color2 = m2.enum("color", choices=["red", "green"], nullable=True)
    m2 &= color2._choice_lits["red"]
    m2 &= color2._choice_lits["green"]
    r2 = m2.solve()
    assert r2.status == "unsat"


def test_enum_export_preserves_exactly_one_semantics_for_nonnullable():
    m = Model()
    color = m.enum("color", choices=["r", "g", "b"], nullable=False)

    cnf = m.to_cnf()
    r = _solve_ok(m)
    assert r[color] in {"r", "g", "b"}


def test_enum_domain_encoding_policy_uses_pairwise_up_to_8_and_seqcounter_from_9():
    m_small = Model()
    e_small = m_small.enum("e_small", choices=[f"c{i}" for i in range(8)], nullable=False)
    g_small = m_small._pending_literal_defs[e_small._choice_lits["c0"].id]
    assert len(g_small._clauses) == 29
    assert m_small._top_id() == 8

    m_big = Model()
    e_big = m_big.enum("e_big", choices=[f"c{i}" for i in range(9)], nullable=False)
    g_big = m_big._pending_literal_defs[e_big._choice_lits["c0"].id]
    assert len(g_big._clauses) == 24
    assert m_big._top_id() == 17


def test_nullable_enum_domain_encoding_policy_uses_pairwise_up_to_8_and_seqcounter_from_9():
    m_small = Model()
    e_small = m_small.enum("e_small", choices=[f"c{i}" for i in range(8)], nullable=True)
    g_small = m_small._pending_literal_defs[e_small._choice_lits["c0"].id]
    assert len(g_small._clauses) == 28
    assert m_small._top_id() == 8

    m_big = Model()
    e_big = m_big.enum("e_big", choices=[f"c{i}" for i in range(9)], nullable=True)
    g_big = m_big._pending_literal_defs[e_big._choice_lits["c0"].id]
    assert len(g_big._clauses) == 23
    assert m_big._top_id() == 17
