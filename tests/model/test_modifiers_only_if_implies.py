import pytest

from hermax.model import Clause, ClauseGroup, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable model, got status={r.status}"
    return r


def test_literal_only_if_enforces_target_when_condition_true():
    m = Model()
    a = m.bool("a")
    cond = m.bool("cond")

    m &= a.only_if(cond)
    m &= cond
    r = _solve_ok(m)
    assert r[cond] is True
    assert r[a] is True


def test_literal_only_if_does_not_enforce_target_when_condition_false():
    m = Model()
    a = m.bool("a")
    cond = m.bool("cond")

    m &= a.only_if(cond)
    m &= ~cond
    m &= ~a
    r = _solve_ok(m)
    assert r[cond] is False
    assert r[a] is False


def test_clause_only_if_enforces_disjunction_when_condition_true():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    cond = m.bool("cond")

    gated = (a | b).only_if(cond)
    assert isinstance(gated, Clause)

    m &= gated
    m &= cond
    m &= ~a
    r = _solve_ok(m)
    assert r[cond] is True
    assert r[a] is False
    assert r[b] is True


def test_clause_only_if_is_inactive_when_condition_false():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    cond = m.bool("cond")

    m &= (a | b).only_if(cond)
    m &= ~cond
    m &= ~a
    m &= ~b
    r = _solve_ok(m)
    assert r[cond] is False
    assert r[a] is False
    assert r[b] is False


def test_public_clausegroup_producer_only_if_gates_all_clauses():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    cond = m.bool("cond")

    # Public producer path: Clause.implies(Clause) returns ClauseGroup.
    group = (a | b).implies(b | c)
    gated = group.only_if(cond)
    assert isinstance(gated, ClauseGroup)
    assert len(gated.clauses) >= 1

    m &= gated
    m &= cond
    m &= a
    m &= ~b
    r = _solve_ok(m)
    # Under cond=true, the gated implication clauses are active. With a=false and
    # b=false, the implication forces c=true.
    assert r[c] is True


def test_literal_implies_literal_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a.implies(b)
    m &= a
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True


def test_literal_implies_clause_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    m &= a.implies(b | c)
    m &= a
    m &= ~b
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is False
    assert r[c] is True


def test_literal_implies_clausegroup_end_to_end():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    d = m.bool("d")

    target = ClauseGroup(m, [b | c, c | d])
    m &= a.implies(target)
    m &= a
    m &= ~c
    r = _solve_ok(m)
    # With a=true, target is enforced. Under ~c, both clauses reduce to b and d.
    assert r[b] is True
    assert r[d] is True


def test_clause_implies_literal_distributes_over_disjunction():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    t = m.bool("t")

    m &= (a | b).implies(t)
    m &= a
    r = _solve_ok(m)
    assert r[a] is True
    assert r[t] is True


def test_clause_implies_clause_returns_clausegroup_and_is_semantically_sound():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    out = (a | b).implies(c | b)
    assert isinstance(out, ClauseGroup)

    m &= out
    m &= a
    m &= ~b
    r = _solve_ok(m)
    assert r[c] is True


def test_pb_clausegroup_as_condition_is_rejected_in_only_if():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    with pytest.raises(TypeError, match="must be a Literal"):
        _ = (a | b).only_if(a + c <= 1)


def test_pb_clausegroup_as_source_is_rejected_in_implies():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    out = (a + b <= 1).implies(c)
    m &= out
    # If c is false and a+b <=1 holds, implication should fail.
    m &= ~c
    m &= ~a
    m &= ~b
    assert m.solve().status == "unsat"


def test_clausegroup_implies_is_rejected_detection_circuit_guardrail():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    group = ClauseGroup(m, [a | b])
    with pytest.raises(TypeError, match="must be a Literal"):
        _ = group.implies(c)


def test_pb_equality_antecedent_implies_literal_supported():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # (a+b == 1) -> c
    m &= (a + b == 1).implies(c)
    m &= ~c
    m &= a
    m &= ~b
    assert m.solve().status == "unsat"


def test_pb_equality_antecedent_implies_literal_chain_only_if_is_sound():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    gate = m.bool("gate")

    m &= (a + b == 1).implies(c).only_if(gate)
    m &= gate
    m &= ~c
    m &= a
    m &= ~b
    assert m.solve().status == "unsat"


def test_cross_model_checks_apply_to_modifiers_and_implications():
    m1 = Model()
    m2 = Model()
    a = m1.bool("a")
    b = m1.bool("b")
    c_other = m2.bool("c")

    with pytest.raises(ValueError, match="different models"):
        _ = a.only_if(c_other)

    with pytest.raises(ValueError, match="different models"):
        _ = (a | b).only_if(c_other)

    with pytest.raises(ValueError, match="different models"):
        _ = a.implies(c_other)


def test_chained_only_if_modifiers_accumulate_conditions_without_mutating_original():
    m = Model()
    a = m.bool("a")
    c1 = m.bool("c1")
    c2 = m.bool("c2")

    base = a
    gated1 = base.only_if(c1)
    gated2 = gated1.only_if(c2)

    # Original remains a literal; chained modifiers create new constraint objects.
    assert base is a
    assert isinstance(gated1, Clause)
    assert isinstance(gated2, Clause)
    assert gated1 is not gated2

    # Semantics: a.only_if(c1).only_if(c2) => (a or ~c1 or ~c2)
    m &= gated2
    m &= c1
    m &= c2
    r = _solve_ok(m)
    assert r[a] is True

    # If either condition is false, target should not be enforced.
    m2 = Model()
    x = m2.bool("x")
    d1 = m2.bool("d1")
    d2 = m2.bool("d2")
    m2 &= x.only_if(d1).only_if(d2)
    m2 &= d1
    m2 &= ~d2
    m2 &= ~x
    r2 = _solve_ok(m2)
    assert r2[x] is False
