import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.encoder._integer_sum.encoding import Costs, Size, WHOLE
from hermax.model import ClauseGroup, IntVector, Model
from hermax.model import _integer_sum


@pytest.mark.parametrize("comparison,estimate", [("<=", 50000), ("<=", 50001), ("==", 25000), ("==", 25001)])
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
    assert routes == (["binary"] if total > 50000 else ["order"] * (2 if comparison == "==" else 1))


@pytest.mark.parametrize("context", ["plain", "gated", "iff"])
@pytest.mark.parametrize("op", [operator.le, operator.ge, operator.eq])
def test_compact_weighted_route_matches_arithmetic(monkeypatch, context, op):
    from hermax.encoder._integer_sum import weighted

    monkeypatch.setattr(weighted, "STATE_LIMIT", 1)
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
    monkeypatch.setattr(_integer_sum, "UNARY_CLAUSE_LIMIT", 1)
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
    monkeypatch.setattr(_integer_sum, "UNARY_CLAUSE_LIMIT", estimate)
    assert not _integer_sum.sum_tree_exceeds_limit([0, 2, 0, 3])
    monkeypatch.setattr(_integer_sum, "UNARY_CLAUSE_LIMIT", estimate - 1)
    assert _integer_sum.sum_tree_exceeds_limit([0, 2, 0, 3])


def test_boolean_sum_var_keeps_strong_counter_even_with_small_tree_limit(monkeypatch):
    monkeypatch.setattr(_integer_sum, "UNARY_CLAUSE_LIMIT", 1)
    m = Model()
    xs = m.int_vector("x", 32, -3, -2)
    total = m.sum_var(xs)
    assert total._binary_view is None
    assert all(x._binary_view is None for x in xs)


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
