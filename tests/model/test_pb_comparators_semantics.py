from hermax.model import Model


def _solve(m: Model):
    return m.solve()


def _solve_ok(m: Model):
    r = _solve(m)
    assert r.ok, f"expected satisfiable model, got status={r.status}"
    return r


def test_cardinality_atmost_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (a + b <= 1)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is False


def test_cardinality_strict_less_semantics_off_by_one():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # a + b < 2  is equivalent to  a + b <= 1 for booleans.
    m &= a
    m &= (a + b < 2)
    r = _solve_ok(m)
    assert r[b] is False


def test_cardinality_atleast_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= ~a
    m &= (a + b >= 1)
    r = _solve_ok(m)
    assert r[a] is False
    assert r[b] is True


def test_cardinality_strict_greater_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # a + b > 1 forces both true.
    m &= a
    m &= (a + b > 1)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True


def test_cardinality_equals_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (a + b == 1)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is False


def test_weighted_pb_leq_and_geq_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # 2*a + 3*b >= 4, with a=true, forces b=true.
    m &= a
    m &= (2 * a + 3 * b >= 4)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is True


def test_weighted_pb_strict_greater_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # 2*a + 3*b > 2, with a=true, still forces b=true.
    m &= a
    m &= (2 * a + 3 * b > 2)
    r = _solve_ok(m)
    assert r[b] is True


def test_weighted_pb_equals_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    m &= a
    m &= (2 * a + 3 * b == 2)
    r = _solve_ok(m)
    assert r[a] is True
    assert r[b] is False


def test_pbexpr_vs_pbexpr_geq_semantics():
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


def test_pbexpr_vs_pbexpr_equals_semantics_sat_case():
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
