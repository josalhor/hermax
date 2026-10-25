"""Weighted integer sums retain the original encoder until its budget is hit."""
import itertools
import operator
from unittest.mock import patch

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.internal import _integer_sum_native as integer_native

OPS = {
    "<=": operator.le,
    "<": operator.lt,
    ">=": operator.ge,
    ">": operator.gt,
    "==": operator.eq,
    "!=": operator.ne,
}


def assignment(xs, values):
    return [
        l.id if j < value - x.lb else -l.id
        for x, value in zip(xs, values)
        for j, l in enumerate(x._threshold_lits)
    ]


def test_small_weighted_constraint_retains_original_cnf():
    from hermax.encoder.pb_enc import PBEnc

    model = Model()
    xs = [model.int(f"x{i}", 0, 10) for i in range(6)]
    coefficients = [7, 8, 9, 10, 11, 13]
    model &= sum(c * x for c, x in zip(coefficients, xs)) <= 290
    cnf = model.to_cnf()
    expected = PBEnc.leq(
        [l.id for x in xs for l in x._threshold_lits],
        weights=[c for c in coefficients for _ in range(10)],
        bound=290,
        top_id=60,
    )
    assert all(x._binary_view is None for x in xs)
    assert cnf.nv == expected.nv
    assert (
        cnf.clauses
        == [
            [-b.id, a.id]
            for x in xs
            for a, b in zip(x._threshold_lits, x._threshold_lits[1:])
        ]
        + expected.clauses
    )


def test_reported_equality_switches_to_cached_binary_views():
    model = Model()
    xs = [model.int(name, 0, 100) for name in ["b", "o", "g"]]
    model &= 189 * xs[0] + 180 * xs[1] + 175 * xs[2] == 15750
    cnf = model.to_cnf()
    assert all(x._binary_view is not None for x in xs)
    assert cnf.nv < 1000 and len(cnf.clauses) < 3000
    top = model._top_id()
    assert model.bool("after").id == top + 1


@pytest.mark.parametrize("reason", ["states", "clauses"])
@pytest.mark.parametrize("op", OPS)
def test_aborted_attempt_is_atomic_and_fallback_is_sound(reason, op):
    original = integer_native.encode_pb
    seen = []

    def bounded(**kwargs):
        if kwargs.get("state_limit") or kwargs.get("clause_limit"):
            seen.append(kwargs)
            assert kwargs["state_limit"] == 20_000 and kwargs["clause_limit"] == 50_000
            raise integer_native.EncodingBudgetExceeded(reason)
        return original(**kwargs)

    model = Model()
    xs = [model.int(f"x{i}", lb, lb + 2) for i, lb in enumerate([-2, 1, 0])]
    with patch.object(integer_native, "encode_pb", side_effect=bounded):
        model &= OPS[op](2 * xs[0] - 3 * xs[1] + 5 * xs[2] + 7, 5)
        cnf = model.to_cnf()
    assert seen and all(x._binary_view is not None for x in xs)
    # A failed speculative result cannot reserve any auxiliary IDs.
    assert (
        min(
            bit
            for v in [x._binary_view for x in xs if x._binary_view is not None]
            for bit in v
        )
        == seen[0]["top_id"] + 1
    )
    with Solver(name="g4", bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product(*(range(x.lb, x.ub + 1) for x in xs)):
            expected = OPS[op](2 * values[0] - 3 * values[1] + 5 * values[2] + 7, 5)
            assert solver.solve(assumptions=assignment(xs, values)) == expected


@pytest.fixture(params=["thresholds", "states", "clauses"])
def budget_route(request, monkeypatch):
    from hermax.encoder._integer_sum import weighted

    monkeypatch.setattr(weighted, "STATE_LIMIT", 1 if request.param == "states" else 0)
    monkeypatch.setattr(
        weighted, "CLAUSE_LIMIT", 1 if request.param == "clauses" else 0
    )
    return request.param


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("scale", [1, 7, 2**80])
def test_real_native_budget_routes_signed_shifted_scaled_sums(budget_route, op, scale):
    for bound in [-8, 1, 4, 12]:
        model = Model()
        xs = [model.int(f"x{i}", lb, lb + 3) for i, lb in enumerate([-2, 1, -1])]
        expr = scale * (2 * xs[0] - 3 * xs[1] + 5 * xs[2]) + 2
        model &= OPS[op](expr, scale * bound + 1)
        with Solver(name="g4", bootstrap_with=model.to_cnf().clauses) as solver:
            for vs in itertools.product(*(range(x.lb, x.ub + 1) for x in xs)):
                expected = OPS[op](
                    scale * (2 * vs[0] - 3 * vs[1] + 5 * vs[2]) + 2, scale * bound + 1
                )
                assert solver.solve(assumptions=assignment(xs, vs)) == expected


@pytest.mark.parametrize("op", ["<=", ">=", "==", "!="])
@pytest.mark.parametrize("mode", ["only_if", "iff", "gated_iff"])
def test_reification_does_not_guard_binary_channel_definitions(budget_route, op, mode):
    model = Model()
    xs = [model.int(f"x{i}", 0, 2) for i in range(3)]
    guard = model.bool("guard")
    result = model.bool("result")
    cmp = OPS[op](2 * xs[0] + 3 * xs[1] + 5 * xs[2], 7)
    constraint = (
        cmp.only_if(guard)
        if mode == "only_if"
        else cmp.iff(result)
        if mode == "iff"
        else cmp.only_if(guard).iff(result)
    )
    model &= constraint
    with Solver(name="g4", bootstrap_with=model.to_cnf().clauses) as solver:
        for vs in itertools.product(range(3), repeat=3):
            truth = OPS[op](2 * vs[0] + 3 * vs[1] + 5 * vs[2], 7)
            for gv, rv in itertools.product([False, True], repeat=2):
                expected = (
                    (not gv or truth)
                    if mode == "only_if"
                    else (rv == truth)
                    if mode == "iff"
                    else (rv == (not gv or truth))
                )
                ass = assignment(xs, vs) + [
                    guard.id if gv else -guard.id,
                    result.id if rv else -result.id,
                ]
                assert solver.solve(assumptions=ass) == expected


def test_binary_view_is_shared_with_unit_sum_path_and_defined_once(monkeypatch):
    from collections import Counter
    from hermax.encoder._integer_sum import weighted, selection, BINARY

    monkeypatch.setattr(weighted, "STATE_LIMIT", 1)
    model = Model()
    xs = [model.int(f"x{i}", 0, 5) for i in range(4)]
    model &= 2 * xs[0] + 3 * xs[1] + 5 * xs[2] + 7 * xs[3] <= 30
    model.to_cnf()
    views = tuple(x._binary_view for x in xs)
    monkeypatch.setattr(selection, "choose", lambda *a, **kw: BINARY)
    model &= sum(xs) >= 5
    model &= -2 * xs[0] + 3 * xs[1] - 5 * xs[2] + 7 * xs[3] >= -10
    model.to_cnf()
    assert tuple(x._binary_view for x in xs) == views
    counts = Counter(tuple(model._clause_to_dimacs_list(c)) for c in model._hard)
    for view in views:
        for bit in view:
            assert bit in model._realized_literal_defs
            assert all(counts[c] == 1 for c in model._pending_literal_defs[bit])


def test_budget_fallback_can_be_added_after_incremental_solver_binding(monkeypatch):
    from hermax.encoder._integer_sum import weighted

    model = Model()
    xs = [model.int(f"x{i}", 0, 4) for i in range(3)]
    model &= 2 * xs[0] + 3 * xs[1] + 5 * xs[2] >= 10
    assert model.solve(incremental=True, backend="sat").ok
    assert all(x._binary_view is None for x in xs)
    monkeypatch.setattr(weighted, "STATE_LIMIT", 1)
    model &= 2 * xs[0] + 3 * xs[1] + 5 * xs[2] <= 9
    assert model.solve(incremental=True, backend="sat").status == "unsat"
    assert all(x._binary_view is not None for x in xs)
    model.close_incremental()


def test_other_native_errors_are_not_silently_treated_as_budget_overflow(monkeypatch):
    def fail(**kwargs):
        raise ValueError("deliberate native error")

    model = Model()
    xs = [model.int(f"x{i}", 0, 3) for i in range(3)]
    monkeypatch.setattr(integer_native, "encode_pb", fail)
    with pytest.raises(ValueError, match="deliberate native error"):
        model &= 2 * xs[0] + 3 * xs[1] + 5 * xs[2] <= 12
    assert all(x._binary_view is None for x in xs)


def test_boolean_and_bivariate_constraints_keep_existing_routes(monkeypatch):
    original = integer_native.encode_pb

    def unbudgeted(**kwargs):
        assert not kwargs.get("state_limit") and not kwargs.get("clause_limit")
        return original(**kwargs)

    monkeypatch.setattr(integer_native, "encode_pb", unbudgeted)
    m = Model()
    bs = m.bool_vector("b", 4)
    m &= sum((i + 2) * b for i, b in enumerate(bs)) <= 7
    m.to_cnf()
    m = Model()
    x = m.int("x", 0, 3)
    y = m.int("y", 0, 3)
    m &= 2 * x + 3 * y <= 7
    m.to_cnf()
    assert x._binary_view is None and y._binary_view is None


def test_explicit_amo_structure_uses_binary_without_threshold_attempt(monkeypatch):
    from hermax.encoder._integer_sum import weighted

    def fail(*args, **kwargs):
        raise AssertionError("AMO integer sums must select Binary directly")

    monkeypatch.setattr(weighted, "encode_thresholds", fail)
    model = Model()
    xs = [model.int(f"x{i}", 0, 3) for i in range(3)]
    model &= ((xs[0] >= 1) + (xs[1] >= 1)) <= 1
    # Explicit structural metadata, as supplied by a group encoder.
    model._register_amo_group([(xs[0] >= 1).id, (xs[1] >= 1).id])
    model &= 2 * xs[0] + 3 * xs[1] + 5 * xs[2] <= 10
    cnf = model.to_cnf()
    assert all(x._binary_view is not None for x in xs)
    with Solver(name="g4", bootstrap_with=cnf.clauses) as solver:
        for vs in itertools.product(range(4), repeat=3):
            expected = (int(vs[0] >= 1) + int(vs[1] >= 1) <= 1) and 2 * vs[0] + 3 * vs[
                1
            ] + 5 * vs[2] <= 10
            assert solver.solve(assumptions=assignment(xs, vs)) == expected


def test_private_fallback_ids_clear_incremental_backend_reserved_range(monkeypatch):
    from hermax.encoder._integer_sum import weighted
    from tests.model.test_model_incremental_native import FakeIPSolver

    model = Model()
    xs = [model.int(f"x{i}", 0, 3) for i in range(3)]
    model.obj[1] += model.bool("soft")
    assert model.solve(incremental=True, backend="maxsat", solver=FakeIPSolver()).ok
    model._inc_state.ip_next_vid = 500
    monkeypatch.setattr(weighted, "STATE_LIMIT", 1)
    model &= 2 * xs[0] + 3 * xs[1] + 5 * xs[2] <= 12
    model.to_wcnf()
    assert (
        min(
            bit
            for view in [x._binary_view for x in xs if x._binary_view is not None]
            for bit in view
        )
        > 500
    )
    model.close_incremental()
