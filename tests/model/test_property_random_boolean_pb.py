import itertools
import random

from hermax.model import Model


SEED = 1337


def _build_expr_from_spec(model: Model, vars_map: dict[str, object], terms_spec: list[tuple[int, str, bool]]):
    expr = 0
    for coeff, name, positive in terms_spec:
        lit = vars_map[name]
        if not positive:
            lit = ~lit
        expr = expr + (coeff * lit)
    return expr


def _apply_compare(model: Model, expr, op: str, bound: int):
    if op == "<=":
        model &= (expr <= bound)
    elif op == "<":
        model &= (expr < bound)
    elif op == ">=":
        model &= (expr >= bound)
    elif op == ">":
        model &= (expr > bound)
    elif op == "==":
        model &= (expr == bound)
    else:
        raise ValueError(op)


def _lit_value(assignment: dict[str, bool], name: str, positive: bool) -> int:
    v = assignment[name]
    return int(v if positive else (not v))


def _expr_value(assignment: dict[str, bool], terms_spec: list[tuple[int, str, bool]]) -> int:
    return sum(int(coeff) * _lit_value(assignment, name, positive) for coeff, name, positive in terms_spec)


def _compare_value(lhs: int, op: str, rhs: int) -> bool:
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
    raise ValueError(op)


def _bruteforce_sat(var_names: list[str], constraints_spec: list[tuple[list[tuple[int, str, bool]], str, int]]) -> bool:
    for bits in itertools.product([False, True], repeat=len(var_names)):
        asg = dict(zip(var_names, bits))
        if all(_compare_value(_expr_value(asg, terms), op, bound) for terms, op, bound in constraints_spec):
            return True
    return False


def _random_terms(rng: random.Random, var_names: list[str], *, max_terms: int, coeff_choices: list[int]):
    n_terms = rng.randint(1, max_terms)
    terms: list[tuple[int, str, bool]] = []
    for _ in range(n_terms):
        coeff = rng.choice(coeff_choices)
        name = rng.choice(var_names)
        positive = rng.choice([True, False])
        terms.append((coeff, name, positive))
    return terms


def test_random_small_boolean_pb_satisfiability_matches_bruteforce():
    rng = random.Random(SEED)
    ops = ["<=", "<", ">=", ">", "=="]

    for _case in range(120):
        n = rng.randint(1, 5)
        var_names = [f"x{i}" for i in range(n)]
        n_constraints = rng.randint(1, 3)

        constraints_spec: list[tuple[list[tuple[int, str, bool]], str, int]] = []
        m = Model()
        vars_map = {name: m.bool(name) for name in var_names}

        for _ in range(n_constraints):
            terms = _random_terms(rng, var_names, max_terms=6, coeff_choices=[-3, -2, -1, 1, 2, 3])
            # Bound range wide enough to exercise strict/off-by-one and unsat/tautology cases.
            total_abs = sum(abs(c) for c, _n, _p in terms)
            bound = rng.randint(-total_abs - 1, total_abs + 1)
            op = rng.choice(ops)
            constraints_spec.append((terms, op, bound))

            expr = _build_expr_from_spec(m, vars_map, terms)
            _apply_compare(m, expr, op, bound)

        expected_sat = _bruteforce_sat(var_names, constraints_spec)
        got = m.solve()
        assert (got.status != "unsat") == expected_sat, (
            f"mismatch on case with vars={var_names}, constraints={constraints_spec}, status={got.status}"
        )


def test_random_cardinality_path_matches_scaled_pb_path():
    rng = random.Random(SEED + 1)
    ops = ["<=", "<", ">=", ">", "=="]

    for _case in range(80):
        n = rng.randint(1, 6)
        var_names = [f"x{i}" for i in range(n)]
        terms = _random_terms(rng, var_names, max_terms=8, coeff_choices=[1])  # cardinality path
        op = rng.choice(ops)
        bound = rng.randint(-2, len(terms) + 2)

        m_card = Model()
        vars_card = {name: m_card.bool(name) for name in var_names}
        expr_card = _build_expr_from_spec(m_card, vars_card, terms)
        _apply_compare(m_card, expr_card, op, bound)

        # Semantically equivalent, but forces PB path by scaling all coeffs/bound by 2.
        m_pb = Model()
        vars_pb = {name: m_pb.bool(name) for name in var_names}
        scaled_terms = [(2 * c, name, pos) for (c, name, pos) in terms]
        expr_pb = _build_expr_from_spec(m_pb, vars_pb, scaled_terms)
        _apply_compare(m_pb, expr_pb, op, 2 * bound)

        sat_card = m_card.solve().status != "unsat"
        sat_pb = m_pb.solve().status != "unsat"
        assert sat_card == sat_pb, (
            f"card vs pb sat mismatch: terms={terms}, op={op}, bound={bound}, "
            f"card={sat_card}, pb={sat_pb}"
        )


def test_random_normalization_regressions_cancellation_and_merging_hold_semantically():
    rng = random.Random(SEED + 2)

    for _case in range(60):
        n = rng.randint(1, 5)
        var_names = [f"x{i}" for i in range(n)]
        pivot = rng.choice(var_names)
        other = rng.choice(var_names)

        # Build expressions with repeated literals and cancellation pressure.
        # expr1 == expr2 should be tautologically satisfiable.
        terms1 = [
            (1, pivot, True),
            (1, other, True),
            (-1, other, True),
            (2, pivot, True),
        ]
        terms2 = [
            (3, pivot, True),
        ]

        m = Model()
        vars_map = {name: m.bool(name) for name in var_names}
        e1 = _build_expr_from_spec(m, vars_map, terms1)
        e2 = _build_expr_from_spec(m, vars_map, terms2)
        m &= (e1 == e2)

        r = m.solve()
        assert r.ok, f"normalization equality should be satisfiable, got status={r.status}"
