from hermax.internal import _encoding_policy as policy
import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.encoder._integer_sum.encoding import Costs, Size, WHOLE
from hermax.model import ClauseGroup, IntVector, Model
from hermax.model import _integer_sum


@pytest.mark.parametrize("comparison,estimate", [("<=", 40000), ("<=", 40001), ("==", 20000), ("==", 20001)])
def test_order_limit_counts_the_complete_equality(monkeypatch, comparison, estimate):
    monkeypatch.setattr(_integer_sum, "assess", lambda *args: Costs(Size(0, estimate), Size(0, estimate), 2))
    monkeypatch.setattr(_integer_sum.selection, "choose", lambda *args, **kwargs: WHOLE)
    routes = []
    m = Model()
    xs = m.int_vector("x", 4, 0, 3)
    monkeypatch.setattr(_integer_sum, "_encode_order_plan", lambda *args: routes.append("order") or ClauseGroup(m, []))
    monkeypatch.setattr(_integer_sum, "compile_binary_sum", lambda *args: routes.append("binary") or ClauseGroup(m, []))
    _integer_sum.compile_sum(m, [(x, 1) for x in xs], -6, comparison)
    total = estimate * (2 if comparison == "==" else 1)
    assert routes == (["binary"] if total > 40000 else ["order"] * (2 if comparison == "==" else 1))


@pytest.mark.parametrize("context", ["plain", "gated", "iff"])
@pytest.mark.parametrize("op", [operator.le, operator.ge, operator.eq])
def test_compact_weighted_route_matches_arithmetic(monkeypatch, context, op):
    from hermax.encoder._integer_sum import weighted

    monkeypatch.setattr(policy, "STATE_LIMIT", 1)
    from hermax.encoder.pb_enc import EncType

    original = _integer_sum.binary_pb
    encodings = []

    def record(*args, **kwargs):
        encodings.append(kwargs.get("encoding"))
        return original(*args, **kwargs)

    monkeypatch.setattr(_integer_sum, "binary_pb", record)
    m = Model()
    xs = [m.int("x", -2, 0), m.int("y", 1, 3), m.int("z", -1, 1)]
    gate = m.bool("gate")
    condition = op(2 * xs[0] - 3 * xs[1] + 5 * xs[2], -3)
    m &= condition if context == "plain" else condition.only_if(gate) if context == "gated" else condition.iff(gate)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product(range(-2, 1), range(1, 4), range(-1, 2)):
            for enabled in [False, True]:
                truth = op(2 * values[0] - 3 * values[1] + 5 * values[2], -3)
                expected = truth if context == "plain" else (not enabled or truth) if context == "gated" else enabled == truth
                atoms = [atom for x, value in zip(xs, values) for atom in x._exact_value_atoms(value)]
                atoms.append(gate if enabled else ~gate)
                assert solver.solve(assumptions=[m._lit_to_dimacs(atom) for atom in atoms]) == expected
    assert encodings and all(encoding == EncType.adder for encoding in encodings)


def test_sum_var_total_tree_limit_preserves_name_and_semantics(monkeypatch):
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 1)
    m = Model()
    xs = [m.int("x", -2, 0), m.int("y", 3, 5), m.int("z", -1, 1)]
    total = m.sum_var(xs, name="total")
    assert total.name == "total_step1"
    assert all(x._binary_view is not None for x in xs)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product(range(-2, 1), range(3, 6), range(-1, 2)):
            for candidate in range(total.lb, total.ub + 1):
                atoms = [atom for x, value in zip([*xs, total], [*values, candidate]) for atom in x._exact_value_atoms(value)]
                assert solver.solve(assumptions=[m._lit_to_dimacs(atom) for atom in atoms]) == (candidate == sum(values))


@pytest.mark.parametrize("n,width,mixed,backend", [(31, 40, False, "pairwise"), (32, 40, False, "bipartite"), (32, 40, True, "pairwise"), (32, 20, False, "pairwise")])
def test_all_different_auto_boundary(monkeypatch, n, width, mixed, backend):
    selected = []
    for name in ["pairwise", "bipartite"]:
        monkeypatch.setattr(IntVector, "_all_different_" + name, lambda self, name=name: selected.append(name) or ClauseGroup(self._model, []))
    m = Model()
    xs = [m.int(f"x{i}", 0, width + (i == 0 and mixed)) for i in range(n)]
    m &= IntVector(m, "xs", xs).all_different()
    assert selected == [backend]


def test_bipartite_uses_compact_amo_columns():
    m = Model()
    xs = m.int_vector("x", 32, 0, 40)
    m &= xs.all_different(backend="bipartite")
    assert m.to_cnf().nv < 3 * 32 * 41


def test_sum_tree_limit_is_inclusive_and_ignores_fixed_inputs(monkeypatch):
    estimate = _integer_sum._merge_clause_upper(2, 3, equality=True) + 4
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", estimate)
    assert not _integer_sum.sum_tree_exceeds_limit([0, 2, 0, 3])
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", estimate - 1)
    assert _integer_sum.sum_tree_exceeds_limit([0, 2, 0, 3])


def test_boolean_sum_var_obeys_count_limit(monkeypatch):
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 1)
    m = Model()
    xs = m.int_vector("x", 32, -3, -2)
    total = m.sum_var(xs)
    assert total._binary_view is not None
    assert all(len(x._threshold_lits) == 1 for x in xs)


@pytest.mark.parametrize("context", ["plain", "gated", "iff"])
def test_auto_bipartite_preserves_conditional_and_reified_semantics(context):
    m = Model()
    xs = m.int_vector("x", 32, -4, 35)
    gate = m.bool("gate")
    condition = xs.all_different()
    m &= condition if context == "plain" else condition.only_if(gate) if context == "gated" else condition.iff(gate)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for duplicate, enabled in itertools.product([False, True], repeat=2):
            values = list(range(-4, 28))
            if duplicate:
                values[-1] = values[0]
            atoms = [atom for x, value in zip(xs, values) for atom in x._exact_value_atoms(value)]
            atoms.append(gate if enabled else ~gate)
            expected = not duplicate if context == "plain" else (not enabled or not duplicate) if context == "gated" else enabled == (not duplicate)
            assert solver.solve(assumptions=[m._lit_to_dimacs(atom) for atom in atoms]) == expected


def test_large_boolean_total_declines_before_building_counter(monkeypatch):
    from hermax.model.encoders import _EncoderDispatch
    from hermax.model.expressions import sum_expr

    def oversized(*args, **kwargs):
        raise AssertionError("large count should use the compact route")

    monkeypatch.setattr(_EncoderDispatch, "_build_sequential_ge_counter", oversized)
    m = Model()
    bits = m.bool_vector("b", 4096)
    total = m.int("total", 0, 4096)
    m &= total == sum_expr(bits)
    cnf = m.to_cnf()
    assert cnf.nv < 20000
    assert len(cnf.clauses) < 120000


@pytest.mark.parametrize("upper_end", [False, True])
def test_large_count_with_narrow_requested_thresholds_keeps_counter(monkeypatch, upper_end):
    from hermax.model import encoders
    from hermax.model.expressions import sum_expr

    def unexpected(*args, **kwargs):
        raise AssertionError("narrow threshold request should keep the counter")

    monkeypatch.setattr(encoders, "compile_binary_sum", unexpected)
    m = Model()
    bits = m.bool_vector("b", 2048)
    lower = 2047 if upper_end else 0
    total = m.int("total", lower, lower + 1)
    m &= total == sum_expr(bits)
    assert total._binary_view is None


@pytest.mark.parametrize("context", ["iff", "implies"])
def test_large_reified_all_different_uses_value_collisions(monkeypatch, context):
    from hermax.model.variables import _BaseVector

    def quadratic(*args):
        raise AssertionError("large bipartite opposite must not compare every pair")

    monkeypatch.setattr(_BaseVector, "_not_all_different", quadratic)
    m = Model()
    xs = m.int_vector("x", 32, 0, 35)
    gate = m.bool("gate")
    condition = xs.all_different()
    m &= condition.iff(gate) if context == "iff" else condition.implies(gate)
    fixed = [atom for x, value in zip(xs[:29], range(29)) for atom in x._exact_value_atoms(value)]
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product([0, 29, 30, 31], repeat=3):
            distinct = len(set([*range(29), *values])) == 32
            atoms = fixed + [atom for x, value in zip(xs[29:], values) for atom in x._exact_value_atoms(value)]
            for enabled in [False, True]:
                assumptions = [m._lit_to_dimacs(atom) for atom in atoms]
                assumptions.append(m._lit_to_dimacs(gate if enabled else ~gate))
                expected = enabled == distinct if context == "iff" else not distinct or enabled
                assert solver.solve(assumptions=assumptions) == expected


@pytest.mark.parametrize("count", [1, 2, 3, 5, 8, 17, 32, 64])
def test_count_estimate_bounds_real_counter_clauses(count):
    from hermax.model._counting import count_clause_upper
    from hermax.model.encoders import _EncoderDispatch

    requests = [[1], [count], [1, count], range(1, count + 1)]
    if count > 2:
        requests += [[2], [count - 1], range(2, count)]
    for thresholds in requests:
        thresholds = sorted(set(thresholds))
        m = Model()
        bits = m.bool_vector("b", count)
        clauses, _ = _EncoderDispatch._build_sequential_ge_counter(m, bits, thresholds=thresholds)
        assert len(clauses) <= count_clause_upper(count, thresholds)


@pytest.mark.parametrize("at_limit", [False, True])
def test_boolean_count_limit_is_inclusive(monkeypatch, at_limit):
    from hermax.model._counting import count_clause_upper
    from hermax.model.expressions import sum_expr

    estimate = count_clause_upper(32, range(1, 33)) + 66
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", estimate if at_limit else estimate - 1)
    m = Model()
    bits = m.bool_vector("b", 32)
    total = m.int("total", 0, 32)
    m &= total == sum_expr(bits)
    assert (total._binary_view is None) == at_limit


@pytest.mark.parametrize("context", ["plain", "gated", "iff"])
@pytest.mark.parametrize("op", [operator.le, operator.lt, operator.ge, operator.gt, operator.eq])
@pytest.mark.parametrize("offset", [-3, 0, 4])
def test_compact_boolean_count_preserves_shifted_comparisons(monkeypatch, context, op, offset):
    from hermax.model.expressions import sum_expr

    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 1)
    m = Model()
    bits = m.bool_vector("b", 3)
    total = m.int("total", -2, 2)
    gate = m.bool("gate")
    condition = op(total, sum_expr([bits[0], ~bits[1], bits[2]]) + offset)
    m &= condition if context == "plain" else condition.only_if(gate) if context == "gated" else condition.iff(gate)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values, value, enabled in itertools.product(itertools.product([False, True], repeat=3), range(-2, 3), [False, True]):
            truth = op(value, values[0] + (not values[1]) + values[2] + offset)
            expected = truth if context == "plain" else (not enabled or truth) if context == "gated" else enabled == truth
            assumptions = [m._lit_to_dimacs(bit if on else ~bit) for bit, on in zip(bits, values)]
            assumptions.extend(m._lit_to_dimacs(atom) for atom in total._exact_value_atoms(value))
            assumptions.append(m._lit_to_dimacs(gate if enabled else ~gate))
            assert solver.solve(assumptions=assumptions) == expected
