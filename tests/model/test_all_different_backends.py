import pytest

from hermax.model import ClauseGroup, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal result, got {r.status!r}"
    return r


def _solve_unsat(m: Model):
    r = m.solve()
    assert not r.ok
    assert r.status in {"unsat", "interrupted", "error"}
    return r


# -----------------------------
# EnumVector backend contracts
# -----------------------------

def test_enumvector_all_different_default_auto_matches_bipartite_type():
    m = Model()
    ev = m.enum_vector("e", length=3, choices=["a", "b", "c"])
    auto = ev.all_different()
    bip = ev.all_different(backend="bipartite")
    assert isinstance(auto, ClauseGroup)
    assert isinstance(bip, ClauseGroup)
    # Structural equality is not guaranteed, but both should be addable.
    m1 = Model()
    e1 = m1.enum_vector("e", length=3, choices=["a", "b", "c"])
    m1 &= e1.all_different()
    _solve_ok(m1)


def test_enumvector_all_different_pairwise_backend_supported():
    m = Model()
    ev = m.enum_vector("e", length=3, choices=["a", "b", "c"])
    cg = ev.all_different(backend="pairwise")
    assert isinstance(cg, ClauseGroup)


def test_enumvector_all_different_bipartite_backend_supported():
    m = Model()
    ev = m.enum_vector("e", length=3, choices=["a", "b", "c"])
    cg = ev.all_different(backend="bipartite")
    assert isinstance(cg, ClauseGroup)


def test_enumvector_all_different_unknown_backend_raises():
    m = Model()
    ev = m.enum_vector("e", length=2, choices=["a", "b"])
    with pytest.raises(ValueError, match="backend"):
        ev.all_different(backend="rainbow")


def test_enumvector_all_different_sorting_backend_rejected_or_not_implemented():
    m = Model()
    ev = m.enum_vector("e", length=3, choices=["a", "b", "c"])
    with pytest.raises((ValueError, NotImplementedError), match="sorting|backend"):
        ev.all_different(backend="sorting")


def test_enumvector_auto_and_pairwise_are_semantically_equivalent_on_forced_duplicate():
    # Duplicate forced assignments should be UNSAT under both backends.
    for backend in ("auto", "pairwise", "bipartite"):
        m = Model()
        ev = m.enum_vector("e", length=2, choices=["a", "b"])
        m &= ev.all_different(backend=backend)
        m &= (ev[0] == "a")
        m &= (ev[1] == "a")
        _solve_unsat(m)


def test_enumvector_auto_and_pairwise_are_semantically_equivalent_on_feasible_case():
    for backend in ("auto", "pairwise", "bipartite"):
        m = Model()
        ev = m.enum_vector("e", length=3, choices=["a", "b", "c"])
        m &= ev.all_different(backend=backend)
        m &= (ev[0] == "a")
        r = _solve_ok(m)
        vals = r[ev]
        assert len(set(vals)) == 3
        assert vals[0] == "a"


def test_enumvector_nullable_bipartite_all_different_treats_none_as_value():
    m = Model()
    ev = m.enum_vector("e", length=2, choices=["a"], nullable=True)
    m &= ev.all_different(backend="bipartite")
    # Force both to None -> should be UNSAT if None counts as a value for all_different.
    m &= ~(ev[0] == "a")
    m &= ~(ev[1] == "a")
    _solve_unsat(m)


# -----------------------------
# IntVector backend contracts
# -----------------------------

def test_intvector_all_different_default_auto_supported():
    m = Model()
    iv = m.int_vector("x", length=3, lb=0, ub=3)
    cg = iv.all_different()
    assert isinstance(cg, ClauseGroup)


def test_intvector_all_different_pairwise_backend_supported():
    m = Model()
    iv = m.int_vector("x", length=3, lb=0, ub=3)
    cg = iv.all_different(backend="pairwise")
    assert isinstance(cg, ClauseGroup)


def test_intvector_all_different_bipartite_backend_supported():
    m = Model()
    iv = m.int_vector("x", length=3, lb=0, ub=3)
    cg = iv.all_different(backend="bipartite")
    assert isinstance(cg, ClauseGroup)


def test_intvector_all_different_unknown_backend_raises():
    m = Model()
    iv = m.int_vector("x", length=3, lb=0, ub=3)
    with pytest.raises(ValueError, match="backend"):
        iv.all_different(backend="rainbow")


def test_intvector_all_different_sorting_backend_currently_rejected():
    m = Model()
    iv = m.int_vector("x", length=4, lb=0, ub=4)
    with pytest.raises(ValueError, match="backend"):
        iv.all_different(backend="sorting")


def test_intvector_backends_equivalent_on_forced_duplicate_unsat():
    for backend in ("auto", "pairwise", "bipartite"):
        m = Model()
        iv = m.int_vector("x", length=2, lb=0, ub=3)
        m &= iv.all_different(backend=backend)
        m &= (iv[0] == 1)
        m &= (iv[1] == 1)
        _solve_unsat(m)


def test_intvector_backends_equivalent_on_feasible_partial_assignment():
    for backend in ("auto", "pairwise", "bipartite"):
        m = Model()
        iv = m.int_vector("x", length=4, lb=0, ub=4)
        m &= iv.all_different(backend=backend)
        m &= (iv[0] == 0)
        m &= (iv[1] == 2)
        r = _solve_ok(m)
        vals = r[iv]
        assert len(set(vals)) == 4
        assert vals[0] == 0 and vals[1] == 2


def test_intvector_bipartite_rejects_domain_smaller_than_vector_length():
    m = Model()
    iv = m.int_vector("x", length=4, lb=0, ub=3)
    with pytest.raises(ValueError, match="domain|all_different|bipartite"):
        iv.all_different(backend="bipartite")
