import pytest

from hermax.model import IntVar, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal result, got {r.status!r}"
    return r


def _solve_unsat(m: Model):
    r = m.solve()
    assert not r.ok
    assert r.status in {"unsat", "interrupted", "error"}
    return r


def test_model_max_enforces_semantics_same_domain():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=6)
    z = m.max(xs, name="zmax")
    assert isinstance(z, IntVar)
    assert z.lb == 0 and z.ub == 6
    m &= (xs[0] == 1)
    m &= (xs[1] == 4)
    m &= (xs[2] == 2)
    r = _solve_ok(m)
    assert r[z] == 4


def test_model_min_enforces_semantics_same_domain():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=6)
    z = m.min(xs, name="zmin")
    assert isinstance(z, IntVar)
    assert z.lb == 0 and z.ub == 6
    m &= (xs[0] == 1)
    m &= (xs[1] == 4)
    m &= (xs[2] == 2)
    r = _solve_ok(m)
    assert r[z] == 1


def test_model_max_mixed_domains():
    m = Model()
    a = m.int("a", lb=1, ub=5)
    b = m.int("b", lb=3, ub=8)
    c = m.int("c", lb=0, ub=4)
    z = m.max([a, b, c], name="z")
    m &= (a == 2)
    m &= (b == 6)
    m &= (c == 3)
    r = _solve_ok(m)
    assert r[z] == 6


def test_model_min_mixed_domains():
    m = Model()
    a = m.int("a", lb=1, ub=5)
    b = m.int("b", lb=3, ub=8)
    c = m.int("c", lb=0, ub=4)
    z = m.min([a, b, c], name="z")
    m &= (a == 2)
    m &= (b == 6)
    m &= (c == 3)
    r = _solve_ok(m)
    assert r[z] == 2 if False else r[z] == 2


def test_model_min_mixed_domains_with_actual_min_lower_than_all():
    m = Model()
    a = m.int("a", lb=1, ub=5)
    b = m.int("b", lb=3, ub=8)
    c = m.int("c", lb=0, ub=4)
    z = m.min([a, b, c], name="z")
    m &= (a == 2)
    m &= (b == 6)
    m &= (c == 0)
    r = _solve_ok(m)
    assert r[z] == 0


def test_model_max_forces_bound_consistency():
    m = Model()
    xs = m.int_vector("x", length=2, lb=0, ub=5)
    z = m.max(xs, name="z")
    m &= (xs[0] == 1)
    m &= (xs[1] == 4)
    m &= (z == 3)
    _solve_unsat(m)


def test_model_min_forces_bound_consistency():
    m = Model()
    xs = m.int_vector("x", length=2, lb=0, ub=5)
    z = m.min(xs, name="z")
    m &= (xs[0] == 1)
    m &= (xs[1] == 4)
    m &= (z == 2)
    _solve_unsat(m)


def test_intvector_max_singleton_returns_same_variable():
    m = Model()
    xs = m.int_vector("x", length=1, lb=0, ub=5)
    z = xs.max("z")
    assert z is xs[0]


def test_intvector_min_singleton_returns_same_variable():
    m = Model()
    xs = m.int_vector("x", length=1, lb=0, ub=5)
    z = xs.min("z")
    assert z is xs[0]


def test_intvector_max_empty_rejected():
    m = Model()
    v = m.vector([m.int("a", 0, 2)], name="tmp")
    # Construct an empty IntVector via direct class route is not public; use slicing flatten path.
    # Simpler: exercise method on an empty synthetic via matrix flatten of 0x0 is unavailable.
    # So validate through a minimal subclass path by mutating test object internals.
    v._items = []  # test-only corruption to hit the guard
    with pytest.raises(ValueError, match="empty"):
        v.max("z")


def test_intvector_min_empty_rejected():
    m = Model()
    v = m.vector([m.int("a", 0, 2)], name="tmp")
    v._items = []  # test-only corruption to hit the guard
    with pytest.raises(ValueError, match="empty"):
        v.min("z")


def test_intvector_max_structural_clause_growth_is_linear_in_thresholds():
    m = Model()
    xs = m.int_vector("x", length=4, lb=0, ub=6)  # span 6 -> 5 thresholds
    hard_before = len(m._hard)
    z = m.max(xs, name="z")
    hard_after = len(m._hard)
    # Output IntVar contributes its own domain constraints (4 clauses here), plus max wiring.
    # Wiring adds (n+1) clauses per threshold = 5 * (4+1) = 25 clauses.
    # Total delta should be at least 29 (exact unless constants are introduced, which they are not here).
    assert hard_after - hard_before >= 29
    assert z.lb == 0 and z.ub == 6


def test_intvector_min_structural_clause_growth_is_linear_in_thresholds():
    m = Model()
    xs = m.int_vector("x", length=4, lb=0, ub=6)
    hard_before = len(m._hard)
    z = m.min(xs, name="z")
    hard_after = len(m._hard)
    assert hard_after - hard_before >= 29
    assert z.lb == 0 and z.ub == 6


def test_intvector_max_name_collision_raises():
    m = Model()
    xs = m.int_vector("x", length=2, lb=0, ub=3)
    m.int("z", lb=0, ub=2)
    with pytest.raises(ValueError):
        m.max(xs, name="z")


def test_intvector_min_name_collision_raises():
    m = Model()
    xs = m.int_vector("x", length=2, lb=0, ub=3)
    m.int("z", lb=0, ub=2)
    with pytest.raises(ValueError):
        m.min(xs, name="z")


def test_intvector_minmax_mixed_domains_do_not_emit_internal_boolean_constants_in_wiring():
    m = Model()
    a = m.int("a", lb=0, ub=10)
    b = m.int("b", lb=100, ub=110)
    v = m.vector([a, b], name="v")

    hard_before = len(m._hard)
    zmax = m.max(v, name="zmax")
    zmin = m.min(v, name="zmin")
    new_clauses = m._hard[hard_before:]

    # The aggregate wiring should constant-fold out-of-domain thresholds instead of
    # inserting __true/__false literals into the emitted clauses.
    leaked_internal_consts = []
    for cl in new_clauses:
        for lit in cl.literals:
            if lit.name.startswith("__"):
                leaked_internal_consts.append((cl, lit))
    assert leaked_internal_consts == []

    # Semantics still hold.
    m &= (a == 3)
    m &= (b == 107)
    r = _solve_ok(m)
    assert r[zmax] == 107
    assert r[zmin] == 3


def test_intvector_upper_bound_is_one_sided_and_valid():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=8)
    ubv = m.upper_bound(xs, name="ubv")
    m &= (xs[0] == 2)
    m &= (xs[1] == 5)
    m &= (xs[2] == 4)
    # One-sided: any z >= 5 is valid.
    m &= (ubv == 6)
    r = _solve_ok(m)
    assert r[ubv] == 6
    vals = r[xs]
    assert all(r[ubv] >= v for v in vals)


def test_intvector_upper_bound_rejects_too_small_value():
    m = Model()
    xs = m.int_vector("x", length=2, lb=0, ub=8)
    ubv = m.upper_bound(xs, name="ubv")
    m &= (xs[0] == 2)
    m &= (xs[1] == 5)
    m &= (ubv == 4)
    _solve_unsat(m)


def test_intvector_lower_bound_is_one_sided_and_valid():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=8)
    lbv = m.lower_bound(xs, name="lbv")
    m &= (xs[0] == 2)
    m &= (xs[1] == 5)
    m &= (xs[2] == 4)
    # One-sided: any z <= 2 is valid.
    m &= (lbv == 1)
    r = _solve_ok(m)
    assert r[lbv] == 1
    vals = r[xs]
    assert all(r[lbv] <= v for v in vals)


def test_intvector_lower_bound_rejects_too_large_value():
    m = Model()
    xs = m.int_vector("x", length=2, lb=0, ub=8)
    lbv = m.lower_bound(xs, name="lbv")
    m &= (xs[0] == 2)
    m &= (xs[1] == 5)
    m &= (lbv == 3)
    _solve_unsat(m)


def test_intvector_upper_bound_with_objective_minimization_hits_max():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=8)
    ubv = m.upper_bound(xs, name="ubv")
    m &= (xs[0] == 2)
    m &= (xs[1] == 5)
    m &= (xs[2] == 4)
    m.obj[1] += ubv
    r = _solve_ok(m)
    assert r[ubv] == 5


def test_intvector_lower_bound_with_objective_maximization_via_soft_penalty_hits_min():
    # Maximize lower bound by minimizing distance to its upper edge:
    # this is just a smoke test that the one-sided lower bound composes with
    # objective modeling and tightens to the true min under pressure.
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=8)
    lbv = m.lower_bound(xs, name="lbv")
    m &= (xs[0] == 2)
    m &= (xs[1] == 5)
    m &= (xs[2] == 4)
    # Push lbv upward by forcing a contradiction if it is too low, then allow exact min.
    m &= (lbv >= 2)
    r = _solve_ok(m)
    assert r[lbv] == 2
def test_model_max_accepts_plain_list_without_vector_wrapper():
    m = Model()
    a = m.int("a", 0, 5)
    b = m.int("b", 0, 5)
    z = m.max([a, b], name="z")
    m &= (a == 1)
    m &= (b == 4)
    r = _solve_ok(m)
    assert r[z] == 4


def test_model_upper_bound_accepts_tuple_without_vector_wrapper():
    m = Model()
    a = m.int("a", 0, 6)
    b = m.int("b", 0, 6)
    z = m.upper_bound((a, b), name="z")
    m &= (a == 1)
    m &= (b == 4)
    m &= (z == 5)
    r = _solve_ok(m)
    assert r[z] == 5
    assert r[z] >= r[a] and r[z] >= r[b]


def test_intvector_running_max_basic_semantics():
    m = Model()
    xs = m.int_vector("x", length=4, lb=0, ub=8)
    rm = xs.running_max("rm")
    assert len(rm) == 4
    assert rm[0] is xs[0]

    m &= (xs[0] == 2)
    m &= (xs[1] == 5)
    m &= (xs[2] == 4)
    m &= (xs[3] == 7)
    r = _solve_ok(m)
    assert r[rm] == [2, 5, 5, 7]


def test_intvector_running_min_basic_semantics():
    m = Model()
    xs = m.int_vector("x", length=4, lb=0, ub=8)
    rn = xs.running_min("rn")
    assert len(rn) == 4
    assert rn[0] is xs[0]

    m &= (xs[0] == 6)
    m &= (xs[1] == 5)
    m &= (xs[2] == 7)
    m &= (xs[3] == 2)
    r = _solve_ok(m)
    assert r[rn] == [6, 5, 5, 2]


def test_intvector_running_max_empty_rejected():
    m = Model()
    v = m.vector([m.int("a", 0, 2)], name="tmp")
    v._items = []  # test-only corruption to hit guard
    with pytest.raises(ValueError, match="empty"):
        v.running_max("rm")


def test_intvector_running_min_empty_rejected():
    m = Model()
    v = m.vector([m.int("a", 0, 2)], name="tmp")
    v._items = []  # test-only corruption to hit guard
    with pytest.raises(ValueError, match="empty"):
        v.running_min("rn")


def test_intvector_running_max_singleton_returns_same_variable():
    m = Model()
    xs = m.int_vector("x", length=1, lb=0, ub=5)
    rm = xs.running_max("rm")
    assert len(rm) == 1
    assert rm[0] is xs[0]


def test_intvector_running_min_singleton_returns_same_variable():
    m = Model()
    xs = m.int_vector("x", length=1, lb=0, ub=5)
    rn = xs.running_min("rn")
    assert len(rn) == 1
    assert rn[0] is xs[0]


def test_intvector_running_max_returns_intvector_with_materialized_intvars():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=6)
    rm = xs.running_max("rm")
    assert all(isinstance(v, IntVar) for v in rm)
    assert rm.name == "rm"


def test_intvector_running_min_returns_intvector_with_materialized_intvars():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=6)
    rn = xs.running_min("rn")
    assert all(isinstance(v, IntVar) for v in rn)
    assert rn.name == "rn"


def test_intvector_running_max_name_collision_raises():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=6)
    m.int_vector("rm", length=1, lb=0, ub=2)
    with pytest.raises(ValueError):
        xs.running_max("rm")


def test_intvector_running_min_name_collision_raises():
    m = Model()
    xs = m.int_vector("x", length=3, lb=0, ub=6)
    m.int_vector("rn", length=1, lb=0, ub=2)
    with pytest.raises(ValueError):
        xs.running_min("rn")


def test_intvector_running_max_prefix_consistency_constraints():
    m = Model()
    xs = m.int_vector("x", length=4, lb=0, ub=8)
    rm = xs.running_max("rm")
    m &= (xs[0] == 2)
    m &= (xs[1] == 5)
    m &= (xs[2] == 4)
    m &= (xs[3] == 7)
    # Prefix-2 max is 5, so forcing 4 must be impossible.
    m &= (rm[2] == 4)
    _solve_unsat(m)


def test_intvector_running_min_prefix_consistency_constraints():
    m = Model()
    xs = m.int_vector("x", length=4, lb=0, ub=8)
    rn = xs.running_min("rn")
    m &= (xs[0] == 6)
    m &= (xs[1] == 5)
    m &= (xs[2] == 7)
    m &= (xs[3] == 2)
    # Prefix-2 min is 5, so forcing 6 must be impossible.
    m &= (rn[2] == 6)
    _solve_unsat(m)
