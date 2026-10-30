from hermax.internal import _encoding_policy as policy
import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.encoder._integer_sum import weighted
from hermax.model import encoders

OPS = {
    "<=": operator.le,
    "<": operator.lt,
    ">=": operator.ge,
    ">": operator.gt,
    "==": operator.eq,
    "!=": operator.ne,
}


def fixed(xs, values):
    return [
        lit.id if j < v - x.lb else -lit.id
        for x, v in zip(xs, values)
        for j, lit in enumerate(x._threshold_lits)
    ]


@pytest.mark.parametrize("limit", ["states", "clauses"])
@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("same_owner", [False, True])
def test_threshold_residual_budget_fallback_is_exact(
    limit, op, same_owner, monkeypatch
):
    monkeypatch.setattr(policy, "STATE_LIMIT", 1 if limit == "states" else 0)
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 1 if limit == "clauses" else 0)
    m = Model()
    xs = [m.int("x", -1, 2), m.int("y", 0, 3), m.int("z", 1, 4)]
    extra = xs[0] if same_owner else m.int("extra", -1, 2)
    inputs = xs if same_owner else xs + [extra]
    b, g = m.bool("b"), m.bool("g")
    expression = (
        5 * xs[0] - 3 * xs[1] + 7 * xs[2] - 2 * (extra >= 1) + 3 * (extra < 1) + 4
    )
    m &= OPS[op](expression, 11).only_if(g).iff(b)
    cnf = m.to_cnf()
    assert all(x._binary_view is not None for x in xs)
    if not same_owner:
        assert extra._binary_view is None
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product(*(range(x.lb, x.ub + 1) for x in inputs)):
            x, y, z = values[:3]
            e = x if same_owner else values[3]
            truth = OPS[op](5 * x - 3 * y + 7 * z - 2 * (e >= 1) + 3 * (e < 1) + 4, 11)
            for gv, bv in itertools.product([False, True], repeat=2):
                assert solver.solve(
                    assumptions=fixed(inputs, values)
                    + [g.id if gv else -g.id, b.id if bv else -b.id]
                ) == (bv == (not gv or truth))


@pytest.mark.parametrize("kind", ["added", "cancelled"])
def test_unit_coefficient_aliases_use_bounded_weighted_adapter(kind, monkeypatch):
    monkeypatch.setattr(policy, "STATE_LIMIT", 1)
    m = Model()
    xs = [m.int(f"x{i}", 0, 3) for i in range(3)]
    expression = sum(xs) + (1 if kind == "added" else -1) * (xs[0] >= 2)
    m &= expression <= 4
    cnf = m.to_cnf()
    assert all(x._binary_view is not None for x in xs)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product(range(4), repeat=3):
            expected = (
                sum(values) + (1 if kind == "added" else -1) * (values[0] >= 2) <= 4
            )
            assert solver.solve(assumptions=fixed(xs, values)) == expected


def test_partial_threshold_expression_alone_does_not_invent_integer_sum():
    m = Model()
    x = m.int("x", 0, 10)
    expression = (x >= 2) + 3 * (x >= 7)
    assert (
        encoders._EncoderDispatch._extract_integer_sum_with_bools(m, expression) is None
    )


@pytest.mark.parametrize("same_owner", [False, True])
def test_reported_threshold_case_builds_within_memory_and_time_caps(same_owner):
    import subprocess
    import sys

    pytest.importorskip("resource")
    code = f"""
import resource
resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
from hermax.model import Model
m=Model();xs=[m.int(f'x{{i}}',0,512) for i in range(6)]
extra=xs[0] if {same_owner} else m.int('extra',0,512)
m &= sum(c*x for c,x in zip([5,11,17,23,31,49],xs))+(extra>=3)<=34816
cnf=m.to_cnf()
assert all(x._binary_view is not None for x in xs)
assert len(cnf.clauses)<35000
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0, result.stderr


def test_recognizer_decomposition_matches_original_expression_without_model_mutation():
    import random
    from hermax.model import PBExpr, Term
    from hermax.model._integer_affine import extract_integer_sum

    rng = random.Random(173)
    m = Model()
    xs = [m.int("x", -2, 2), m.int("y", 0, 3), m.int("z", 1, 3)]
    b = m.bool("b")
    literals = [lit for x in xs for lit in x._threshold_lits] + [b]
    recognized = 0
    for _ in range(100):
        terms = [
            Term(rng.choice([-3, -1, 0, 1, 3]), lit if rng.randrange(2) else ~lit)
            for lit in literals
        ]
        expr = PBExpr(m, terms, rng.randrange(-5, 6))
        before = m._top_id(), tuple(m._hard)
        plan = extract_integer_sum(m, expr)
        assert (m._top_id(), tuple(m._hard)) == before
        if plan is None:
            continue
        recognized += 1
        for values in itertools.product(*(range(x.lb, x.ub + 1) for x in xs)):
            for bv in (False, True):
                true_ids = {
                    lit.id
                    for x, v in zip(xs, values)
                    for j, lit in enumerate(x._threshold_lits)
                    if j < v - x.lb
                }
                if bv:
                    true_ids.add(b.id)

                def truth(lit):
                    return (lit.id in true_ids) == lit.polarity

                original = expr.constant + sum(
                    t.coefficient * truth(t.literal) for t in expr.terms
                )
                recovered = plan.constant + sum(
                    c * sum(truth(lit) for lit in x._threshold_lits)
                    for x, c in plan.items
                )
                assert recovered == original
    assert recognized > 20
