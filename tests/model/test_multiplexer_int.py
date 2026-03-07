import pytest

from hermax.model import ClauseGroup, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_multiplexer_constant_rhs_filters_domain_by_unrolling():
    m = Model()
    w = m.int("w", lb=0, ub=3)  # values 0,1,2
    costs = [10, 100, 1000]

    cg = (costs @ w <= 50)
    assert isinstance(cg, ClauseGroup)
    m &= cg

    r = _solve_ok(m)
    assert r[w] == 0  # only index 0 survives


def test_multiplexer_constant_rhs_unsat_when_no_index_satisfies():
    m = Model()
    w = m.int("w", lb=0, ub=3)
    costs = [10, 100, 1000]

    m &= (costs @ w < 0)
    r = m.solve()
    assert r.status == "unsat"


def test_multiplexer_with_nonzero_lower_bound_uses_shifted_array_positions():
    m = Model()
    w = m.int("w", lb=3, ub=6)  # domain values 3,4,5 map to array positions 0,1,2
    costs = [7, 50, 90]

    m &= (costs @ w <= 49)
    r = _solve_ok(m)
    assert r[w] == 3

    m2 = Model()
    w2 = m2.int("w", lb=3, ub=6)
    m2 &= (costs @ w2 >= 80)
    r2 = _solve_ok(m2)
    assert r2[w2] == 5


def test_multiplexer_intvar_rhs_gates_branch_constraints():
    m = Model()
    w = m.int("w", lb=0, ub=3)
    budget = m.int("budget", lb=0, ub=200)
    costs = [10, 100, 150]

    # Fix index to 1 -> requires budget >= 100
    m &= (w == 1)
    m &= (costs @ w <= budget)
    m &= (budget < 100)
    r = m.solve()
    assert r.status == "unsat"

    m2 = Model()
    w2 = m2.int("w", lb=0, ub=3)
    budget2 = m2.int("budget", lb=0, ub=200)
    m2 &= (w2 == 1)
    m2 &= (costs @ w2 <= budget2)
    m2 &= (budget2 >= 100)
    r2 = _solve_ok(m2)
    assert r2[w2] == 1
    assert r2[budget2] >= 100


def test_multiplexer_eq_and_ne_with_intvar_rhs():
    m = Model()
    w = m.int("w", lb=0, ub=3)
    x = m.int("x", lb=0, ub=20)
    vals = [5, 9, 13]

    m &= (w == 2)
    m &= (vals @ w == x)
    r = _solve_ok(m)
    assert r[w] == 2
    assert r[x] == 13

    m2 = Model()
    w2 = m2.int("w", lb=0, ub=3)
    x2 = m2.int("x", lb=0, ub=20)
    m2 &= (w2 == 0)
    m2 &= (vals @ w2 != x2)
    m2 &= (x2 == 5)
    r2 = m2.solve()
    assert r2.status == "unsat"


def test_multiplexer_errors_for_bad_array_coverage_or_type():
    m = Model()
    w = m.int("w", lb=0, ub=3)

    with pytest.raises(ValueError, match="does not cover"):
        _ = ([1, 2] @ w <= 1)

    with pytest.raises(TypeError, match="sequence of ints"):
        _ = ("abc" @ w <= 1)  # type: ignore[operator]


def test_multiplexer_rejects_negative_lb_for_now():
    m = Model()
    w = m.int("w", lb=-1, ub=2)
    with pytest.raises(ValueError, match="lb >= 0"):
        _ = ([10, 20, 30] @ w <= 15)

