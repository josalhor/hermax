import pytest

from hermax.model import BoolVector, Clause, ClauseGroup, EnumVector, IntVector, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_bool_vector_construction_indexing_iteration_and_length():
    m = Model()
    v = m.bool_vector("v", length=4)

    assert isinstance(v, BoolVector)
    assert len(v) == 4
    assert list(v) == [v[0], v[1], v[2], v[3]]
    assert [lit.name for lit in v] == ["v[0]", "v[1]", "v[2]", "v[3]"]
    assert [lit.id for lit in v] == [1, 2, 3, 4]

    m &= v[0]
    m &= ~v[1]
    r = _solve_ok(m)
    assert r[v] == [True, False, False, False]


def test_int_vector_construction_indexing_iteration_and_length():
    m = Model()
    v = m.int_vector("v", length=3, lb=0, ub=5)

    assert isinstance(v, IntVector)
    assert len(v) == 3
    assert list(v) == [v[0], v[1], v[2]]
    assert [x.name for x in v] == ["v[0]", "v[1]", "v[2]"]
    # Each int has ub-lb threshold literals.
    assert all(len(x._threshold_lits) == 4 for x in v)


def test_enum_vector_construction_indexing_iteration_and_length():
    m = Model()
    v = m.enum_vector("color", length=2, choices=["r", "g"], nullable=True)

    assert isinstance(v, EnumVector)
    assert len(v) == 2
    assert list(v) == [v[0], v[1]]
    assert [x.name for x in v] == ["color[0]", "color[1]"]
    assert all(set(x._choice_lits.keys()) == {"r", "g"} for x in v)


def test_base_vector_constructor_validates_item_types_and_model_ownership():
    m1 = Model()
    m2 = Model()
    a = m1.bool("a")
    b_other = m2.bool("b")
    x = m1.int("x", lb=0, ub=3)
    e = m1.enum("e", choices=["r", "g"])

    with pytest.raises(TypeError, match="BoolVector expects items"):
        BoolVector(m1, "bad_bools", [a, x])

    with pytest.raises(TypeError, match="IntVector expects items"):
        IntVector(m1, "bad_ints", [x, a])

    with pytest.raises(TypeError, match="EnumVector expects items"):
        EnumVector(m1, "bad_enums", [e, a])

    with pytest.raises(ValueError, match="same model"):
        BoolVector(m1, "cross_model", [a, b_other])


def test_vector_naming_conflicts_are_rejected():
    m = Model()
    m.bool_vector("x", length=2)
    with pytest.raises(ValueError, match="already registered"):
        m.int_vector("x", length=2, lb=0, ub=3)

    m2 = Model()
    m2.bool("y")
    with pytest.raises(ValueError, match="already registered"):
        m2.enum_vector("y", length=2, choices=["r", "g"])


def test_intvector_all_different_increasing_and_lex_return_clausegroup_and_are_addable():
    m = Model()
    v1 = m.int_vector("v1", length=3, lb=0, ub=4)
    v2 = m.int_vector("v2", length=3, lb=0, ub=4)

    ad = v1.all_different()
    inc = v1.increasing()
    lex = v1.lexicographic_less_than(v2)

    assert isinstance(ad, ClauseGroup)
    assert isinstance(inc, ClauseGroup)
    assert isinstance(lex, ClauseGroup)

    m &= ad
    m &= inc
    m &= lex
    r = _solve_ok(m)
    assert r.status == "sat"


def test_enumvector_all_different_semantics_rejects_duplicate_choices():
    m = Model()
    ev = m.enum_vector("e", length=3, choices=["r", "g", "b"], nullable=False)
    ad = ev.all_different()
    assert isinstance(ad, ClauseGroup)
    m &= ad
    m &= (ev[0] == "r")
    m &= (ev[1] == "r")
    r = m.solve()
    assert r.status == "unsat"


def test_enumvector_all_different_allows_distinct_choices():
    m = Model()
    ev = m.enum_vector("e", length=3, choices=["r", "g", "b"], nullable=False)
    m &= ev.all_different()
    m &= (ev[0] == "r")
    m &= (ev[1] == "g")
    m &= (ev[2] == "b")
    r = _solve_ok(m)
    assert r[ev] == ["r", "g", "b"]


def test_intvector_is_in_allowed_combinations_semantics():
    m = Model()
    spec = m.int_vector("spec", length=3, lb=0, ub=6)
    allowed = [(1, 2, 1), (2, 4, 2), (3, 4, 3)]
    table = spec.is_in(allowed)
    assert isinstance(table, ClauseGroup)
    m &= table
    # Partial assignment should force the only compatible row.
    m &= (spec[0] == 2)
    m &= (spec[1] == 4)
    r = _solve_ok(m)
    assert r[spec] == [2, 4, 2]

    # Symmetric direction: fixing the shared suffix value should force the row too.
    m2 = Model()
    s2 = m2.int_vector("spec", length=3, lb=0, ub=6)
    m2 &= s2.is_in(allowed)
    m2 &= (s2[1] == 2)
    r2 = _solve_ok(m2)
    assert r2[s2] == [1, 2, 1]


def test_intvector_is_in_rejects_disallowed_combination():
    m = Model()
    spec = m.int_vector("spec", length=3, lb=0, ub=6)
    m &= spec.is_in([(1, 2, 1), (2, 4, 2), (3, 4, 3)])
    m &= (spec[0] == 1)
    m &= (spec[1] == 4)
    m &= (spec[2] == 1)
    assert m.solve().status == "unsat"


def test_enumvector_is_in_supports_nullable_none_and_rejects_bad_rows():
    m = Model()
    ev = m.enum_vector("shift", length=2, choices=["m", "d", "n"], nullable=True)
    m &= ev.is_in([("m", "d"), (None, "n")])
    # Partial assignment should force the only compatible row.
    m &= (ev[1] == "n")
    r = _solve_ok(m)
    assert r[ev] == [None, "n"]

    # Opposite branch also forces the row.
    m2 = Model()
    ev2 = m2.enum_vector("shift", length=2, choices=["m", "d", "n"], nullable=True)
    m2 &= ev2.is_in([("m", "d"), (None, "n")])
    m2 &= (ev2[0] == "m")
    r2 = _solve_ok(m2)
    assert r2[ev2] == ["m", "d"]

    with pytest.raises(ValueError, match="vector length"):
        _ = ev.is_in([("m",)])
    with pytest.raises(ValueError, match="Unknown enum choice"):
        _ = ev.is_in([("x", "m")])


def test_boolvector_is_in_allowed_combinations_and_deduplicates_rows():
    dup_rows = [(True, False), (True, False), (False, True)]
    uniq_rows = [(True, False), (False, True)]

    m = Model()
    bv = m.bool_vector("b", length=2)
    cg = bv.is_in(dup_rows)
    assert isinstance(cg, ClauseGroup)
    m &= cg
    # Table semantics should propagate: b1=True forces b0=False.
    m &= bv[1]
    r = _solve_ok(m)
    assert r[bv] == [False, True]

    # And vice versa.
    m2 = Model()
    bv2 = m2.bool_vector("b", length=2)
    m2 &= bv2.is_in(dup_rows)
    m2 &= bv2[0]
    r2 = _solve_ok(m2)
    assert r2[bv2] == [True, False]

    # Duplicate rows should be removed structurally.
    m3 = Model()
    a = m3.bool_vector("b", length=2)
    cg_dup = a.is_in(dup_rows)
    m4 = Model()
    b = m4.bool_vector("b", length=2)
    cg_uni = b.is_in(uniq_rows)
    assert len(cg_dup.clauses) == len(cg_uni.clauses)


def test_intvector_lexicographic_less_than_requires_intvector_and_same_model():
    m1 = Model()
    m2 = Model()
    v1 = m1.int_vector("v1", length=2, lb=0, ub=3)
    v2 = m2.int_vector("v2", length=2, lb=0, ub=3)

    with pytest.raises(TypeError, match="expects IntVector"):
        _ = v1.lexicographic_less_than(object())

    with pytest.raises(ValueError, match="different models"):
        _ = v1.lexicographic_less_than(v2)


def test_vector_operator_bans_eq_and_le():
    m = Model()
    v1 = m.int_vector("v1", length=2, lb=0, ub=3)
    v2 = m.int_vector("v2", length=2, lb=0, ub=3)

    with pytest.raises(TypeError, match="ambiguous"):
        _ = (v1 == v2)

    with pytest.raises(TypeError, match="lexicographic_less_than"):
        _ = (v1 <= v2)


def test_intvector_ne_returns_flat_clause_of_elementwise_difference_indicators():
    m = Model()
    v1 = m.int_vector("v1", length=3, lb=0, ub=4)
    v2 = m.int_vector("v2", length=3, lb=0, ub=4)

    diff = (v1 != v2)
    assert isinstance(diff, Clause)
    assert len(diff.literals) == 3

    # Current implementation uses exact per-element inequality indicators.
    expected = [v1[i]._neq_indicator(v2[i]) for i in range(3)]
    for got, exp in zip(diff.literals, expected):
        assert got is exp

    # It should be addable and solvable.
    m &= diff
    r = _solve_ok(m)
    assert any(r[lit] for lit in diff.literals)


def test_intvector_all_different_semantics_detects_equal_neighbors():
    m = Model()
    v = m.int_vector("v", length=3, lb=0, ub=4)
    m &= v.all_different()

    # Force v0 = 1 and v1 = 1 via threshold prefixes.
    v0t = v[0]._threshold_lits
    v1t = v[1]._threshold_lits
    m &= v0t[0]
    m &= ~v0t[1]
    m &= ~v0t[2]
    m &= v1t[0]
    m &= ~v1t[1]
    m &= ~v1t[2]

    r = m.solve()
    assert r.status == "unsat"


def test_intvector_increasing_semantics_allows_nondecreasing_and_rejects_descent():
    # Nondecreasing valid pattern.
    m1 = Model()
    v1 = m1.int_vector("v", length=3, lb=0, ub=4)
    m1 &= v1.increasing()
    # Values [0,1,1]
    # v[0]=0
    for lit in v1[0]._threshold_lits:
        m1 &= ~lit
    # v[1]=1
    t = v1[1]._threshold_lits
    m1 &= t[0]
    m1 &= ~t[1]
    m1 &= ~t[2]
    # v[2]=1
    t = v1[2]._threshold_lits
    m1 &= t[0]
    m1 &= ~t[1]
    m1 &= ~t[2]
    r1 = _solve_ok(m1)
    assert [r1[v1[i]] for i in range(3)] == [0, 1, 1]

    # Descent invalid pattern [2,1].
    m2 = Model()
    v2 = m2.int_vector("v", length=2, lb=0, ub=4)
    m2 &= v2.increasing()
    # v[0]=2
    t = v2[0]._threshold_lits
    m2 &= t[0]
    m2 &= t[1]
    m2 &= ~t[2]
    # v[1]=1
    t = v2[1]._threshold_lits
    m2 &= t[0]
    m2 &= ~t[1]
    m2 &= ~t[2]
    r2 = m2.solve()
    assert r2.status == "unsat"


def test_intvector_lexicographic_less_than_semantics():
    # Valid lex-less: [1,0] < [1,2]
    m1 = Model()
    a = m1.int_vector("a", length=2, lb=0, ub=4)
    b = m1.int_vector("b", length=2, lb=0, ub=4)
    m1 &= a.lexicographic_less_than(b)
    # a[0]=1, a[1]=0
    t = a[0]._threshold_lits
    m1 &= t[0]
    m1 &= ~t[1]
    m1 &= ~t[2]
    for lit in a[1]._threshold_lits:
        m1 &= ~lit
    # b[0]=1, b[1]=2
    t = b[0]._threshold_lits
    m1 &= t[0]
    m1 &= ~t[1]
    m1 &= ~t[2]
    t = b[1]._threshold_lits
    m1 &= t[0]
    m1 &= t[1]
    m1 &= ~t[2]
    r1 = _solve_ok(m1)
    assert [r1[a[i]] for i in range(2)] == [1, 0]
    assert [r1[b[i]] for i in range(2)] == [1, 2]

    # Invalid lex-less: [2,0] < [1,3] is false.
    m2 = Model()
    x = m2.int_vector("x", length=2, lb=0, ub=4)
    y = m2.int_vector("y", length=2, lb=0, ub=4)
    m2 &= x.lexicographic_less_than(y)
    # x=[2,0]
    t = x[0]._threshold_lits
    m2 &= t[0]
    m2 &= t[1]
    m2 &= ~t[2]
    for lit in x[1]._threshold_lits:
        m2 &= ~lit
    # y=[1,3]
    t = y[0]._threshold_lits
    m2 &= t[0]
    m2 &= ~t[1]
    m2 &= ~t[2]
    t = y[1]._threshold_lits
    m2 &= t[0]
    m2 &= t[1]
    m2 &= t[2]
    r2 = m2.solve()
    assert r2.status == "unsat"


def test_intvector_ne_clause_is_semantically_exact_via_indicators():
    m = Model()
    v1 = m.int_vector("v1", length=2, lb=0, ub=4)
    v2 = m.int_vector("v2", length=2, lb=0, ub=4)
    diff = (v1 != v2)
    m &= diff

    # Force vectors equal: [1,2] and [1,2] -> diff should become UNSAT.
    # v1[0]=1, v2[0]=1
    for vec in (v1, v2):
        t = vec[0]._threshold_lits
        m &= t[0]
        m &= ~t[1]
        m &= ~t[2]
    # v1[1]=2, v2[1]=2
    for vec in (v1, v2):
        t = vec[1]._threshold_lits
        m &= t[0]
        m &= t[1]
        m &= ~t[2]

    r = m.solve()
    assert r.status == "unsat"


def test_intvector_ne_length_mismatch_raises():
    m = Model()
    v1 = m.int_vector("v1", length=2, lb=0, ub=3)
    v2 = m.int_vector("v2", length=3, lb=0, ub=3)

    with pytest.raises(ValueError, match="lengths differ"):
        _ = (v1 != v2)


def test_intvector_ne_cross_model_raises():
    m1 = Model()
    m2 = Model()
    v1 = m1.int_vector("v1", length=2, lb=0, ub=3)
    v2 = m2.int_vector("v2", length=2, lb=0, ub=3)

    with pytest.raises(ValueError, match="different models"):
        _ = (v1 != v2)


def test_vector_items_participate_in_mixed_modeling_end_to_end():
    m = Model()
    flags = m.bool_vector("f", length=3)
    nums = m.int_vector("n", length=2, lb=0, ub=4)
    colors = m.enum_vector("c", length=2, choices=["red", "green"], nullable=False)

    # Use vector members in normal constraints.
    m &= (flags[0] | flags[1])
    m &= ~flags[1]
    m &= (nums[0] == nums[1])
    m &= (colors[0] == "red")
    m &= (colors[0] != colors[1])

    r = _solve_ok(m)
    assert r[flags] in ([True, False, False], [True, False, True]) or r[flags][0] is True
    assert r[nums[0]] == r[nums[1]]
    assert r[colors[0]] == "red"
    assert r[colors[1]] == "green"


def test_bool_and_enum_vector_declarations_emit_expected_domain_clause_patterns():
    m = Model()
    _bv = m.bool_vector("b", length=2)
    ev = m.enum_vector("e", length=2, choices=["r", "g"], nullable=False)

    # bool_vector emits no domain constraints; enum_vector emits EO for each enum.
    cnf = m.to_cnf()
    hard = cnf.clauses
    # Each 2-choice non-nullable enum contributes: [-r,-g] and [r,g].
    e0r = ev[0]._choice_lits["r"].id
    e0g = ev[0]._choice_lits["g"].id
    e1r = ev[1]._choice_lits["r"].id
    e1g = ev[1]._choice_lits["g"].id
    expected_pairs = {
        (-e0r, -e0g),
        (e0r, e0g),
        (-e1r, -e1g),
        (e1r, e1g),
    }
    assert expected_pairs.issubset({tuple(cl) for cl in hard})


def test_boolvector_cardinality_helpers_are_available_and_semantically_correct():
    m1 = Model()
    b1 = m1.bool_vector("b", length=3)
    m1 &= b1.exactly_one()
    r1 = _solve_ok(m1)
    assert sum(int(v) for v in r1[b1]) == 1

    m2 = Model()
    b2 = m2.bool_vector("b", length=3)
    m2 &= b2.at_most_one()
    m2 &= b2[0]
    m2 &= b2[1]
    assert m2.solve().status == "unsat"

    m3 = Model()
    b3 = m3.bool_vector("b", length=3)
    m3 &= b3.at_least_one()
    m3 &= ~b3[0]
    m3 &= ~b3[1]
    m3 &= ~b3[2]
    assert m3.solve().status == "unsat"
