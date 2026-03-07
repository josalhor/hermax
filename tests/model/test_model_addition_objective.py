import pytest

from hermax.model import ClauseGroup, Model


def _solve(m: Model):
    return m.solve()


def _solve_ok(m: Model):
    r = _solve(m)
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_model_iand_accepts_literal_clause_and_clausegroup_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    m &= a                   # unit hard
    m &= (~a | b)            # clause hard, forces b
    m &= a.implies(c)        # ClauseGroup hard, with a=true forces c

    r = _solve_ok(m)
    assert r.status == "sat"
    assert r[a] is True
    assert r[b] is True
    assert r[c] is True


def test_model_iand_true_is_noop_and_false_makes_unsat():
    m1 = Model()
    a = m1.bool("a")
    m1 &= True
    m1 &= a
    r1 = _solve_ok(m1)
    assert r1[a] is True

    m2 = Model()
    b = m2.bool("b")
    m2 &= False
    m2 &= b
    r2 = _solve(m2)
    assert r2.status == "unsat"


def test_objective_rejects_invalid_weights():
    m = Model()
    a = m.bool("a")

    with pytest.raises(ValueError, match="positive int"):
        m.obj[0] += a

    with pytest.raises(ValueError, match="positive int"):
        m.obj[-1] += a

    with pytest.raises(ValueError, match="positive int"):
        m.obj[1.5] += a


def test_objective_soft_literal_and_clause_choose_min_cost_assignment():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Pay 5 if a is false. Pay 2 if b is true (soft clause ~b violated when b=true).
    m.obj[5] += a
    m.obj[2] += ~b

    r = _solve_ok(m)
    assert r.status == "optimum"
    assert r.cost == 0
    assert r[a] is True
    assert r[b] is False


def test_objective_repeated_weight_bucket_accumulates_multiple_soft_clauses():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Force both soft clauses to be violated.
    m &= ~a
    m &= b

    m.obj[3] += a     # violated because a=false => +3
    m.obj[3] += ~b    # violated because b=true  => +3

    r = _solve_ok(m)
    assert r.status == "optimum"
    assert r.cost == 6
    assert r[a] is False
    assert r[b] is True


def test_objective_accepts_clausegroup_from_public_producer_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # Public ClauseGroup producer: Clause.implies(Clause)
    group = (a | b).implies(c | b)
    assert isinstance(group, ClauseGroup)

    # Force a=true and b=false so the generated clauses make c mandatory.
    m &= a
    m &= ~b
    m.obj[7] += group

    # To avoid cost, solver should satisfy the whole group and set c=true.
    r = _solve_ok(m)
    assert r.status == "optimum"
    assert r.cost == 0
    assert r[c] is True


def test_objective_soft_pb_clausegroup_penalizes_violation_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # PB comparator finalizes to ClauseGroup. Force a=b=true so (a+b<=1) is violated.
    m &= a
    m &= b
    m.obj[10] += (a + b <= 1)

    r = _solve_ok(m)
    assert r.status == "optimum"
    assert r[a] is True
    assert r[b] is True
    assert r.cost == 10


def test_objective_true_is_noop_and_false_adds_unavoidable_cost():
    m = Model()
    a = m.bool("a")

    m &= a
    m.obj[4] += True   # no-op
    m.obj[9] += False  # empty soft clause: always violated => unavoidable cost

    r = _solve_ok(m)
    assert r.status == "optimum"
    assert r[a] is True
    assert r.cost == 9


def test_empty_clausegroup_addition_is_noop_for_hard_and_soft():
    m = Model()
    a = m.bool("a")
    empty = ClauseGroup(m, [])

    m &= empty
    m.obj[5] += empty
    m &= a

    r = _solve_ok(m)
    assert r.status == "optimum" if m.to_wcnf().soft else "sat"
    # Current model has no soft clauses because empty group contributes none.
    assert r.status == "sat"
    assert r[a] is True
    assert r.cost is None


def test_internal_hard_soft_storage_invariants_preserve_clause_shapes_and_weights():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # Hard additions through all accepted public entry shapes.
    m &= a
    m &= (~a | b)
    cg = (a | b).implies(c | b)  # public ClauseGroup producer
    m &= cg

    # Soft additions through literal, clause, and ClauseGroup.
    m.obj[5] += ~c
    m.obj[7] += (a | ~b)
    m.obj[11] += (a + b <= 1)  # PB comparator finalizes to ClauseGroup

    # Hard storage invariants.
    assert isinstance(m._hard, list)
    assert all(hasattr(cl, "literals") for cl in m._hard)
    # unit a + one clause + all clauses from the ClauseGroup
    assert len(m._hard) == 2 + len(cg.clauses)
    assert [m._lit_to_dimacs(l) for l in m._hard[0].literals] == [a.id]
    assert [m._lit_to_dimacs(l) for l in m._hard[1].literals] == [-a.id, b.id]

    # Soft storage invariants.
    assert isinstance(m._soft, list)
    assert all(isinstance(w, int) and w > 0 for w, _cl in m._soft)
    assert all(hasattr(cl, "literals") for _w, cl in m._soft)
    # literal + clause + expanded PB ClauseGroup (one or more clauses)
    assert len(m._soft) >= 3
    weights = [w for w, _cl in m._soft]
    assert 5 in weights and 7 in weights and 11 in weights

    # The literal and clause softs should be preserved exactly as unit/clause entries.
    soft_dimacs = [([m._lit_to_dimacs(l) for l in cl.literals], w) for w, cl in m._soft]
    assert ([-c.id], 5) in soft_dimacs
    assert ([a.id, -b.id], 7) in soft_dimacs

    # End-to-end sanity: storage state solves and returns a consistent optimum.
    r = _solve_ok(m)
    assert r.status == "optimum"


def test_soft_pbconstraint_requires_targeted_relaxation_single_penalty():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    pb = (a + b + c <= 1)
    compiled = pb.clauses()
    assert len(compiled.clauses) >= 1

    m.obj[100] += pb

    soft_100 = [cl for (w, cl) in m._soft if w == 100]
    assert len(soft_100) == 1, (
        "PB soft constraints should use targeted relaxation (one weighted soft "
        "penalty), not clausewise softening of the compiled PB network."
    )


def test_objective_accepts_intvar_and_lowers_to_weighted_threshold_softs():
    m = Model()
    x = m.int("x", lb=0, ub=5)  # values 0..4, threshold width = 5

    m.obj[3] += x

    # x = sum(threshold_bits) for lb=0, so we expect one soft (~t) per threshold bit.
    assert len(m._soft) == len(x._threshold_lits)
    soft_dimacs = [([m._lit_to_dimacs(l) for l in cl.literals], w) for (w, cl) in m._soft]
    for t in x._threshold_lits:
        assert ([-t.id], 3) in soft_dimacs

    # Unconstrained minimization should choose x=0 with zero cost.
    r = _solve_ok(m)
    assert r.status == "optimum"
    assert r[x] == 0
    assert r.cost == 0


def test_objective_intvar_cost_includes_lower_bound_constant_offset():
    m = Model()
    x = m.int("x", lb=3, ub=7)  # values 3..6
    m.obj[2] += x

    # True optimum should be x=3, cost = 2*3 = 6.
    r = _solve_ok(m)
    assert r.status == "optimum"
    assert r[x] == 3
    assert r.cost == 6


def test_objective_intvar_negative_lower_bound_is_rejected_for_now():
    m = Model()
    x = m.int("x", lb=-2, ub=3)  # values -2..2
    with pytest.raises(ValueError, match="lb >= 0|negative objective offsets"):
        m.obj[5] += x


def test_objective_intvar_and_manual_threshold_soft_encoding_agree_on_argmin_and_cost():
    m1 = Model()
    x1 = m1.int("x", lb=1, ub=6)
    m1 &= (x1 >= 3)
    m1.obj[4] += x1
    r1 = _solve_ok(m1)

    m2 = Model()
    x2 = m2.int("x", lb=1, ub=6)
    m2 &= (x2 >= 3)
    # Manual equivalent: constant offset + weighted threshold penalties.
    for t in x2._threshold_lits:
        m2.obj[4] += ~t
    m2._objective_constant += 4 * x2.lb
    r2 = _solve_ok(m2)

    assert r1[x1] == r2[x2]
    assert r1.cost == r2.cost
