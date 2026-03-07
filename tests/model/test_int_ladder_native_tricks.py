import pytest

from hermax.model import Clause, ClauseGroup, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal, got {r.status!r}"
    return r


def _solve_unsat(m: Model):
    r = m.solve()
    assert not r.ok
    assert r.status in {"unsat", "interrupted", "error"}
    return r


# -------------------------
# distance_at_most(x, y, D)
# -------------------------

def test_distance_at_most_returns_clausegroup():
    m = Model()
    x = m.int("x", 0, 8)
    y = m.int("y", 0, 8)
    cg = x.distance_at_most(y, 2)
    assert isinstance(cg, ClauseGroup)


def test_distance_at_most_rejects_negative_distance():
    m = Model()
    x = m.int("x", 0, 8)
    y = m.int("y", 0, 8)
    with pytest.raises(ValueError):
        x.distance_at_most(y, -1)


def test_distance_at_most_rejects_non_int_distance():
    m = Model()
    x = m.int("x", 0, 8)
    y = m.int("y", 0, 8)
    with pytest.raises(TypeError):
        x.distance_at_most(y, 1.5)


def test_distance_at_most_rejects_cross_model():
    m1 = Model()
    m2 = Model()
    x = m1.int("x", 0, 8)
    y = m2.int("y", 0, 8)
    with pytest.raises(ValueError):
        x.distance_at_most(y, 2)


def test_distance_at_most_semantics_satisfied_case():
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    m &= x.distance_at_most(y, 2)
    m &= (x == 3)
    m &= (y == 5)
    _solve_ok(m)


def test_distance_at_most_semantics_unsat_case():
    m = Model()
    x = m.int("x", 0, 10)
    y = m.int("y", 0, 10)
    m &= x.distance_at_most(y, 2)
    m &= (x == 2)
    m &= (y == 6)
    _solve_unsat(m)


def test_distance_at_most_zero_means_equality():
    m = Model()
    x = m.int("x", 0, 6)
    y = m.int("y", 0, 6)
    m &= x.distance_at_most(y, 0)
    m &= (x == 4)
    m &= (y == 4)
    _solve_ok(m)

    m2 = Model()
    a = m2.int("a", 0, 6)
    b = m2.int("b", 0, 6)
    m2 &= a.distance_at_most(b, 0)
    m2 &= (a == 4)
    m2 &= (b == 3)
    _solve_unsat(m2)


def test_distance_at_most_handles_shifted_domains():
    m = Model()
    x = m.int("x", 10, 20)
    y = m.int("y", 100, 110)
    m &= x.distance_at_most(y, 200)  # trivially satisfiable over these domains
    m &= (x == 12)
    m &= (y == 107)
    _solve_ok(m)


def test_distance_at_most_large_distance_can_be_trivial():
    m = Model()
    x = m.int("x", 0, 4)
    y = m.int("y", 10, 14)
    cg = x.distance_at_most(y, 20)
    assert isinstance(cg, ClauseGroup)
    m &= cg
    m &= (x == 0)
    m &= (y == 13)
    _solve_ok(m)


def test_distance_at_most_exact_domain_gap_boundary_sat_and_unsat():
    # Domains force minimum distance 6 (x in {0,1}, y in {7,8})
    m_sat = Model()
    x1 = m_sat.int("x", 0, 2)
    y1 = m_sat.int("y", 7, 9)
    m_sat &= x1.distance_at_most(y1, 8)
    m_sat &= (x1 == 1)
    m_sat &= (y1 == 7)
    _solve_ok(m_sat)

    m_unsat = Model()
    x2 = m_unsat.int("x", 0, 2)
    y2 = m_unsat.int("y", 7, 9)
    m_unsat &= x2.distance_at_most(y2, 5)
    _solve_unsat(m_unsat)


def test_distance_at_most_exact_assignment_boundary_sat_and_unsat():
    m = Model()
    x = m.int("x", 0, 20)
    y = m.int("y", 0, 20)
    m &= x.distance_at_most(y, 3)
    m &= (x == 4)
    m &= (y == 7)
    _solve_ok(m)

    m2 = Model()
    a = m2.int("a", 0, 20)
    b = m2.int("b", 0, 20)
    m2 &= a.distance_at_most(b, 2)
    m2 &= (a == 4)
    m2 &= (b == 7)
    _solve_unsat(m2)


def test_distance_at_most_is_symmetric_semantically():
    # Same forced assignments; both direction call forms should agree.
    m1 = Model()
    x1 = m1.int("x", 0, 10)
    y1 = m1.int("y", 0, 10)
    m1 &= x1.distance_at_most(y1, 2)
    m1 &= (x1 == 3)
    m1 &= (y1 == 6)
    r1 = m1.solve()

    m2 = Model()
    x2 = m2.int("x", 0, 10)
    y2 = m2.int("y", 0, 10)
    m2 &= y2.distance_at_most(x2, 2)
    m2 &= (x2 == 3)
    m2 &= (y2 == 6)
    r2 = m2.solve()

    assert r1.status == r2.status == "unsat"


# -------------------------
# forbid_value(x, v)
# -------------------------

def test_forbid_value_returns_clause_inside_domain():
    m = Model()
    x = m.int("x", 0, 6)
    c = x.forbid_value(3)
    assert isinstance(c, Clause)


def test_forbid_value_outside_domain_is_tautological_clause():
    m = Model()
    x = m.int("x", 0, 6)
    c1 = x.forbid_value(-1)
    c2 = x.forbid_value(6)
    assert isinstance(c1, Clause)
    assert isinstance(c2, Clause)
    # Should be addable and not constrain solutions.
    m &= c1
    m &= c2
    m &= (x == 4)
    _solve_ok(m)


def test_forbid_value_interior_value_unsat_when_forced():
    m = Model()
    x = m.int("x", 0, 8)
    m &= x.forbid_value(3)
    m &= (x == 3)
    _solve_unsat(m)


def test_forbid_value_interior_value_allows_other_values():
    m = Model()
    x = m.int("x", 0, 8)
    m &= x.forbid_value(3)
    m &= (x == 4)
    _solve_ok(m)


def test_forbid_value_lower_boundary_collapses_correctly():
    m = Model()
    x = m.int("x", 0, 5)
    m &= x.forbid_value(0)
    m &= (x == 0)
    _solve_unsat(m)

    m2 = Model()
    y = m2.int("y", 0, 5)
    m2 &= y.forbid_value(0)
    m2 &= (y == 1)
    _solve_ok(m2)


def test_forbid_value_upper_boundary_collapses_correctly():
    m = Model()
    x = m.int("x", 0, 5)  # values 0..4
    m &= x.forbid_value(4)
    m &= (x == 4)
    _solve_unsat(m)

    m2 = Model()
    y = m2.int("y", 0, 5)
    m2 &= y.forbid_value(4)
    m2 &= (y == 3)
    _solve_ok(m2)


def test_forbid_value_repeated_holes_builds_swiss_cheese_domain():
    m = Model()
    x = m.int("x", 0, 8)
    for v in [1, 3, 4, 6]:
        m &= x.forbid_value(v)

    # Blocked value
    m1 = Model()
    y = m1.int("y", 0, 8)
    for v in [1, 3, 4, 6]:
        m1 &= y.forbid_value(v)
    m1 &= (y == 4)
    _solve_unsat(m1)

    # Allowed value
    m2 = Model()
    z = m2.int("z", 0, 8)
    for v in [1, 3, 4, 6]:
        m2 &= z.forbid_value(v)
    m2 &= (z == 5)
    _solve_ok(m2)


# -------------------------
# forbid_interval(x, [a,b])
# -------------------------


def test_forbid_interval_returns_clause_for_interior_gap():
    m = Model()
    x = m.int("x", 0, 10)
    c = x.forbid_interval(3, 6)
    assert isinstance(c, Clause)


def test_forbid_interval_no_overlap_is_tautological_clause():
    m = Model()
    x = m.int("x", 10, 20)
    c1 = x.forbid_interval(0, 5)
    c2 = x.forbid_interval(30, 40)
    assert isinstance(c1, Clause)
    assert isinstance(c2, Clause)
    m &= c1
    m &= c2
    m &= (x == 12)
    _solve_ok(m)


def test_forbid_interval_interior_gap_blocks_all_values_in_gap_and_allows_outside():
    # Forbid [3, 6] from domain [0, 10) => values 3,4,5,6 blocked
    for blocked in [3, 4, 5, 6]:
        m = Model()
        x = m.int("x", 0, 10)
        m &= x.forbid_interval(3, 6)
        m &= (x == blocked)
        _solve_unsat(m)

    for allowed in [0, 2, 7, 9]:
        m = Model()
        x = m.int("x", 0, 10)
        m &= x.forbid_interval(3, 6)
        m &= (x == allowed)
        _solve_ok(m)


def test_forbid_interval_left_boundary_overlap_collapses_semantically():
    # Forbid [0, 3] in [0, 10) => force x >= 4
    m = Model()
    x = m.int("x", 0, 10)
    m &= x.forbid_interval(0, 3)
    m &= (x == 2)
    _solve_unsat(m)

    m2 = Model()
    y = m2.int("y", 0, 10)
    m2 &= y.forbid_interval(0, 3)
    m2 &= (y == 4)
    _solve_ok(m2)


def test_forbid_interval_right_boundary_overlap_collapses_semantically():
    # Forbid [7, 20] in [0, 10) => force x <= 6
    m = Model()
    x = m.int("x", 0, 10)
    m &= x.forbid_interval(7, 20)
    m &= (x == 8)
    _solve_unsat(m)

    m2 = Model()
    y = m2.int("y", 0, 10)
    m2 &= y.forbid_interval(7, 20)
    m2 &= (y == 6)
    _solve_ok(m2)


def test_forbid_interval_covering_entire_domain_is_contradiction():
    m = Model()
    x = m.int("x", 0, 10)
    m &= x.forbid_interval(-5, 50)
    _solve_unsat(m)


def test_forbid_interval_invalid_reversed_bounds_is_tautological_noop():
    m = Model()
    x = m.int("x", 0, 10)
    m &= x.forbid_interval(6, 3)
    m &= (x == 5)
    _solve_ok(m)


def test_forbid_interval_huge_gap_is_still_one_clause_and_semantically_correct():
    m = Model()
    x = m.int("x", 0, 1001)
    c = x.forbid_interval(200, 800)
    assert isinstance(c, Clause)
    # Implementation should stay tiny regardless of interval width.
    assert len(c.literals) <= 2

    m &= c
    m &= (x == 500)
    _solve_unsat(m)

    m2 = Model()
    y = m2.int("y", 0, 1001)
    m2 &= y.forbid_interval(200, 800)
    m2 &= (y == 801)
    _solve_ok(m2)
