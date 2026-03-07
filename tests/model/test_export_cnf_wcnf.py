import pytest

from pysat.examples.rc2 import RC2
from pysat.solvers import Solver as PySATSolver

from hermax.model import Model


def _solve_cnf(cnf, solver_name="g4"):
    with PySATSolver(name=solver_name) as s:
        s.append_formula(cnf.clauses)
        sat = s.solve()
        return sat, (s.get_model() or [])


def _solve_wcnf(wcnf):
    with RC2(wcnf) as rc2:
        model = rc2.compute()
        if model is None:
            return None, None
        return list(model), int(rc2.cost)


def test_to_cnf_hard_only_roundtrip_solver_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # a and (~a or b) force b. c remains free.
    m &= a
    m &= (~a | b)

    cnf = m.to_cnf()
    sat, raw = _solve_cnf(cnf)
    assert sat is True

    dec = m.decode_model(raw)
    assert dec[a] is True
    assert dec[b] is True
    # c is unconstrained; only assert decode is boolean.
    assert isinstance(dec[c], bool)


def test_to_cnf_basic_clause_translation_and_variable_ids_are_exact():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    assert (a.id, b.id, c.id) == (1, 2, 3)

    m &= a
    m &= (~a | b)
    m &= (b | ~c)

    cnf = m.to_cnf()
    assert cnf.clauses == [[1], [-1, 2], [2, -3]]
    assert cnf.nv == 3


def test_to_cnf_rejects_soft_model_even_if_soft_is_boolean_constant():
    m = Model()
    a = m.bool("a")
    m &= a
    m.obj[7] += False

    with pytest.raises(ValueError, match="soft clauses"):
        m.to_cnf()


def test_to_wcnf_roundtrip_rc2_matches_model_solve_cost_and_assignment_on_simple_case():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Prefer a=true, b=false.
    m.obj[5] += a
    m.obj[2] += ~b

    wcnf = m.to_wcnf()
    raw_w, cost_w = _solve_wcnf(wcnf)
    assert raw_w is not None
    assert cost_w == 0

    dec = m.decode_model(raw_w)
    assert dec[a] is True
    assert dec[b] is False

    r = m.solve()
    assert r.status == "optimum"
    assert r.cost == cost_w
    assert r[a] == dec[a]
    assert r[b] == dec[b]


def test_to_wcnf_soft_pb_clausegroup_roundtrip_cost_is_preserved():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Force violation of (a+b<=1) and penalize it.
    m &= a
    m &= b
    m.obj[10] += (a + b <= 1)

    wcnf = m.to_wcnf()
    raw_w, cost_w = _solve_wcnf(wcnf)
    assert raw_w is not None
    assert cost_w == 10

    dec = m.decode_model(raw_w)
    assert dec[a] is True
    assert dec[b] is True


def test_to_wcnf_boolean_constants_export_as_regular_soft_and_hard_clauses():
    m = Model()
    x = m.bool("x")

    m &= True
    m &= x
    m.obj[4] += True
    m.obj[9] += False

    wcnf = m.to_wcnf()
    # Hard should include x plus definitions/uses for __true/__false.
    assert len(wcnf.hard) >= 3
    # Soft should include two unit clauses (for __true and __false).
    assert len(wcnf.soft) == 2

    raw_w, cost_w = _solve_wcnf(wcnf)
    assert raw_w is not None
    assert cost_w == 9

    dec = m.decode_model(raw_w)
    assert dec[x] is True


def test_boolean_constants_materialize_internal_reserved_vars_and_expected_clauses():
    m = Model()
    x = m.bool("x")
    m &= x
    m &= True
    m.obj[4] += True
    m.obj[9] += False

    # Internal constants should exist and be reserved-style names.
    assert "__true" in m._registry
    assert "__false" in m._registry
    t = m._registry["__true"]
    f = m._registry["__false"]
    assert t.id > x.id
    assert f.id > t.id

    w = m.to_wcnf()

    # Hard clauses:
    # [x]
    # [__true] definition (forced true)
    # [__true] user-added hard True
    # [~__false] definition may be absent until False used as hard; here only soft False is used,
    # but creating __false still installs the hard definition.
    hard_set = {tuple(cl) for cl in w.hard}
    assert (x.id,) in hard_set
    assert (t.id,) in hard_set
    assert (-f.id,) in hard_set

    # Soft clauses are plain unit clauses over the constants.
    soft_with_w = list(zip(w.soft, w.wght))
    assert ([t.id], 4) in soft_with_w
    assert ([f.id], 9) in soft_with_w


def test_bool_vector_instantiation_allocates_ids_but_emits_no_clauses():
    m = Model()
    bv = m.bool_vector("bv", length=3)

    assert [lit.id for lit in bv] == [1, 2, 3]

    cnf = m.to_cnf()
    w = m.to_wcnf()
    assert cnf.clauses == []
    assert w.hard == []
    assert w.soft == []


def test_enum_instantiation_emits_exactly_one_domain_clauses_in_expected_shape():
    m = Model()
    color = m.enum("color", choices=["r", "g", "b"], nullable=False)

    r = color._choice_lits["r"]
    g = color._choice_lits["g"]
    b = color._choice_lits["b"]
    assert [r.id, g.id, b.id] == [1, 2, 3]

    cnf = m.to_cnf()
    hard = {tuple(cl) for cl in cnf.clauses}

    # Pairwise AMO + one ALO = EO over 3 values.
    expected = {
        (-r.id, -g.id),
        (-r.id, -b.id),
        (-g.id, -b.id),
        (r.id, g.id, b.id),
    }
    assert hard == expected


def test_nullable_enum_instantiation_emits_only_amo_without_alo():
    m = Model()
    color = m.enum("color", choices=["r", "g", "b"], nullable=True)
    r = color._choice_lits["r"]
    g = color._choice_lits["g"]
    b = color._choice_lits["b"]

    cnf = m.to_cnf()
    hard = {tuple(cl) for cl in cnf.clauses}
    expected = {
        (-r.id, -g.id),
        (-r.id, -b.id),
        (-g.id, -b.id),
    }
    assert hard == expected


def test_int_instantiation_emits_ladder_domain_clauses_in_expected_shape():
    m = Model()
    speed = m.int("speed", lb=0, ub=4)  # compact ladder => span-1=3 threshold lits
    ts = speed._threshold_lits
    assert [t.id for t in ts] == [1, 2, 3]

    cnf = m.to_cnf()
    hard = {tuple(cl) for cl in cnf.clauses}
    expected = {
        (-ts[1].id, ts[0].id),   # t1 -> t0
        (-ts[2].id, ts[1].id),   # t2 -> t1
    }
    assert hard == expected


def test_mixed_container_instantiation_allocates_monotonic_noncolliding_ids():
    m = Model()
    bv = m.bool_vector("bv", length=3)
    iv = m.int_vector("iv", length=2, lb=0, ub=5)          # 2 * 4 threshold lits
    ev = m.enum_vector("ev", length=2, choices=["r", "g"])  # 2 * 2 choice lits
    mat = m.int_matrix("mat", rows=2, cols=2, lb=0, ub=3)    # 4 * 2 threshold lits

    ids = []
    ids.extend([lit.id for lit in bv])  # 3
    for cell in iv:
        ids.extend([lit.id for lit in cell._threshold_lits])  # 8
    for enum_cell in ev:
        ids.extend([lit.id for lit in enum_cell._choice_lits.values()])  # 4
    for r in range(2):
        for c in range(2):
            ids.extend([lit.id for lit in mat._grid[r][c]._threshold_lits])  # 8

    assert len(ids) == 3 + 8 + 4 + 8
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    assert ids[0] == 1
    assert ids[-1] == len(ids)


def test_export_is_stable_across_repeated_calls_without_mutation():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a | b)
    m.obj[3] += ~a

    w1 = m.to_wcnf()
    w2 = m.to_wcnf()

    assert w1.hard == w2.hard
    assert w1.soft == w2.soft
    assert w1.wght == w2.wght

    raw1, cost1 = _solve_wcnf(w1)
    raw2, cost2 = _solve_wcnf(w2)
    assert cost1 == cost2
    assert m.decode_model(raw1 or [])[a] == m.decode_model(raw2 or [])[a]
    assert m.decode_model(raw1 or [])[b] == m.decode_model(raw2 or [])[b]


def test_export_after_encoder_generated_aux_variables_remains_solveable():
    m = Model()
    xs = [m.bool(f"x{i}") for i in range(4)]

    # Force encoder-generated aux vars via cardinality and PB paths.
    m &= (xs[0] + xs[1] + xs[2] <= 1)
    m &= (2 * xs[1] + 3 * xs[3] >= 2)
    m &= xs[0]

    w = m.to_wcnf()
    raw, cost = _solve_wcnf(w)
    assert raw is not None
    assert cost == 0

    dec = m.decode_model(raw)
    assert dec[xs[0]] is True


def test_to_cnf_then_model_solve_agree_on_unsat_hard_only_case():
    m = Model()
    a = m.bool("a")
    m &= a
    m &= ~a

    cnf = m.to_cnf()
    sat, _raw = _solve_cnf(cnf)
    assert sat is False

    r = m.solve()
    assert r.status == "unsat"
