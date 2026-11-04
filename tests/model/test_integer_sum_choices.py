import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import Model, sum_expr
from hermax.model import _integer_sum as sums
from hermax.model import _sum_choices as choices


@pytest.mark.parametrize("count,width,bound,expected", [
    (4, 3, 6, "direct"), (8, 3, 12, "tree"),
    (4, 31, 62, "current"), (8, 31, 2, "tree"), (10, 2, 10, "tree"),
])
def test_default_choices(count, width, bound, expected, monkeypatch):
    selected = []
    original = sums.choose_sum_encoding

    def record(*args):
        result = original(*args)
        selected.append(result[0])
        return result

    monkeypatch.setattr(sums, "choose_sum_encoding", record)
    m = Model()
    xs = [m.int(f"x{i}", 0, width) for i in range(count)]
    m &= sum_expr(xs) == bound
    assert selected[0] == expected
    assert m.solve(time_limit=2).ok


@pytest.mark.parametrize("kind", ["current", "direct", "tree"])
@pytest.mark.parametrize("op", ["<=", "<", ">=", ">", "=="])
@pytest.mark.parametrize("signed", [False, True])
@pytest.mark.parametrize("mode", ["post", "only_if", "iff", "gated_iff"])
def test_three_encodings_signed_shifted_truth_tables(kind, op, signed, mode, monkeypatch):
    def force(widths, bound, comparator, clauses, variables):
        if kind == "tree":
            if len(widths) < 4:
                return "current", None
            return "tree", choices._tree_plan(widths, bound, comparator, 100000)
        return kind, None

    monkeypatch.setattr(sums, "choose_sum_encoding", force)
    m = Model()
    xs = [m.int(f"x{i}", -1, 1) for i in range(4)]
    coefficients = [1, -1, 1, -1] if signed else [1] * 4
    gate, flag = m.bool(), m.bool()
    compare = {"<=": operator.le, "<": operator.lt, ">=": operator.ge, ">": operator.gt, "==": operator.eq}[op]
    condition = compare(sum_expr(c*x for c, x in zip(coefficients, xs)) + 2, 3)
    if mode == "only_if":
        condition = condition.only_if(gate)
    elif mode == "iff":
        condition = condition.iff(flag)
    elif mode == "gated_iff":
        condition = condition.only_if(gate).iff(flag)
    m &= condition
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for values, gv, fv in itertools.product(itertools.product(range(-1, 2), repeat=4), (False, True), (False, True)):
            truth = compare(sum(c*v for c, v in zip(coefficients, values)) + 2, 3)
            expected = {"post": truth, "only_if": not gv or truth,
                        "iff": fv == truth, "gated_iff": fv == (not gv or truth)}[mode]
            assumptions = [lit.id if i < value-x.lb else -lit.id
                           for x, value in zip(xs, values) for i, lit in enumerate(x._threshold_lits)]
            assumptions += [gate.id if gv else -gate.id, flag.id if fv else -flag.id]
            assert solver.solve(assumptions=assumptions) == expected


def test_direct_counter_respects_budget():
    assert choices.direct_clause_count([31] * 8, 124, "==", 1000) == 1001
    assert choices.direct_clause_count([31] * 8, 2, "==", 1000) == 128


def test_clause_cap_and_score_tiebreak():
    widths, bound = [3] * 3, 4
    direct = choices.direct_clause_count(widths, bound, "==", 1000)
    # No tree for three operands: isolate direct-vs-current policy decisions.
    assert choices.choose_sum_encoding(widths, bound, "==", direct // 2, 100)[0] == "current"
    assert choices.choose_sum_encoding(widths, bound, "==", direct, 0)[0] == "direct"


def test_unposted_tree_does_not_constrain_original_integers():
    m = Model()
    xs = [m.int(f"x{i}", 0, 2) for i in range(10)]
    condition = sum_expr(xs) == 10
    condition.clauses()  # Compile the intermediate domains without posting equations.
    for x in xs:
        m &= x == 0
    assert m.solve().ok
    m &= condition
    assert not m.solve().ok


def test_tree_preserves_bounds_propagation():
    m = Model()
    xs = [m.int(f"x{i}", 0, 2) for i in range(10)]
    m &= sum_expr(xs) == 10
    assumptions = [lit.id if i < 1 else -lit.id
                   for x in xs[:-1] for i, lit in enumerate(x._threshold_lits)]
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        ok, forced = solver.propagate(assumptions=assumptions)
        assert ok
        assert xs[-1]._threshold_lits[0].id in forced
        assert -xs[-1]._threshold_lits[1].id in forced


def test_tree_after_incremental_sat_solve():
    m = Model()
    xs = [m.int(f"x{i}", 0, 2) for i in range(10)]
    m &= xs[0] >= 1
    assert m.solve(incremental=True, backend="sat").ok
    m &= sum_expr(xs) == 10
    result = m.solve(incremental=True, backend="sat")
    assert result.ok
    assert sum(result[x] for x in xs) == 10


def test_tree_allocations_avoid_incremental_backend_ids():
    from tests.model.test_model_incremental_native import FakeIPSolver

    m = Model()
    xs = [m.int(f"x{i}", 0, 2) for i in range(10)]
    m.obj += m.bool("soft")
    assert m.solve(incremental=True, backend="maxsat", solver=FakeIPSolver()).ok
    before, hard = m._top_id(), len(m._hard)
    m._inc_state.ip_next_vid = 500
    m &= sum_expr(xs) == 10
    cnf = m.to_wcnf()
    assert cnf.nv > 500
    assert all(not before < abs(lit) <= 500 for row in m._hard[hard:] for lit in row)
    m.close_incremental()
