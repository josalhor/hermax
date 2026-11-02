import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.encoder._integer_sum import weighted
from hermax.encoder._packed import _EncodedCNF
from hermax.internal._clause_storage import ClauseStorage
from hermax.model import Model
from hermax.model._weighted_integer_sum import compile_weighted_sum


def ready_views(model, items):
    for item in items:
        for bit in item._get_binary_view():
            literal = model._dimacs_to_lit(bit)
            model &= literal | ~literal


def test_cached_views_reduce_large_weighted_constraint():
    m = Model()
    xs = m.int_vector("x", 6, 0, 32)
    m.obj += sum(xs)
    views = [x._binary_view for x in xs]
    m &= sum(c * x for c, x in zip([2, 3, 4, 5, 2, 3], xs)) >= 150
    cnf = m.to_wcnf()
    assert cnf.nv < 1500
    assert len(cnf.hard) < 3000
    assert [x._binary_view for x in xs] == views


@pytest.mark.parametrize("state", ["absent", "allocated", "partial"])
def test_candidate_requires_every_binary_definition_to_be_realized(monkeypatch, state):
    m = Model()
    xs = m.int_vector("x", 3, 0, 3)
    ready_views(m, xs[:2])
    if state != "absent":
        bits = xs[2]._get_binary_view()
        if state == "partial":
            literal = m._dimacs_to_lit(bits[0])
            m &= literal | ~literal

    def unexpected(*args, **kwargs):
        pytest.fail("tried a candidate without fully realized binary views")

    monkeypatch.setattr(weighted, "encode_binary_views", unexpected, raising=False)
    compile_weighted_sum(m, [(x, c) for x, c in zip(xs, [2, 3, 5])], 7, ">=")


@pytest.mark.parametrize("clauses,auxiliaries,selected", [(10, 5, True), (11, 5, False), (10, 6, False)])
def test_candidate_margin_and_private_ids(monkeypatch, clauses, auxiliaries, selected):
    m = Model()
    xs = m.int_vector("x", 3, 0, 3)
    ready_views(m, xs)
    top = m._top_id()

    def encoding(count, extra):
        return _EncodedCNF(ClauseStorage([[1, -1]] * count), top + extra)

    def thresholds(*args, **kwargs):
        assert args[4] == top
        return encoding(20, 5)

    def binary(*args, **kwargs):
        assert args[4] == top
        return encoding(clauses, auxiliaries)

    monkeypatch.setattr(weighted, "encode_thresholds", thresholds)
    monkeypatch.setattr(weighted, "encode_binary_views", binary, raising=False)
    result = compile_weighted_sum(m, [(x, c) for x, c in zip(xs, [2, 3, 5])], 7, ">=")
    assert len(result) == (clauses if selected else 20)
    assert m._top_id() == top + 5
    assert m.bool("next").id == top + 6


def test_candidate_limit_retains_threshold_result(monkeypatch):
    m = Model()
    xs = m.int_vector("x", 3, 0, 3)
    ready_views(m, xs)
    top = m._top_id()
    expected = weighted.encode_thresholds(
        [[lit.id for lit in x._threshold_lits] for x in xs], [2, 3, 5], 7, ">=", top, _packed=True
    )
    attempted = []

    def limited(*args, **kwargs):
        attempted.append(True)
        raise weighted.BudgetExceeded("test candidate limit")

    monkeypatch.setattr(weighted, "encode_binary_views", limited, raising=False)
    result = compile_weighted_sum(m, [(x, c) for x, c in zip(xs, [2, 3, 5])], 7, ">=")
    assert attempted
    assert list(result.iter_dimacs()) == list(map(tuple, expected.clauses))
    assert m._top_id() == expected.nv


@pytest.mark.parametrize("mode", ["plain", "only_if", "iff"])
@pytest.mark.parametrize("op", [operator.le, operator.ge, operator.eq, operator.ne])
def test_cached_candidate_preserves_signed_shifted_arithmetic(monkeypatch, mode, op):
    original = weighted.encode_thresholds

    def larger_equivalent(*args, **kwargs):
        cnf = original(*args, **kwargs)
        # Equivalent duplicates and spare IDs force the candidate branch on tiny domains.
        cnf.clauses = ClauseStorage([row for row in cnf.clauses for _ in range(20)])
        cnf.nv += 1000
        return cnf

    monkeypatch.setattr(weighted, "encode_thresholds", larger_equivalent)
    m = Model()
    xs = [m.int("x", -2, 1), m.int("y", 1, 4), m.int("z", 0, 3)]
    ready_views(m, xs)
    gate = m.bool("gate")
    condition = op(2 * xs[0] - 3 * xs[1] + 5 * xs[2] + 7, 5)
    m &= condition if mode == "plain" else getattr(condition, mode)(gate)
    cnf = m.to_cnf()
    assert cnf.nv < 1000, "the discarded threshold candidate reserved its IDs"
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product(*(range(x.lb, x.ub + 1) for x in xs)):
            truth = op(2 * values[0] - 3 * values[1] + 5 * values[2] + 7, 5)
            atoms = [m._lit_to_dimacs(atom) for x, value in zip(xs, values)
                     for atom in x._exact_value_atoms(value)]
            for enabled in (False, True):
                expected = truth if mode == "plain" else not enabled or truth if mode == "only_if" else enabled == truth
                assert solver.solve(assumptions=atoms + [gate.id if enabled else -gate.id]) == expected
