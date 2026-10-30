import random

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
    iv = m.int_vector("x", length=4, lb=0, ub=2)
    with pytest.raises(ValueError, match="domain|all_different|bipartite"):
        iv.all_different(backend="bipartite")


def test_intvector_bipartite_accepts_exact_domain_size_boundary():
    m = Model()
    iv = m.int_vector("x", length=4, lb=0, ub=3)
    m &= iv.all_different(backend="bipartite")
    m &= (iv[0] == 0)
    m &= (iv[1] == 1)
    m &= (iv[2] == 2)
    m &= (iv[3] == 3)

    r = _solve_ok(m)
    assert r[iv] == [0, 1, 2, 3]


def test_intvector_bipartite_accepts_distinct_fixed_assignments_across_random_cases():
    rng = random.Random(29)

    for case in range(12):
        length = rng.randint(2, 5)
        start = rng.randint(-2, 3)
        domain = list(range(start, start + length + 1 + rng.randint(0, 2)))
        chosen = rng.sample(domain, length)

        m = Model()
        iv = m.int_vector(f"x_{case}", length=length, lb=domain[0], ub=domain[-1])
        m &= iv.all_different(backend="bipartite")
        for x, value in zip(iv, chosen):
            m &= (x == value)

        r = _solve_ok(m)
        assert r[iv] == chosen


def test_intvector_bipartite_rejects_duplicate_fixed_assignments_across_random_cases():
    rng = random.Random(31)

    for case in range(12):
        length = rng.randint(2, 5)
        start = rng.randint(0, 3)
        domain = list(range(start, start + length + 2))
        chosen = rng.sample(domain, length)
        dup_index = rng.randrange(length)
        other_index = (dup_index + 1) % length
        chosen[other_index] = chosen[dup_index]

        m = Model()
        iv = m.int_vector(f"xdup_{case}", length=length, lb=domain[0], ub=domain[-1])
        m &= iv.all_different(backend="bipartite")
        for x, value in zip(iv, chosen):
            m &= (x == value)

        _solve_unsat(m)


@pytest.mark.parametrize("reified", [False, True])
def test_large_nullable_enum_all_different_avoids_pairwise_growth(reified):
    m = Model()
    xs = m.enum_vector("x", 64, choices=[str(i) for i in range(64)], nullable=True)
    condition = xs.all_different()
    m &= condition.iff(m.bool("flag")) if reified else condition
    cnf = m.to_cnf()
    assert len(cnf.clauses) < (80_000 if reified else 40_000)
    assert cnf.nv < (25_000 if reified else 13_000)


@pytest.mark.parametrize("mode", ["plain", "iff", "implies", "only_if"])
@pytest.mark.parametrize("nullable", [False, True])
def test_large_enum_all_different_collision_semantics(mode, nullable):
    import itertools
    from pysat.solvers import Solver
    from hermax.model import EnumVector

    m = Model()
    labels = ["a", "b", "c"] + [f"fixed{i}" for i in range(29)]
    items = [m.enum(f"x{i}", labels, nullable=nullable and i < 3) for i in range(32)]
    xs = EnumVector(m, "xs", items)
    for i, item in enumerate(items[3:]):
        m &= item == f"fixed{i}"
    flag = m.bool("flag")
    condition = xs.all_different()
    m &= condition if mode == "plain" else getattr(condition, mode)(flag)
    domain = ["a", "b", "c"] + ([None] if nullable else [])
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product(domain, repeat=3):
            truth = len(set(values)) == 3
            for enabled in (False, True):
                atoms = [item._none_indicator() if value is None else item == value
                         for item, value in zip(items, values)]
                atoms.append(flag if enabled else ~flag)
                expected = (truth if mode == "plain" else enabled == truth if mode == "iff"
                            else not truth or enabled if mode == "implies" else not enabled or truth)
                assert solver.solve(assumptions=[m._lit_to_dimacs(atom) for atom in atoms]) == expected


@pytest.mark.parametrize("mode", ["plain", "iff", "implies", "only_if"])
def test_mixed_integer_all_different_truth_table(mode):
    import itertools
    from pysat.solvers import Solver
    from hermax.model import IntVector

    m = Model()
    fixed = [m.int(f"fixed{i}", i, i) for i in range(29)]
    varying = [m.int("a", 29, 31), m.int("b", 30, 32), m.int("c", 29, 32)]
    xs = IntVector(m, "xs", fixed + varying)
    flag = m.bool("flag")
    condition = xs.all_different()
    m &= condition if mode == "plain" else getattr(condition, mode)(flag)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product(range(29, 32), range(30, 33), range(29, 33)):
            truth = len(set(values)) == 3
            for enabled in (False, True):
                atoms = [atom for x, value in zip(varying, values)
                         for atom in x._exact_value_atoms(value)]
                atoms.append(flag if enabled else ~flag)
                expected = (truth if mode == "plain" else truth == enabled if mode == "iff"
                            else not truth or enabled if mode == "implies" else not enabled or truth)
                assert solver.solve(assumptions=[m._lit_to_dimacs(atom) for atom in atoms]) == expected


def test_mixed_integer_all_different_skips_domain_gaps(monkeypatch):
    from hermax.model import IntVector
    from hermax.model import variables

    m = Model()
    xs = IntVector(m, "xs", [m.int(f"x{i}", (i // 2) * 10**9, (i // 2) * 10**9 + 1)
                             for i in range(32)])

    def short_range(*args):
        values = range(*args)
        assert len(values) <= 64, "all_different enumerated gaps between domains"
        return values

    monkeypatch.setattr(variables, "range", short_range, raising=False)
    flag = m.bool("flag")
    m &= xs.all_different().iff(flag)
    assert len(m.to_cnf().clauses) < 1000
    assert m.solve(assumptions=[flag]).ok
    assert m.solve(assumptions=[~flag]).ok


@pytest.mark.parametrize("reified", [False, True])
def test_mixed_integer_all_different_avoids_pairwise_growth(reified):
    from hermax.model import IntVector

    m = Model()
    xs = IntVector(m, "xs", [m.int(f"x{i}", 0, 100 + (i == 0)) for i in range(64)])
    condition = xs.all_different()
    m &= condition.iff(m.bool("flag")) if reified else condition
    assert len(m.to_cnf().clauses) < (120_000 if reified else 50_000)


def test_integer_all_different_two_owner_columns_need_no_auxiliaries():
    m = Model()
    xs = m.vector([m.int(f"x{i}", (i // 2) * 10, (i // 2) * 10 + 2)
                   for i in range(32)])
    baseline = m.to_cnf()
    top, clauses = baseline.nv, len(baseline.clauses)
    m &= xs.all_different()
    cnf = m.to_cnf()
    assert cnf.nv == top
    assert len(cnf.clauses) - clauses == 16 * 3


@pytest.mark.parametrize("repeated", [False, True])
@pytest.mark.parametrize("mode", ["plain", "iff", "implies", "only_if"])
def test_integer_all_different_two_owner_columns_truth_table(repeated, mode):
    import itertools
    from pysat.solvers import Solver

    m = Model()
    a = m.int("a", 0, 2)
    b = a if repeated else m.int("b", 0, 2)
    c, d = m.int("c", 4, 6), m.int("d", 4, 6)
    fixed = [m.int(f"fixed{i}", 20 + i, 20 + i) for i in range(28)]
    xs = m.vector([a, b, c, d, *fixed])
    flag = m.bool("flag")
    condition = xs.all_different()
    m &= condition if mode == "plain" else getattr(condition, mode)(flag)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for av, bv, cv, dv in itertools.product(range(3), range(3), range(4, 7), range(4, 7)):
            if repeated and av != bv:
                continue
            truth = av != bv and cv != dv
            atoms = [m._lit_to_dimacs(atom) for x, value in zip([a, b, c, d], [av, bv, cv, dv])
                     for atom in x._exact_value_atoms(value)]
            for enabled in (False, True):
                expected = (truth if mode == "plain" else truth == enabled if mode == "iff"
                            else not truth or enabled if mode == "implies" else not enabled or truth)
                assert solver.solve(assumptions=atoms + [flag.id if enabled else -flag.id]) == expected
