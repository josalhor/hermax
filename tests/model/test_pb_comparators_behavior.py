import pytest

from hermax.model import Model


def _solve(m: Model):
    return m.solve()


def _solve_ok(m: Model):
    r = _solve(m)
    assert r.ok, f"expected satisfiable model, got status={r.status}"
    return r


def test_cardinality_atmost_behavior():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (a + b <= 1)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is False


def test_cardinality_strict_less_off_by_one():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # a + b < 2  is equivalent to  a + b <= 1 for booleans.
    m &= a
    m &= (a + b < 2)
    r = _solve_ok(m)
    assert r[b] is False


def test_cardinality_atleast_behavior():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= ~a
    m &= (a + b >= 1)
    r = _solve_ok(m)
    assert r[a] is False
    assert r[b] is True


def test_cardinality_strict_greater_behavior():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # a + b > 1 forces both true.
    m &= a
    m &= (a + b > 1)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True


def test_cardinality_equals_behavior():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (a + b == 1)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is False


def test_weighted_pb_leq_and_geq_behavior():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # 2*a + 3*b >= 4, with a=true, forces b=true.
    m &= a
    m &= (2 * a + 3 * b >= 4)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True


def test_weighted_pb_strict_greater_behavior():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # 2*a + 3*b > 2, with a=true, still forces b=true.
    m &= a
    m &= (2 * a + 3 * b > 2)
    r = _solve_ok(m)
    assert r[b] is True


def test_weighted_pb_equals_behavior():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (2 * a + 3 * b == 2)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is False


def test_pbexpr_vs_pbexpr_geq_behavior():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # 2*a + b >= c + a + c with a=true,c=true forces b=true.
    m &= a
    m &= c
    m &= (2 * a + b >= c + a + c)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[c] is True
    assert r[b] is True


def test_pbexpr_vs_pbexpr_equals_sat_case():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # a + b == c + a  reduces to  b == c
    m &= b
    m &= (a + b == c + a)
    r = _solve_ok(m)
    assert r[b] is True
    assert r[c] is True


def test_pb_normalization_coalesces_duplicates_created_by_complement_flip():
    """Regression from ``tests.model_fuzzing`` case 15177_0000911_518454542."""
    m = Model()
    b0 = m.bool("b0")
    b1 = m.bool("b1")
    i0 = m.int("i0", -1, 1)
    i1 = m.int("i1", 1, 4)

    # The normalized lhs-rhs contains negative b0/b1 terms. Flipping them to
    # positive complementary literals must merge with the existing ~b0/~b1.
    m &= 1 + 3 * ~b0 + i1.scale(2) + 3 * ~b1 + i0 < 1 + b1 + b0 + b1
    m &= ~b0
    m &= ~b1
    m &= i0 == -1
    m &= i1 == 1

    assert _solve(m).status == "unsat"


def test_pb_complement_flip_coalescing_preserves_constant_offset_truth_table():
    # 3*~b + x < 2*b normalizes to 5*~b + x - 2 < 0. Besides
    # coalescing ~b, the -2 offset introduced by flipping -2*b is essential.
    for b_value in (False, True):
        for x_value in range(-1, 2):
            m = Model()
            b = m.bool("b")
            x = m.int("x", -1, 1)
            m &= b if b_value else ~b
            m &= x == x_value
            m &= 3 * ~b + x < 2 * b

            expected = 3 * int(not b_value) + x_value < 2 * int(b_value)
            assert _solve(m).ok is expected


def test_pb_normalization_coalesces_duplicates_created_by_negated_literal_flip():
    """Regression from ``tests.model_fuzzing`` case 15385_0002945_316809963."""
    m = Model()
    b0 = m.bool("b0")
    b1 = m.bool("b1")
    i0 = m.int("i0", -1, 1)
    i1 = m.int("i1", 0, 3)

    # -2*~b0 becomes 2*b0 - 2 during normalization and must merge with
    # the remaining positive b0 coefficient after subtracting the RHS.
    m &= 3 * b0 - 2 * ~b0 + i1.scale(2) < -3 + b0 + b1 + i0.scale(2)
    m &= ~b0
    m &= ~b1
    m &= i0 == -1
    m &= i1 == 0

    assert _solve(m).status == "unsat"


def test_pbexpr_equals_int_unsat_when_assignments_conflict():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Use PBExpr equality finalization (Literal == Literal semantics remain separate).
    m &= a
    m &= ~b
    m &= (a + b == 2)
    r = _solve(m)
    assert r.status == "unsat"


def test_constant_only_pb_comparator_finalization_true_and_false_cases():
    a = Model().bool("tmp")  # local helper source literal for expressions

    # Build on separate models to keep constraints isolated.
    m1 = a._model
    m1 &= (a - a <= 0)   # constant 0 <= 0 => true constraint
    r1 = _solve_ok(m1)
    assert r1.status == "sat"

    m2 = Model()
    x = m2.bool("x")
    m2 &= (x - x < 0)    # constant 0 < 0 => false constraint
    r2 = _solve(m2)
    assert r2.status == "unsat"

    m3 = Model()
    y = m3.bool("y")
    m3 &= (y - y == 0)   # constant 0 == 0 => true constraint
    r3 = _solve_ok(m3)
    assert r3.status == "sat"

    m4 = Model()
    z = m4.bool("z")
    m4 &= (z - z > 0)    # constant 0 > 0 => false constraint
    r4 = _solve(m4)
    assert r4.status == "unsat"


def test_constant_only_pb_comparator_uses_internal_boolean_constants_in_export():
    m = Model()
    a = m.bool("a")
    m &= (a - a <= 0)  # true comparator may be folded away
    m &= (a - a < 0)   # should materialize __false and make UNSAT

    assert "__false" in m._registry
    f = m._registry["__false"]

    cnf = m.to_cnf()
    hard = {tuple(cl) for cl in cnf.clauses}
    # False constant definition and use should be present as unit clauses.
    assert (-f.id,) in hard
    assert sum(1 for cl in cnf.clauses if cl == [f.id]) >= 1


@pytest.mark.parametrize("op", ["<=", "<", ">=", ">", "==", "!="])
def test_pb_constraint_implies_matches_truth_table_for_each_comparator(op):
    def antecedent_value(a: bool, b: bool, c: bool) -> bool:
        lhs = int(a) + 2 * int(b) - int(c)
        rhs = 1
        if op == "<=":
            return lhs <= rhs
        if op == "<":
            return lhs < rhs
        if op == ">=":
            return lhs >= rhs
        if op == ">":
            return lhs > rhs
        if op == "==":
            return lhs == rhs
        if op == "!=":
            return lhs != rhs
        raise AssertionError(op)

    for aval in [False, True]:
        for bval in [False, True]:
            for cval in [False, True]:
                for tval in [False, True]:
                    m = Model()
                    a = m.bool("a")
                    b = m.bool("b")
                    c = m.bool("c")
                    t = m.bool("t")
                    m &= (a if aval else ~a)
                    m &= (b if bval else ~b)
                    m &= (c if cval else ~c)
                    m &= (t if tval else ~t)
                    expr = a + 2 * b - c
                    if op == "<=":
                        constraint = expr <= 1
                    elif op == "<":
                        constraint = expr < 1
                    elif op == ">=":
                        constraint = expr >= 1
                    elif op == ">":
                        constraint = expr > 1
                    elif op == "==":
                        constraint = expr == 1
                    else:
                        constraint = expr != 1
                    m &= constraint.implies(t)
                    expected = (not antecedent_value(aval, bval, cval)) or tval
                    assert (m.solve().status != "unsat") is expected
