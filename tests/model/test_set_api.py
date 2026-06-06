from __future__ import annotations

import random

import pytest

from hermax.model import ClauseGroup, IntSetDict, IntSetVar, IntSetVector, Literal, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_int_set_declaration_range_and_explicit_values():
    m = Model()
    s = m.int_set("s", lb=1, ub=3)
    t = m.int_set("t", values=[5, 3, 5])

    assert isinstance(s, IntSetVar)
    assert isinstance(t, IntSetVar)
    assert s.name == "s"
    assert t.name == "t"
    assert s.universe == (1, 2, 3)
    assert t.universe == (3, 5)
    assert all(isinstance(s.contains(v), Literal) for v in s.universe)


def test_int_set_declaration_rejects_invalid_signatures():
    m = Model()
    with pytest.raises(ValueError, match="exactly one"):
        m.int_set("x")
    with pytest.raises(ValueError, match="exactly one"):
        m.int_set("x2", lb=0, ub=3, values=[1, 2])
    with pytest.raises(TypeError, match="integers"):
        m.int_set("x3", values=[1, 2.5])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="lb <= ub"):
        m.int_set("x4", lb=3, ub=2)


def test_int_set_contains_outside_universe_is_false_constant():
    m = Model()
    s = m.int_set("s", lb=2, ub=4)
    outside = s.contains(1)
    assert outside is m._get_bool_constant_literal(False)


def test_int_set_constant_equality_and_decode():
    m = Model()
    s = m.int_set("s", lb=1, ub=4)
    m &= (s == {1, 3})
    r = _solve_ok(m)
    assert r[s] == {1, 3}


def test_int_set_constant_equality_outside_domain_is_unsat():
    m = Model()
    s = m.int_set("s", lb=1, ub=4)
    m &= (s == {1, 5})
    r = m.solve()
    assert r.status == "unsat"


def test_int_set_subset_and_superset_semantics():
    m = Model()
    a = m.int_set("a", lb=1, ub=3)
    b = m.int_set("b", lb=1, ub=3)
    m &= (a == {1})
    m &= (b == {1, 2})
    m &= a.subset_of(b)
    m &= b.superset_of(a)
    r = _solve_ok(m)
    assert r[a] == {1}
    assert r[b] == {1, 2}

    m_bad = Model()
    a_bad = m_bad.int_set("a", lb=1, ub=3)
    b_bad = m_bad.int_set("b", lb=1, ub=3)
    m_bad &= (a_bad == {1})
    m_bad &= (b_bad == {2})
    m_bad &= a_bad.subset_of(b_bad)
    assert m_bad.solve().status == "unsat"


def test_int_set_subset_and_superset_reject_non_set_rhs():
    m = Model()
    s = m.int_set("s", lb=1, ub=3)

    with pytest.raises(TypeError, match="IntSetVar"):
        s.subset_of(object())

    with pytest.raises(TypeError, match="IntSetVar"):
        s.superset_of(object())


def test_int_set_subset_and_superset_match_python_inclusion_on_random_universes():
    rng = random.Random(41)

    for case in range(18):
        left_universe = sorted({rng.randint(0, 7) for _ in range(rng.randint(2, 5))})
        right_universe = sorted({rng.randint(0, 7) for _ in range(rng.randint(2, 5))})
        if not left_universe:
            left_universe = [0, 1]
        if not right_universe:
            right_universe = [0, 1]
        left_values = {v for v in left_universe if rng.randrange(2)}
        right_values = {v for v in right_universe if rng.randrange(2)}

        m_sub = Model()
        a_sub = m_sub.int_set(f"a_sub_{case}", values=left_universe)
        b_sub = m_sub.int_set(f"b_sub_{case}", values=right_universe)
        m_sub &= (a_sub == left_values)
        m_sub &= (b_sub == right_values)
        m_sub &= a_sub.subset_of(b_sub)
        assert m_sub.solve().status == ("sat" if left_values <= right_values else "unsat")

        m_sup = Model()
        a_sup = m_sup.int_set(f"a_sup_{case}", values=left_universe)
        b_sup = m_sup.int_set(f"b_sup_{case}", values=right_universe)
        m_sup &= (a_sup == left_values)
        m_sup &= (b_sup == right_values)
        m_sup &= a_sup.superset_of(b_sup)
        assert m_sup.solve().status == ("sat" if left_values >= right_values else "unsat")


def test_int_set_inequality_semantics_with_set_and_constant_rhs():
    m = Model()
    a = m.int_set("a", lb=1, ub=3)
    b = m.int_set("b", lb=1, ub=3)
    m &= (a == {1, 2})
    m &= (b == {1, 2})
    m &= (a != b)
    assert m.solve().status == "unsat"

    m2 = Model()
    s = m2.int_set("s", lb=1, ub=3)
    m2 &= (s == {1})
    m2 &= (s != {1})
    assert m2.solve().status == "unsat"


def test_int_set_inequality_with_outside_value_is_always_satisfied():
    m = Model()
    s = m.int_set("s", lb=1, ub=3)
    m &= (s == {2})
    m &= (s != {2, 5})
    r = _solve_ok(m)
    assert r[s] == {2}


def test_int_set_cardinality_expr_and_card_helper_variable():
    m = Model()
    s = m.int_set("s", lb=1, ub=4)
    k = s.card(name="k")
    m &= (s == {1, 4})
    m &= (k == 2)
    r = _solve_ok(m)
    assert r[s] == {1, 4}
    assert r[k] == 2

    m_bad = Model()
    s_bad = m_bad.int_set("s", lb=1, ub=4)
    k_bad = m_bad.int("k", lb=0, ub=5)
    m_bad &= (s_bad == {1, 4})
    m_bad &= (s_bad.cardinality() == k_bad)
    m_bad &= (k_bad == 3)
    assert m_bad.solve().status == "unsat"


def test_int_set_card_does_not_eagerly_mutate_model():
    """Calling card() without adding it to the model must not commit binding clauses.

    model.int() itself emits O(n) ladder-ordering axioms (inherent to IntVar
    creation). What must NOT be emitted eagerly are the sorting-network
    clauses that bind the set membership bits to the cardinality variable.
    We check that no *extra* clauses beyond bare IntVar construction are added.
    """
    m = Model()
    s = m.int_set("s", lb=1, ub=4)
    universe_size = len(s.universe)   # 4

    # Capture how many clauses a bare model.int() of the same domain adds.
    baseline_m = Model()
    _baseline_var = baseline_m.int("baseline", lb=0, ub=universe_size)
    expected_domain_clauses = len(baseline_m._hard)  # ladder-ordering axioms only

    hard_before = len(m._hard)
    _k = s.card()   # result discarded
    actual_delta = len(m._hard) - hard_before

    assert actual_delta == expected_domain_clauses, (
        f"card() committed {actual_delta} clauses but only "
        f"{expected_domain_clauses} ladder-ordering axioms are expected from model.int(). "
        f"Sorting-network binding clauses must be registered lazily."
    )



def test_int_set_contains_intvar_indicator_semantics_exhaustive_small_domain():
    for xv in range(0, 6):
        truth = xv in {1, 3, 4}

        m_in = Model()
        s_in = m_in.int_set("s", values=[1, 3, 4])
        x_in = m_in.int("x", lb=0, ub=6)  # 0..5
        b_in = s_in.contains(x_in)
        m_in &= (x_in == xv)
        m_in &= b_in
        assert (m_in.solve().status != "unsat") is truth

        m_out = Model()
        s_out = m_out.int_set("s", values=[1, 3, 4])
        x_out = m_out.int("x", lb=0, ub=6)
        b_out = s_out.contains(x_out)
        m_out &= (x_out == xv)
        m_out &= ~b_out
        assert (m_out.solve().status != "unsat") is (not truth)


def test_int_set_algebra_union_intersection_difference_symdiff():
    m = Model()
    a = m.int_set("a", lb=1, ub=4)
    b = m.int_set("b", lb=1, ub=4)
    u = a | b
    i = a & b
    d = a - b
    x = a ^ b

    assert isinstance(a == b, ClauseGroup)

    m &= (a == {1, 2})
    m &= (b == {2, 3})
    m &= (u == {1, 2, 3})
    m &= (i == {2})
    m &= (d == {1})
    m &= (x == {1, 3})

    r = _solve_ok(m)
    assert r[a] == {1, 2}
    assert r[b] == {2, 3}
    assert r[u] == {1, 2, 3}
    assert r[i] == {2}
    assert r[d] == {1}
    assert r[x] == {1, 3}


def test_int_set_randomized_set_ops_cardinality_and_inequality():
    rng = random.Random(0)

    for case in range(20):
        universe = tuple(range(1, rng.randint(3, 6)))
        lhs_vals = {v for v in universe if rng.randrange(2)}
        rhs_vals = {v for v in universe if rng.randrange(2)}
        outside = max(universe) + 1

        m = Model()
        a = m.int_set(f"a_{case}", values=universe)
        b = m.int_set(f"b_{case}", values=universe)
        u = a | b
        i = a & b
        d = a - b
        x = a ^ b
        k = a.card(name=f"k_{case}")

        m &= (a == lhs_vals)
        m &= (b == rhs_vals)
        m &= (u == (lhs_vals | rhs_vals))
        m &= (i == (lhs_vals & rhs_vals))
        m &= (d == (lhs_vals - rhs_vals))
        m &= (x == (lhs_vals ^ rhs_vals))
        m &= (k == len(lhs_vals))
        m &= (a != {outside})
        if lhs_vals != rhs_vals:
            m &= (a != b)
            m &= (a != rhs_vals)

        r = _solve_ok(m)
        assert r[a] == lhs_vals
        assert r[b] == rhs_vals
        assert r[u] == (lhs_vals | rhs_vals)
        assert r[i] == (lhs_vals & rhs_vals)
        assert r[d] == (lhs_vals - rhs_vals)
        assert r[x] == (lhs_vals ^ rhs_vals)
        assert r[k] == len(lhs_vals)

        m_eq = Model()
        a_eq = m_eq.int_set(f"a_eq_{case}", values=universe)
        b_eq = m_eq.int_set(f"b_eq_{case}", values=universe)
        m_eq &= (a_eq == lhs_vals)
        m_eq &= (b_eq == rhs_vals)
        m_eq &= (a_eq != b_eq)
        assert m_eq.solve().status == ("unsat" if lhs_vals == rhs_vals else "sat")

        m_const = Model()
        a_const = m_const.int_set(f"a_const_{case}", values=universe)
        m_const &= (a_const == lhs_vals)
        m_const &= (a_const != rhs_vals)
        assert m_const.solve().status == ("unsat" if lhs_vals == rhs_vals else "sat")


def test_int_set_vector_and_dict_typed_construction_and_decode():
    m = Model()
    sv = m.int_set_vector("sv", length=2, lb=1, ub=3)
    sd = m.int_set_dict("sd", keys=["a", "b"], lb=1, ub=3)

    assert isinstance(sv, IntSetVector)
    assert isinstance(sd, IntSetDict)

    m &= (sv[0] == {1})
    m &= (sv[1] == {2, 3})
    m &= (sd["a"] == {2})
    m &= (sd["b"] == set())

    r = _solve_ok(m)
    assert r[sv] == [{1}, {2, 3}]
    assert r[sd] == {"a": {2}, "b": set()}
