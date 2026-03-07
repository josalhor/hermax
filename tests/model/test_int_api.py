import pytest

from hermax.model import Literal, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_int_declaration_properties_and_threshold_literals():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)

    assert speed.name == "speed"
    assert speed.lb == 0
    assert speed.ub == 4
    assert speed.lower_bound() == 0
    assert speed.upper_bound() == 3
    assert len(speed._threshold_lits) == 3
    assert all(isinstance(l, Literal) for l in speed._threshold_lits)
    assert [l.id for l in speed._threshold_lits] == [1, 2, 3]


def test_int_invalid_domains_raise():
    m = Model()

    with pytest.raises(ValueError):
        m.int("x", lb=5, ub=5)

    with pytest.raises(ValueError):
        m.int("y", lb=6, ub=5)

    with pytest.raises(TypeError):
        m.int("z", lb=0.0, ub=4)


def test_int_comparisons_return_literals_and_are_cached_by_operator_value():
    m = Model()
    speed = m.int("speed", lb=0, ub=10)

    le5_a = speed <= 5
    le5_b = speed <= 5
    lt5 = speed < 5
    ge3 = speed >= 3
    gt3 = speed > 3

    assert isinstance(le5_a, Literal)
    assert isinstance(lt5, Literal)
    assert isinstance(ge3, Literal)
    assert isinstance(gt3, Literal)
    assert le5_a is le5_b
    assert le5_a is not lt5


def test_int_comparisons_require_integer_rhs():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)

    with pytest.raises(TypeError):
        _ = speed <= 1.5
    with pytest.raises(TypeError):
        _ = speed >= "3"


def test_int_exact_equality_returns_cached_literal_in_domain():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)

    eq2_a = speed == 2
    eq2_b = speed == 2
    eq0 = speed == 0

    assert isinstance(eq2_a, Literal)
    assert eq2_a is eq2_b
    assert eq2_a is not eq0


def test_int_exact_equality_out_of_domain_raises():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)

    with pytest.raises(ValueError):
        _ = (speed == 4)
    with pytest.raises(ValueError):
        _ = (speed == -1)


def test_int_domain_constraints_allow_all_true_threshold_assignment_for_max_value():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)
    for t in speed._threshold_lits:
        m &= t

    r = _solve_ok(m)
    assert r[speed] == 3


def test_int_domain_constraints_enforce_prefix_monotonicity():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)
    t0, t1, t2 = speed._threshold_lits

    # Invalid non-prefix pattern: t1=true but t0=false should be UNSAT.
    m &= ~t0
    m &= t1
    r = m.solve()
    assert r.status == "unsat"

    # Another invalid pattern: t3=true but t2=false should also be UNSAT.
    m2 = Model()
    speed2 = m2.int("speed", lb=0, ub=4)
    s0, s1, s2 = speed2._threshold_lits
    m2 &= s2
    m2 &= ~s1
    r2 = m2.solve()
    assert r2.status == "unsat"


def test_int_valid_prefix_patterns_decode_to_expected_values():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)
    t0, t1, t2 = speed._threshold_lits

    # Value 2 under fallback decode => first two threshold bits true.
    m &= t0
    m &= t1
    m &= ~t2
    # max value no longer has an extra threshold bit in compact encoding.
    r = _solve_ok(m)
    assert r[speed] == 2


def test_int_exact_equality_literal_can_be_added_and_decoded_end_to_end():
    m = Model()
    speed = m.int("speed", lb=0, ub=5)

    m &= (speed == 3)
    r = _solve_ok(m)
    assert r[speed] == 3
    assert r[speed == 3] is True


def test_int_neq_integer_is_negated_equality_literal():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)

    neq2 = (speed != 2)
    assert isinstance(neq2, Literal)

    m &= (speed == 2)
    m &= neq2
    r = m.solve()
    assert r.status == "unsat"


def test_int_to_int_equality_returns_clausegroup_and_enforces_equal_value():
    m = Model()
    a = m.int("a", lb=0, ub=4)
    b = m.int("b", lb=0, ub=4)

    eq = (a == b)
    from hermax.model import ClauseGroup

    assert isinstance(eq, ClauseGroup)
    m &= eq
    # Force a=2 via threshold-prefix pattern (current exact equality literals are
    # still placeholders and cannot be used to pin semantics).
    ta0, ta1, ta2 = a._threshold_lits
    m &= ta0
    m &= ta1
    m &= ~ta2
    # compact ladder has 3 thresholds for [0,4)
    r = _solve_ok(m)
    assert r[a] == 2
    assert r[b] == 2


def test_int_to_int_inequality_returns_clausegroup_and_enforces_distinct_values():
    m = Model()
    a = m.int("a", lb=0, ub=4)
    b = m.int("b", lb=0, ub=4)

    neq = (a != b)
    from hermax.model import ClauseGroup

    assert isinstance(neq, ClauseGroup)
    m &= neq
    # Force both to the same value (1) via threshold-prefix patterns.
    ta0, ta1, ta2 = a._threshold_lits
    tb0, tb1, tb2 = b._threshold_lits
    m &= ta0
    m &= ~ta1
    m &= ~ta2
    # compact ladder has 3 thresholds for [0,4)
    m &= tb0
    m &= ~tb1
    m &= ~tb2
    # compact ladder has 3 thresholds for [0,4)
    r = m.solve()
    assert r.status == "unsat"


def test_int_to_int_inequality_with_disjoint_domains_is_tautology_clausegroup():
    m = Model()
    a = m.int("a", lb=0, ub=2)   # {0,1}
    b = m.int("b", lb=3, ub=5)   # {3,4}

    neq = (a != b)
    from hermax.model import ClauseGroup

    assert isinstance(neq, ClauseGroup)
    assert len(neq.clauses) == 0
    m &= neq
    r = _solve_ok(m)
    assert 0 <= r[a] < 2
    assert 3 <= r[b] < 5


def test_int_export_shape_contains_expected_ladder_domain_clauses():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)
    t0, t1, t2 = speed._threshold_lits

    cnf = m.to_cnf()
    got = {tuple(cl) for cl in cnf.clauses}
    expected = {
        (-t1.id, t0.id),
        (-t2.id, t1.id),
    }
    assert got == expected


def test_int_bound_queries_return_declared_static_domain_bounds():
    m = Model()
    speed = m.int("speed", lb=3, ub=9)

    # Add constraints that narrow the feasible set, but the current API exposes
    # declared/static bounds only (not propagated bounds).
    m &= (speed >= 6)
    m &= (speed <= 7)

    assert speed.lower_bound() == 3
    assert speed.upper_bound() == 8


def test_int_comparison_literals_have_real_semantics_end_to_end():
    m = Model()
    speed = m.int("speed", lb=0, ub=5)

    # Force speed=3 via threshold prefix.
    t0, t1, t2, t3 = speed._threshold_lits
    m &= t0
    m &= t1
    m &= t2
    m &= ~t3

    m &= (speed >= 3)
    m &= (speed > 2)
    m &= (speed <= 3)
    m &= (speed < 4)

    r = _solve_ok(m)
    assert r[speed] == 3
    assert r[speed >= 3] is True
    assert r[speed > 2] is True
    assert r[speed <= 3] is True
    assert r[speed < 4] is True


def test_int_comparison_edge_literals_map_to_constants_semantically():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)

    # These should be tautological under [0,4): speed>=0 and speed<=3
    m &= (speed >= 0)
    m &= (speed <= 3)
    r = _solve_ok(m)
    assert r[speed >= 0] is True
    assert r[speed <= 3] is True

    # These should be contradictions under [0,4): speed<0 and speed>=4
    m2 = Model()
    speed2 = m2.int("speed", lb=0, ub=4)
    m2 &= (speed2 < 0)
    r2 = m2.solve()
    assert r2.status == "unsat"

    m3 = Model()
    speed3 = m3.int("speed", lb=0, ub=4)
    m3 &= (speed3 >= 4)
    r3 = m3.solve()
    assert r3.status == "unsat"


def test_int_equality_literal_is_now_semantically_linked_to_threshold_pattern():
    m = Model()
    speed = m.int("speed", lb=0, ub=5)
    eq2 = (speed == 2)

    # Force the exact threshold pattern for value 2 and require eq2.
    t0, t1, t2, t3 = speed._threshold_lits
    m &= t0
    m &= t1
    m &= ~t2
    m &= ~t3
    m &= eq2
    r = _solve_ok(m)
    assert r[speed] == 2
    assert r[eq2] is True

    # Force a different value while requiring eq2 -> UNSAT.
    m2 = Model()
    speedb = m2.int("speed", lb=0, ub=5)
    eq2b = (speedb == 2)
    s0, s1, s2, s3 = speedb._threshold_lits
    # Value 1 pattern
    m2 &= s0
    m2 &= ~s1
    m2 &= ~s2
    m2 &= ~s3
    m2 &= eq2b
    r2 = m2.solve()
    assert r2.status == "unsat"
