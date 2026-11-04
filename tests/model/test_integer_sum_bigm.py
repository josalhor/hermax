import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import Model, sum_expr
from hermax.model.encoders import _EncoderDispatch


@pytest.mark.parametrize("coefficients", [(1, 1, 1), (2, -3, 1)])
@pytest.mark.parametrize("op", ["<=", "<", ">=", ">"])
@pytest.mark.parametrize("mode", ["post", "gated", "iff"])
@pytest.mark.parametrize("swapped", [False, True])
def test_domain_extremal_bigm_truth_table(coefficients, op, mode, swapped):
    m = Model()
    xs = [m.int(f"x{i}", -1, 1) for i in range(3)]
    flag, gate, result = m.bool(), m.bool(), m.bool()
    main = sum_expr(c * x for c, x in zip(coefficients, xs)) + 2
    radius = sum(abs(c) for c in coefficients)
    low = op in ("<=", "<")
    endpoint = 2 - radius if low else 2 + radius
    constant = endpoint + (op == "<") - (op == ">")
    weight = 3 if low else -3
    indicator = ~flag if swapped else flag
    rhs = constant + weight * indicator
    flipped = {"<=": ">=", "<": ">", ">=": "<=", ">": "<"}
    compare = {"<=": operator.le, "<": operator.lt, ">=": operator.ge, ">": operator.gt}
    condition = compare[flipped[op]](rhs, main) if swapped else compare[op](main, rhs)
    m &= condition.only_if(gate) if mode == "gated" else condition.iff(result) if mode == "iff" else condition
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for values, fv, gv, rv in itertools.product(itertools.product(range(-1, 2), repeat=3), (False, True), (False, True), (False, True)):
            lhs = 2 + sum(c * v for c, v in zip(coefficients, values))
            bound = constant + weight * (not fv if swapped else fv)
            truth = {"<=": lhs <= bound, "<": lhs < bound, ">=": lhs >= bound, ">": lhs > bound}[op]
            expected = (not gv or truth) if mode == "gated" else rv == truth if mode == "iff" else truth
            assumptions = [m._lit_to_dimacs(atom) for x, value in zip(xs, values) for atom in x._exact_value_atoms(value)]
            assumptions += [flag.id if fv else -flag.id, gate.id if gv else -gate.id, result.id if rv else -result.id]
            assert solver.solve(assumptions=assumptions) == expected


def test_integer_bigm_propagates_endpoints():
    m = Model()
    xs = [m.int(f"x{i}", 0, 60) for i in range(5)]
    opened = m.bool()
    m &= sum_expr(xs) <= 120 * opened
    cases = [
        ([-opened.id], [x <= 0 for x in xs]),
        ([m._lit_to_dimacs(xs[0] >= 1)], [opened]),
    ]
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for assumptions, targets in cases:
            ok, forced = solver.propagate(assumptions=assumptions)
            assert ok
            assert all(m._lit_to_dimacs(target) in forced for target in targets)


def test_nonextremal_bigm_stays_on_existing_path():
    m = Model()
    xs = [m.int(f"x{i}", 0, 3) for i in range(3)]
    condition = sum_expr(xs) <= 1 + 4 * m.bool()
    assert _EncoderDispatch._try_integer_sum_bigm_fastpath(
        m, condition._lhs._realize_int_terms(m), "<=", condition._rhs._realize_int_terms(m)
    ) is None


def test_integer_bigm_matches_explicit_split():
    def build(explicit):
        m = Model()
        xs = [m.int(f"x{i}", 0, 60) for i in range(5)]
        opened = m.bool()
        if explicit:
            m &= sum_expr(xs) <= 120
            for x in xs:
                m &= (x == 0).only_if(~opened)
        else:
            m &= sum_expr(xs) <= 120 * opened
        return m.to_cnf()

    automatic, explicit = build(False), build(True)
    assert automatic.nv == explicit.nv
    assert sorted(map(tuple, automatic.clauses)) == sorted(map(tuple, explicit.clauses))


def test_equality_does_not_use_integer_bigm_split():
    m = Model()
    xs = [m.int(f"x{i}", 0, 3) for i in range(3)]
    condition = sum_expr(xs) == 4 * m.bool()
    assert _EncoderDispatch._try_integer_sum_bigm_fastpath(
        m, condition._lhs._realize_int_terms(m), "==", condition._rhs._realize_int_terms(m)
    ) is None
