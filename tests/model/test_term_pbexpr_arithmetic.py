import pytest
import random

from hermax.model import Model, PBExpr, Term


def _solve(m: Model):
    return m.solve()


def _solve_ok(m: Model):
    r = _solve(m)
    assert r.ok, f"expected satisfiable model, got status={r.status}"
    return r


def test_integer_scaling_of_literal_is_semantically_respected():
    m = Model()
    a = m.bool("a")

    # 3*a >= 2 forces a to be true.
    m &= (3 * a >= 2)
    r = _solve_ok(m)
    assert r[a] is True


def test_weighted_pb_term_arithmetic_with_rmul_and_mul_match_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # If a is true, 2*a + 3*b <= 2 forces b=false.
    m &= a
    m &= (2 * a + b * 3 <= 2)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is False


def test_pbexpr_addition_and_subtraction_handle_negative_terms_via_solving():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # a + b - c <= 1 with a=b=true forces c=true.
    m &= a
    m &= b
    m &= (a + b - c <= 1)
    r = _solve_ok(m)
    assert r[c] is True


def test_pbexpr_offsets_are_allowed_and_preserve_expected_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # +0/-0 should be accepted (important for folds like sum(...)).
    m &= (a + b + 0 - 0 <= 0)
    r = _solve_ok(m)
    assert r[a] is False
    assert r[b] is False

    # a + b + 1 <= 1  <=> a + b <= 0
    m2 = Model()
    x = m2.bool("x")
    y = m2.bool("y")
    m2 &= (x + y + 1 <= 1)
    r2 = _solve_ok(m2)
    assert r2[x] is False
    assert r2[y] is False

    m3 = Model()
    x3 = m3.bool("x")
    y3 = m3.bool("y")
    m3 &= (1 + x3 + y3 <= 1)
    r3 = _solve_ok(m3)
    assert r3[x3] is False
    assert r3[y3] is False


def test_pbexpr_rsub_with_offsets_is_allowed_and_semantic():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # 0 - (a + b) <= -2  => -(a+b) <= -2  => a+b >= 2
    m &= (0 - (a + b) <= -2)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True

    m2 = Model()
    x = m2.bool("x")
    y = m2.bool("y")
    # 2 - (x+y) <= 0  <=> x+y >= 2
    m2 &= (2 - (x + y) <= 0)
    r2 = _solve_ok(m2)
    assert r2[x] is True
    assert r2[y] is True


def test_pbexpr_vs_pbexpr_arithmetic_compare_semantics_sat_case():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # a + b <= c + a, with a=true and c=false, forces b=false.
    m &= a
    m &= ~c
    m &= (a + b <= c + a)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[c] is False
    assert r[b] is False


def test_pbexpr_vs_pbexpr_arithmetic_compare_semantics_unsat_case():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # 2*a + b <= c + a is impossible when a=b=true and c=false.
    m &= a
    m &= b
    m &= ~c
    m &= (2 * a + b <= c + a)
    r = _solve(m)
    assert r.status == "unsat"


def test_pbexpr_collapses_duplicate_literals_and_cancels_zero_sum_terms():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    expr1 = a + b - b
    assert len(expr1.terms) == 1
    t = expr1.terms[0]
    assert t.literal is a
    assert t.coefficient == 1

    expr2 = a + b + 2 * b
    by_key = {(t.literal.id, t.literal.polarity): t.coefficient for t in expr2.terms}
    assert by_key[(a.id, True)] == 1
    assert by_key[(b.id, True)] == 3
    assert len(expr2.terms) == 2


def test_pbexpr_iadd_and_isub_return_new_expr_and_preserve_collapse():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    expr = 3 * a  # start from Term on purpose; += should promote to PBExpr
    term_id = id(expr)
    expr += 2 * b
    from hermax.model import PBExpr
    assert isinstance(expr, PBExpr)
    assert id(expr) != term_id
    expr_id = id(expr)
    expr -= b
    expr_after_sub = expr
    expr += 0
    expr_after_add0 = expr
    expr -= 0
    expr_after_sub0 = expr

    # `+=/-= 0` are immutable-by-operator no-ops semantically. CPython may
    # reuse object ids, so do not assert id churn; assert the expression shape.
    assert isinstance(expr_after_add0, PBExpr)
    assert isinstance(expr_after_sub0, PBExpr)
    by_key = {(t.literal.id, t.literal.polarity): t.coefficient for t in expr.terms}
    assert by_key[(a.id, True)] == 3
    assert by_key[(b.id, True)] == 1
    assert len(expr.terms) == 2

    m &= (expr >= 4)  # 3*a + b >= 4 forces a and b to be true.
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True


def test_pbexpr_explicit_mutators_require_inplace_flag_and_mutate():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    expr = a + b
    expr_id = id(expr)
    with pytest.raises(TypeError, match="inplace=True"):
        expr.add(2 * a)
    with pytest.raises(TypeError, match="inplace=True"):
        expr.sub(a)

    out = expr.add(2 * a, inplace=True)
    assert out is expr
    assert id(expr) == expr_id

    # Now expr = 3*a + b
    by_key = {(t.literal.id, t.literal.polarity): t.coefficient for t in expr.terms}
    assert by_key[(a.id, True)] == 3
    assert by_key[(b.id, True)] == 1

    expr.sub(a, inplace=True)
    expr.add(0, inplace=True)
    expr.sub(0, inplace=True)
    by_key = {(t.literal.id, t.literal.polarity): t.coefficient for t in expr.terms}
    assert by_key[(a.id, True)] == 2
    assert by_key[(b.id, True)] == 1

    m &= (expr >= 3)  # 2*a + b >= 3 forces a and b true.
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True


def test_pbexpr_inplace_add_disjoint_terms_skips_global_recollapse(monkeypatch):
    m = Model()
    lits = list(m.bool_vector("b", length=6))

    expr = PBExpr(m, terms=[])

    def _boom(_terms):
        raise AssertionError("PBExpr.add(inplace=True) should not recollapse the full prefix for disjoint terms")

    monkeypatch.setattr(PBExpr, "_collapse_terms", staticmethod(_boom))
    for lit in lits:
        expr.add(lit, inplace=True)

    assert [(t.literal, int(t.coefficient)) for t in expr.terms] == [(lit, 1) for lit in lits]


def test_pbexpr_inplace_mutators_preserve_order_and_cancel_overlaps():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    expr = PBExpr(m, terms=[])
    expr.add(Term(2, b), inplace=True)
    expr.add(a, inplace=True)
    expr.sub(b, inplace=True)
    expr.add(3 * a, inplace=True)
    expr.sub(4 * a, inplace=True)

    assert [(t.literal, int(t.coefficient)) for t in expr.terms] == [(b, 1)]


def test_pbexpr_sub_cancels_lazy_scaled_int_terms_end_to_end():
    m = Model()
    x = m.int("x", 0, 4)
    a = m.bool("a")

    expr = x.scale(2) + a
    expr.sub(x.scale(2), inplace=True)

    m &= (x == 3)
    m &= ~a
    m &= (expr <= 0)
    r = _solve_ok(m)
    assert r[x] == 3
    assert r[a] is False

    m2 = Model()
    x2 = m2.int("x", 0, 4)
    a2 = m2.bool("a")
    expr2 = x2.scale(2) + a2
    expr2.sub(x2.scale(2), inplace=True)
    m2 &= (x2 == 3)
    m2 &= ~a2
    m2 &= (expr2 >= 1)
    assert _solve(m2).status == "unsat"


def test_pbexpr_scalar_multiplication_from_grouped_expression_is_supported():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # 2 * (a + b) <= 1 forces both false.
    m &= (2 * (a + b) <= 1)
    r = _solve_ok(m)
    assert r[a] is False
    assert r[b] is False


def test_pbexpr_scalar_multiplication_scales_terms_and_constant():
    m = Model()
    a = m.bool("a")
    expr = 2 * (a + 1)
    # Semantics: 2a + 2 <= 2  => a == 0
    m &= (expr <= 2)
    r = _solve_ok(m)
    assert r[a] is False


def test_pbexpr_unary_negation_is_supported_and_semantic():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    expr = -(a + 2 * b + 3)
    # -(a + 2b + 3) <= -3  <=> a + 2b >= 0 (always true) but we also test shape.
    m &= (expr <= -3)
    r = _solve_ok(m)
    assert r.ok

    # Stronger check: -(a + 2b + 3) <= -5  <=> a + 2b >= 2, so b must be true.
    m2 = Model()
    x = m2.bool("x")
    y = m2.bool("y")
    m2 &= (-(x + 2 * y + 3) <= -5)
    r2 = _solve_ok(m2)
    assert r2[y] is True


def test_pbexpr_randomized_subtraction_matches_fixed_assignment_value():
    rng = random.Random(2)

    for case in range(15):
        coeffs_lhs = [rng.choice([-2, -1, 0, 1, 2]) for _ in range(3)]
        coeffs_rhs = [rng.choice([-2, -1, 0, 1, 2]) for _ in range(3)]
        const_lhs = rng.randint(-2, 3)
        const_rhs = rng.randint(-2, 3)

        for aval in [False, True]:
            for bval in [False, True]:
                for cval in [False, True]:
                    lhs_val = const_lhs + coeffs_lhs[0] * int(aval) + coeffs_lhs[1] * int(bval) + coeffs_lhs[2] * int(cval)
                    rhs_val = const_rhs + coeffs_rhs[0] * int(aval) + coeffs_rhs[1] * int(bval) + coeffs_rhs[2] * int(cval)
                    expect = lhs_val - rhs_val

                    m = Model()
                    a = m.bool(f"a_{case}")
                    b = m.bool(f"b_{case}")
                    c = m.bool(f"c_{case}")
                    lhs = const_lhs + coeffs_lhs[0] * a + coeffs_lhs[1] * b + coeffs_lhs[2] * c
                    rhs = const_rhs + coeffs_rhs[0] * a + coeffs_rhs[1] * b + coeffs_rhs[2] * c
                    m &= (a if aval else ~a)
                    m &= (b if bval else ~b)
                    m &= (c if cval else ~c)
                    m &= (lhs - rhs == expect)
                    assert m.solve().status != "unsat"

                    m_bad = Model()
                    a_bad = m_bad.bool(f"a_bad_{case}")
                    b_bad = m_bad.bool(f"b_bad_{case}")
                    c_bad = m_bad.bool(f"c_bad_{case}")
                    lhs_bad = const_lhs + coeffs_lhs[0] * a_bad + coeffs_lhs[1] * b_bad + coeffs_lhs[2] * c_bad
                    rhs_bad = const_rhs + coeffs_rhs[0] * a_bad + coeffs_rhs[1] * b_bad + coeffs_rhs[2] * c_bad
                    m_bad &= (a_bad if aval else ~a_bad)
                    m_bad &= (b_bad if bval else ~b_bad)
                    m_bad &= (c_bad if cval else ~c_bad)
                    m_bad &= (lhs_bad - rhs_bad == expect + 1)
                    assert m_bad.solve().status == "unsat"


def test_pbexpr_double_negation_roundtrips_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    expr = a + b + 1
    m &= (-(-expr) <= 1)  # a + b + 1 <= 1 => a=b=false
    r = _solve_ok(m)
    assert r[a] is False
    assert r[b] is False

    m2 = Model()
    x = m2.bool("x")
    expr2 = 3 * (x + 1)
    # 3x + 3 >= 6  => x == 1
    m2 &= (expr2 >= 6)
    r2 = _solve_ok(m2)
    assert r2[x] is True


def test_pbexpr_scalar_multiplication_rejects_nonlinear_rhs():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    with pytest.raises(TypeError):
        _ = (a + b) * (a + 1)  # type: ignore[operator]
