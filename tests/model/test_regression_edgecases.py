import pytest

from pysat.examples.rc2 import RC2 as PySATRC2

from hermax.model import Clause, ClauseGroup, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_negative_coefficient_normalization_semantics_and_collapse():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # (a + b - b <= 0) should collapse to (a <= 0), i.e. force a = False.
    m &= (a + b - b <= 0)
    # (-2*a + 2*c >= 0) is equivalent to (~a + ~a + 2*c - 2 >= 0) after normalization,
    # but semantically here we only assert the solver respects the intended relation
    # under concrete pins.
    m &= c

    r = _solve_ok(m)
    assert r[a] is False
    assert r[c] is True


def test_strict_inequality_off_by_one_on_int_bounds():
    m1 = Model()
    x1 = m1.int("x1", lb=1, ub=5)  # {1,2,3,4}
    m1 &= (x1 < 1)
    assert m1.solve().status == "unsat"

    m2 = Model()
    x2 = m2.int("x2", lb=1, ub=5)
    m2 &= (x2 > 4)
    assert m2.solve().status == "unsat"

    m3 = Model()
    x3 = m3.int("x3", lb=1, ub=5)
    m3 &= (x3 < 2)
    r3 = _solve_ok(m3)
    assert r3[x3] == 1

    m4 = Model()
    x4 = m4.int("x4", lb=1, ub=5)
    m4 &= (x4 > 3)
    r4 = _solve_ok(m4)
    assert r4[x4] == 4


def test_constant_only_pb_comparators_semantics_and_export_constants():
    # Semantically constant expressions arising from cancellation should work
    # and materialize internal constants.
    m = Model()
    a = m.bool("a")
    m &= (a - a <= 0)   # always true after collapse
    m &= (a - a == 0)   # always true after collapse
    r = _solve_ok(m)
    assert r.ok is True

    cnf = m.to_cnf()
    assert "__true" in m._registry
    t = m._registry["__true"].id
    # __true definition and at least one use should be present.
    hard = [tuple(cl) for cl in cnf.clauses]
    assert (t,) in hard

    m_bad = Model()
    b = m_bad.bool("b")
    m_bad &= (b - b < 0)  # always false after collapse
    assert m_bad.solve().status == "unsat"
    assert "__false" in m_bad._registry


def test_aux_id_generation_after_many_anonymous_vars_and_encoder_auxiliaries():
    m = Model()
    anon = [m.bool() for _ in range(40)]
    top_before = max(v.id for v in anon)

    # Force encoder aux vars (cardinality equality over many vars usually introduces aux vars).
    m &= (sum(anon) == 7)

    top_after_encoder = m._top_id()
    assert top_after_encoder >= top_before

    # New user variable IDs must continue monotonic allocation after encoder aux IDs.
    z = m.bool("z")
    assert z.id == top_after_encoder + 1

    # Sanity solve to ensure the generated constraints are usable.
    m &= z
    r = _solve_ok(m)
    assert r[z] is True


def test_objective_iadd_python_protocol_regressions_accumulate_exactly_once():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Exercise Python's obj[key] += protocol repeatedly on the same bucket.
    m.obj[3] += a
    m.obj[3] += b
    m.obj[3] += (a | b)

    # Exactly three soft entries should be present, each with the same weight.
    assert len(m._soft) == 3
    assert [w for (w, _c) in m._soft] == [3, 3, 3]

    # Solvable and cost-checkable.
    r = _solve_ok(m)
    wcnf = m.to_wcnf()
    with PySATRC2(wcnf) as rc2:
        raw = rc2.compute()
        assert raw is not None
        assert int(rc2.cost) == r.cost


def test_empty_and_tautological_clauses_in_clausegroup_if_exposed_behave_transparently():
    m = Model()
    a = m.bool("a")

    # Tautological hard clause should not constrain the model.
    taut = Clause(m, [a, ~a])
    m &= ClauseGroup(m, [taut])
    r = _solve_ok(m)
    assert r.ok is True

    # Empty hard clause makes the model UNSAT.
    m2 = Model()
    empty = Clause(m2, [])
    m2 &= ClauseGroup(m2, [empty])
    assert m2.solve().status == "unsat"

    # Empty soft clause is an unavoidable penalty and should be representable at export level.
    m3 = Model()
    m3.obj[5] += ClauseGroup(m3, [Clause(m3, [])])
    wcnf = m3.to_wcnf()
    assert [] in [list(cl) for cl in wcnf.soft]
    # Do not solve here: RC2 may reject direct empty soft clauses. This regression check
    # intentionally locks export transparency only.


def test_decode_partial_or_underspecified_solver_model_is_stable():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    x = m.int("x", lb=1, ub=5)  # {1,2,3,4}
    color = m.enum("color", choices=["r", "g"], nullable=True)

    # Partial raw model: only sets a, one threshold bit for x, and no enum choice.
    raw = [a.id, x._threshold_lits[0].id]
    dv = m.decode_model(raw)

    assert dv[a] is True
    assert dv[b] is False  # default false when unspecified
    # One threshold true => value = lb + 1
    assert dv[x] == 2
    assert dv[color] is None


def test_decode_partial_model_prefers_exact_int_equality_literal_when_present():
    m = Model()
    x = m.int("x", lb=0, ub=4)  # {0,1,2,3}
    eq2 = (x == 2)
    # Underspecified / inconsistent raw model: threshold bits suggest maybe another value,
    # but equality literal is present. Decoder should prefer exact equality literals.
    raw = [eq2.id, x._threshold_lits[0].id, x._threshold_lits[1].id, x._threshold_lits[2].id]
    dv = m.decode_model(raw)
    assert dv[x] == 2


def test_int_indicator_construction_respects_holding_tank_and_does_not_eagerly_mutate_model():
    m = Model()
    x = m.int("x", lb=0, ub=8)
    y = m.int("y", lb=0, ub=8)

    hard_before = len(m._hard)

    # Pure construction of indicator/equality literals should not inject hard clauses
    # into the global model before the user adds a constraint explicitly.
    eq_val = (x == 5)
    neq_xy = x._neq_indicator(y)
    eq_xy = x._eq_indicator(y)

    assert eq_val is not None
    assert neq_xy is not None
    assert eq_xy is not None
    assert len(m._hard) == hard_before

    # Once the user adds a constraint, growth is expected.
    m &= eq_val
    assert len(m._hard) >= hard_before + 1


def test_int_scalar_relation_literal_construction_does_not_eagerly_mutate_model():
    m = Model()
    x = m.int("x", lb=0, ub=8)
    hard_before = len(m._hard)

    # Scalar compare literals are stage-1 objects and should not inject helper clauses.
    lits = [x <= 3, x < 4, x >= 2, x > 1, x == 4, x != 4]
    assert all(l is not None for l in lits)
    assert len(m._hard) == hard_before


def test_intvector_neq_clause_construction_does_not_eagerly_mutate_model():
    m = Model()
    v1 = m.int_vector("v1", length=3, lb=0, ub=6)
    v2 = m.int_vector("v2", length=3, lb=0, ub=6)
    hard_before = len(m._hard)

    diff_clause = (v1 != v2)
    assert isinstance(diff_clause, Clause)
    assert len(m._hard) == hard_before


def test_intvector_table_constraint_construction_does_not_eagerly_mutate_model():
    m = Model()
    spec = m.int_vector("spec", length=3, lb=0, ub=6)
    hard_before = len(m._hard)

    table = spec.is_in([(1, 2, 1), (2, 4, 2), (3, 4, 3)])
    assert isinstance(table, ClauseGroup)
    assert len(m._hard) == hard_before


def test_multiplexer_constraint_construction_does_not_eagerly_mutate_model():
    # Constant RHS case
    m1 = Model()
    w1 = m1.int("w", lb=0, ub=4)
    hard_before_1 = len(m1._hard)
    c1 = ([10, 20, 30, 40] @ w1 <= 25)
    assert isinstance(c1, ClauseGroup)
    assert len(m1._hard) == hard_before_1

    # IntVar RHS case
    m2 = Model()
    w2 = m2.int("w", lb=0, ub=4)
    b2 = m2.int("budget", lb=0, ub=100)
    hard_before_2 = len(m2._hard)
    c2 = ([10, 20, 30, 40] @ w2 <= b2)
    assert isinstance(c2, ClauseGroup)
    assert len(m2._hard) == hard_before_2
