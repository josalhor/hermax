from hermax.model import Model


def _solve_status_and_decode(m: Model, a, x):
    r = m.solve()
    if r.status == "unsat":
        return "unsat", None, None
    return r.status, r[a], r[x]


def _exists_solution(lb: int, ub: int, bound: int, *, weight_x: int = 1) -> bool:
    # Brute force over actual integer semantics: a in {0,1}, x in [lb, ub)
    for a in (0, 1):
        for x in range(lb, ub):
            if a + weight_x * x <= bound:
                return True
    return False


def test_bool_plus_int_pb_lifting_lb_zero_matches_intended_semantics():
    # x in {0,1,2,3}; a + x <= 0 has exactly one solution: a=0,x=0
    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=0, ub=4)
    m &= (a + x <= 0)

    status, aval, xval = _solve_status_and_decode(m, a, x)
    assert status != "unsat"
    assert aval is False
    assert xval == 0


def test_bool_plus_weighted_int_pb_lifting_lb_zero_matches_intended_semantics():
    # x in {0,1,2,3}; a + 2*x <= 1 forces x=0 (a may be 0 or 1).
    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=0, ub=4)
    m &= (a + 2 * x <= 1)

    status, aval, xval = _solve_status_and_decode(m, a, x)
    assert status != "unsat"
    assert xval == 0
    assert (int(aval) + 2 * xval) <= 1


def test_bool_plus_int_pb_lifting_nonzero_lb_respects_actual_integer_values_unsat_case():
    # Actual semantics: x in {3,4,5,6}; a + x <= 2 is impossible.
    assert _exists_solution(3, 7, 2, weight_x=1) is False

    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=3, ub=7)
    m &= (a + x <= 2)

    r = m.solve()
    assert r.status == "unsat"


def test_bool_plus_weighted_int_pb_lifting_nonzero_lb_respects_actual_integer_values_unsat_case():
    # Actual semantics: x in {3,4,5,6}; a + 2*x <= 5 is impossible.
    assert _exists_solution(3, 7, 5, weight_x=2) is False

    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=3, ub=7)
    m &= (a + 2 * x <= 5)

    r = m.solve()
    assert r.status == "unsat"


def test_bool_plus_int_pb_lifting_nonzero_lb_sat_case_decoded_solution_satisfies_actual_semantics():
    # Actual semantics: x in {3,4,5,6}; a + x <= 4 is satisfiable (e.g., a=0,x=3).
    assert _exists_solution(3, 7, 4, weight_x=1) is True

    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=3, ub=7)
    m &= (a + x <= 4)

    status, aval, xval = _solve_status_and_decode(m, a, x)
    assert status != "unsat"
    assert (int(aval) + xval) <= 4


def test_bool_plus_weighted_int_pb_lifting_nonzero_lb_sat_case_decoded_solution_satisfies_actual_semantics():
    # Actual semantics: x in {3,4,5,6}; a + 2*x <= 7 is satisfiable only with x=3,a=0/1?
    # Check by brute force and then require decoded solution to satisfy real arithmetic.
    assert _exists_solution(3, 7, 7, weight_x=2) is True

    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=3, ub=7)
    m &= (a + 2 * x <= 7)

    status, aval, xval = _solve_status_and_decode(m, a, x)
    assert status != "unsat"
    assert (int(aval) + 2 * xval) <= 7


def test_mixed_bool_int_pb_lifting_with_explicit_offsets_on_both_sides():
    # Check algebraic-offset normalization with nonzero-lb IntVar lifting:
    # a + x + 2 <= 8  <=>  a + x <= 6
    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=3, ub=7)
    m &= (a + x + 2 <= 8)

    status, aval, xval = _solve_status_and_decode(m, a, x)
    assert status != "unsat"
    assert (int(aval) + xval + 2) <= 8


def test_mixed_bool_int_pb_lifting_with_negative_offset_and_weighted_int():
    # 1 + a + 2*x - 3 <= 5  <=> a + 2*x <= 7
    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=3, ub=7)
    m &= (1 + a + 2 * x - 3 <= 5)

    status, aval, xval = _solve_status_and_decode(m, a, x)
    assert status != "unsat"
    assert (1 + int(aval) + 2 * xval - 3) <= 5


def test_bool_minus_int_pb_lifting_nonzero_lb_respects_sign_and_offset_unsat_case():
    # Actual semantics: x in {3,4,5,6}; a - x <= -7 is impossible.
    for a in (0, 1):
        for x in range(3, 7):
            assert not (a - x <= -7)

    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=3, ub=7)
    m &= (a - x <= -7)
    assert m.solve().status == "unsat"


def test_bool_minus_int_pb_lifting_nonzero_lb_respects_sign_and_offset_sat_case():
    # Actual semantics: x in {3,4,5,6}; a - x <= -5 is satisfiable (e.g., x=6).
    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=3, ub=7)
    m &= (a - x <= -5)

    status, aval, xval = _solve_status_and_decode(m, a, x)
    assert status != "unsat"
    assert (int(aval) - xval) <= -5
