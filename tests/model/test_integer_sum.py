"""All internal sum strategies preserve the existing modeling semantics."""
import itertools
import operator
from collections import Counter

import pytest
from pysat.solvers import Solver

from hermax.model import Model, Literal
from hermax.encoder._integer_sum import selection, LEAF, WHOLE, BINARY

OPS = {
    "<=": operator.le,
    "<": operator.lt,
    ">=": operator.ge,
    ">": operator.gt,
    "==": operator.eq,
    "!=": operator.ne,
}
KINDS = [LEAF, WHOLE, BINARY]


@pytest.fixture(params=KINDS)
def strategy(request, monkeypatch):
    calls = []

    def choose(*args, **kwargs):
        calls.append((args, kwargs))
        return request.param

    monkeypatch.setattr(selection, "choose", choose)
    return request.param, calls


def assumptions(variables, values):
    return [
        lit.id if j < value - v.lb else -lit.id
        for v, value in zip(variables, values)
        for j, lit in enumerate(v._threshold_lits)
    ]


@pytest.mark.parametrize("comparator", OPS)
@pytest.mark.parametrize(
    "coefficients", [(1, 1, 1, 1), (-1, 1, -1, 1), (-1, -1, -1, -1)]
)
def test_all_values_signed_offsets_strict_comparisons(
    strategy, comparator, coefficients
):
    kind, calls = strategy
    for bound in [-7, -2, 0, 3, 8]:
        m = Model()
        variables = [
            m.int(f"x{i}", lb, lb + w)
            for i, (lb, w) in enumerate([(-2, 2), (1, 3), (0, 1), (-1, 2)])
        ]
        expression = sum(c * v for c, v in zip(coefficients, variables)) + 2
        m &= OPS[comparator](expression, bound)
        cnf = m.to_cnf()
        with Solver(name="g4", bootstrap_with=cnf.clauses) as solver:
            for values in itertools.product(
                *(range(v.lb, v.ub + 1) for v in variables)
            ):
                expected = OPS[comparator](
                    sum(c * x for c, x in zip(coefficients, values)) + 2, bound
                )
                assert (
                    solver.solve(assumptions=assumptions(variables, values)) == expected
                ), (kind, comparator, coefficients, bound, values)
    assert calls, "model did not use the integrated integer-sum strategy"


@pytest.mark.parametrize("comparator", ["<=", ">=", "==", "!="])
@pytest.mark.parametrize("reification", ["only_if", "iff", "gated_iff"])
def test_conditional_and_full_reification(strategy, comparator, reification):
    kind, calls = strategy
    m = Model()
    xs = [m.int(f"x{i}", 0, 2) for i in range(4)]
    g = m.bool("g")
    b = m.bool("b")
    comparison = OPS[comparator](sum(xs), 4)
    if reification == "only_if":
        m &= comparison.only_if(g)
    elif reification == "iff":
        m &= comparison.iff(b)
    else:
        m &= comparison.only_if(g).iff(b)
    cnf = m.to_cnf()
    with Solver(name="g4", bootstrap_with=cnf.clauses) as s:
        for values in itertools.product(range(3), repeat=4):
            numeric = OPS[comparator](sum(values), 4)
            for gv, bv in itertools.product([False, True], repeat=2):
                expected = (
                    (not gv or numeric)
                    if reification == "only_if"
                    else (
                        (bv == numeric)
                        if reification == "iff"
                        else (bv == (not gv or numeric))
                    )
                )
                ass = assumptions(xs, values) + [
                    g.id if gv else -g.id,
                    b.id if bv else -b.id,
                ]
                assert s.solve(assumptions=ass) == expected, (
                    kind,
                    comparator,
                    reification,
                    values,
                    gv,
                    bv,
                )
    assert calls


def test_binary_views_are_cached_once_and_comparisons_keep_literal_identity(
    monkeypatch,
):
    monkeypatch.setattr(selection, "choose", lambda *a, **k: BINARY)
    m = Model()
    xs = [m.int(f"x{i}", 0, 5) for i in range(4)]
    before = xs[0] >= 2
    m &= (sum(xs) >= 7).only_if(m.bool("guard"))
    first = m.to_cnf()
    views = tuple(x._binary_view for x in xs)
    assert all(view is not None for view in views)
    first_ids = {bit for view in views for bit in view}
    m &= sum(xs) <= 14
    m &= xs[0] - xs[1] + xs[2] - xs[3] >= -2
    second = m.to_cnf()
    assert tuple(x._binary_view for x in xs) == views
    assert isinstance(before, Literal)
    assert (xs[0] >= 2) is before
    counts = Counter(tuple(m._clause_to_dimacs_list(c)) for c in m._hard)
    for bit in first_ids:
        assert bit in m._realized_literal_defs
        for clause in m._pending_literal_defs[bit]:
            assert counts[clause] == 1
    # Re-export and repeated cached comparisons cannot add definitions.
    hard = len(m._hard)
    m.to_cnf()
    assert len(m._hard) == hard
    top = m._top_id()
    fresh = m.bool("after")
    assert fresh.id > top


@pytest.mark.parametrize("soft", [False, True])
def test_model_solving_and_decoding(strategy, soft):
    kind, calls = strategy
    m = Model()
    xs = [m.int(f"x{i}", 0, 4) for i in range(4)]
    m &= sum(xs) >= 7
    if soft:
        for x in xs:
            m.obj += x
    result = m.solve()
    assert result.ok
    values = [result[x] for x in xs]
    assert all(0 <= v <= 4 for v in values) and sum(values) >= 7
    if soft:
        assert sum(values) == 7
    assert calls


def test_incremental_solving_can_add_a_binary_view_after_binding(monkeypatch):
    requested = [LEAF]
    monkeypatch.setattr(selection, "choose", lambda *a, **k: requested[0])
    m = Model()
    xs = [m.int(f"x{i}", 0, 3) for i in range(4)]
    m &= sum(xs) >= 5
    assert m.solve(incremental=True, backend="sat").ok
    assert all(x._binary_view is None for x in xs)
    requested[0] = BINARY
    m &= sum(xs) <= 4
    assert m.solve(incremental=True, backend="sat").status == "unsat"
    assert all(x._binary_view is not None for x in xs)
    m.close_incremental()


def test_native_auxiliary_ids_avoid_bound_backend_owned_range(strategy):
    from tests.model.test_model_incremental_native import FakeIPSolver

    kind, calls = strategy
    m = Model()
    xs = [m.int(f"x{i}", 0, 3) for i in range(4)]
    m.obj[1] += m.bool("soft")
    assert m.solve(incremental=True, backend="maxsat", solver=FakeIPSolver()).ok
    old_top = m._top_id()
    m._inc_state.ip_next_vid = 500
    hard = len(m._hard)
    m &= sum(xs) >= 5
    m.to_wcnf()
    assert calls
    assert all(
        not old_top < abs(l) <= 500
        for c in m._hard[hard:]
        for l in m._clause_to_dimacs_list(c)
    )
    m.close_incremental()


@pytest.mark.parametrize("comparator", ["<=", ">=", "==", "!="])
def test_uniform_scaling_uses_the_same_internal_sum_strategies(strategy, comparator):
    kind, calls = strategy
    for bound in [3, 7, 8, 12]:
        m = Model()
        xs = [m.int(f"x{i}", -1, 1) for i in range(4)]
        m &= OPS[comparator](2 * sum(xs) + 3, bound)
        with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as s:
            for values in itertools.product(range(-1, 2), repeat=4):
                assert s.solve(assumptions=assumptions(xs, values)) == OPS[comparator](
                    2 * sum(values) + 3, bound
                )
    assert calls


def test_nonuniform_weighted_integers_keep_existing_pipeline(monkeypatch):
    def unexpected(*a, **k):
        raise AssertionError("weighted sum must not use unit-sum encoding")

    monkeypatch.setattr(selection, "choose", unexpected)
    m = Model()
    xs = [m.int(f"x{i}", 0, 2) for i in range(4)]
    m &= sum((i + 1) * x for i, x in enumerate(xs)) >= 8
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as s:
        for values in itertools.product(range(3), repeat=4):
            assert s.solve(assumptions=assumptions(xs, values)) == (
                sum((i + 1) * v for i, v in enumerate(values)) >= 8
            )


def test_unposted_binary_definitions_are_not_treated_as_free(monkeypatch):
    model = Model()
    xs = [model.int(f"x{i}", 0, 5) for i in range(4)]
    for x in xs:
        x._get_binary_view()
    observed = []

    def choose(widths, bound, costs, cached, **kwargs):
        observed.append(tuple(cached))
        return BINARY

    monkeypatch.setattr(selection, "choose", choose)
    model &= sum(xs) <= 10
    model.to_cnf()
    assert observed == [(False,) * 4]
    observed.clear()
    model &= sum(xs) >= 7
    model.to_cnf()
    assert observed == [(True,) * 4]


@pytest.mark.parametrize(
    "comparator,bound,expected", [("<=", 1, BINARY), (">=", 8, WHOLE), ("<=", 15, LEAF)]
)
def test_automatic_pipeline_uses_each_strategy_deterministically(
    monkeypatch, comparator, bound, expected
):
    original = selection.choose
    selected = []

    def choose(*args, **kwargs):
        kind = original(*args, **kwargs)
        selected.append(kind)
        return kind

    monkeypatch.setattr(selection, "choose", choose)
    outputs = []
    for _ in range(2):
        model = Model()
        xs = [model.int(f"x{i}", 0, 4) for i in range(4)]
        model &= OPS[comparator](sum(xs), bound)
        cnf = model.to_cnf()
        outputs.append((cnf.nv, cnf.clauses))
    assert selected == [expected, expected]
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("comparator", OPS)
def test_automatic_signed_sums_with_large_offsets(comparator):
    import random

    rng = random.Random("large-offset-" + comparator)
    for _ in range(8):
        model = Model()
        widths = [rng.randint(1, 7) for _ in range(6)]
        offsets = [rng.choice([-(10**12), 10**12]) for _ in widths]
        signs = [rng.choice([-1, 1]) for _ in widths]
        xs = [
            model.int(f"x{i}", lb, lb + w)
            for i, (lb, w) in enumerate(zip(offsets, widths))
        ]
        scale = rng.choice([1, 2, 7])
        constant = rng.randrange(-10, 11)
        center = scale * sum(c * lb for c, lb in zip(signs, offsets)) + constant
        bound = center + rng.randrange(-sum(widths), sum(widths) + 1)
        model &= OPS[comparator](
            scale * sum(c * x for c, x in zip(signs, xs)) + constant, bound
        )
        with Solver(name="g4", bootstrap_with=model.to_cnf().clauses) as solver:
            for _ in range(70):
                values = [lb + rng.randrange(w + 1) for lb, w in zip(offsets, widths)]
                total = scale * sum(c * v for c, v in zip(signs, values)) + constant
                assert solver.solve(assumptions=assumptions(xs, values)) == OPS[
                    comparator
                ](total, bound)


def test_fixed_and_cancelled_terms_preserve_integer_sum_semantics(strategy):
    _, calls = strategy
    model = Model()
    xs = [model.int(f"x{i}", -1, 2) for i in range(4)]
    fixed = model.int("fixed", 123, 123)
    expression = sum(xs) + xs[0] - xs[0] + fixed
    model &= expression == 126
    with Solver(name="g4", bootstrap_with=model.to_cnf().clauses) as solver:
        for values in itertools.product(range(-1, 3), repeat=4):
            assert solver.solve(assumptions=assumptions(xs, values)) == (
                sum(values) == 3
            )
    assert calls
