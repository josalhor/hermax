import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.encoder._integer_sum import selection, weighted

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


def no_threshold_attempt(*args, **kwargs):
    raise AssertionError("AMO integer route must go directly to binary")


@pytest.mark.parametrize("group", ["amo", "eo"])
@pytest.mark.parametrize("negated", [False, True])
@pytest.mark.parametrize("op", OPS)
def test_amo_weighted_integer_route_is_direct_and_exact(
    group, negated, op, monkeypatch
):
    m = Model()
    xs = [m.int("x", -1, 1), m.int("y", 0, 2), m.int("z", 1, 3)]
    bs = m.bool_vector("b", 2)
    g, r = m.bool("g"), m.bool("r")
    literals = [~b if negated else b for b in bs]
    m &= sum(literals) == 1 if group == "eo" else sum(literals) <= 1
    m.to_cnf()
    assert m._known_eo_groups if group == "eo" else m._known_amo_groups
    monkeypatch.setattr(weighted, "encode_thresholds", no_threshold_attempt)
    expression = (
        4 * xs[0] - 6 * xs[1] + 10 * xs[2] + 2 * literals[0] + 4 * literals[1] + 3
    )
    m &= OPS[op](expression, 11).only_if(g).iff(r)
    cnf = m.to_cnf()
    assert all(x._binary_view is not None for x in xs)
    for values in itertools.product(range(-1, 2), range(3), range(1, 4)):
        with Solver(bootstrap_with=cnf.clauses) as solver:
            for b0, b1, gv, rv in itertools.product([False, True], repeat=4):
                terms = [not b0, not b1] if negated else [b0, b1]
                structure = sum(terms) == 1 if group == "eo" else sum(terms) <= 1
                truth = OPS[op](
                    4 * values[0]
                    - 6 * values[1]
                    + 10 * values[2]
                    + 2 * terms[0]
                    + 4 * terms[1]
                    + 3,
                    11,
                )
                expected = structure and rv == (not gv or truth)
                ass = fixed(xs, values) + [
                    b.id if v else -b.id for b, v in zip([*bs, g, r], [b0, b1, gv, rv])
                ]
                assert solver.solve(assumptions=ass) == expected


@pytest.mark.parametrize("strategy", ["whole", "binary"])
def test_uniform_integer_amo_sums_keep_the_existing_selector(strategy, monkeypatch):
    m = Model()
    xs = [m.int(f"x{i}", 0, 3) for i in range(3)]
    bs = m.bool_vector("b", 2)
    m &= bs.at_most_one()
    m.to_cnf()
    calls = []

    def choose(*args, **kwargs):
        calls.append(True)
        return strategy

    monkeypatch.setattr(selection, "choose", choose)
    monkeypatch.setattr(weighted, "encode_thresholds", no_threshold_attempt)
    m &= sum(xs) + sum(bs) <= 5
    cnf = m.to_cnf()
    assert calls
    assert all((x._binary_view is not None) == (strategy == "binary") for x in xs)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product(range(4), repeat=3):
            for b0, b1 in itertools.product([False, True], repeat=2):
                ass = fixed(xs, values) + [
                    bs[0].id if b0 else -bs[0].id,
                    bs[1].id if b1 else -bs[1].id,
                ]
                assert solver.solve(assumptions=ass) == (
                    b0 + b1 <= 1 and sum(values) + b0 + b1 <= 5
                )


def test_pure_boolean_weighted_amo_keeps_pbamo_routing(monkeypatch):
    from hermax.encoder.pbamo import PBAMOEnc

    m = Model()
    bs = m.bool_vector("b", 4)
    m &= bs[0] + bs[1] <= 1
    m.to_cnf()
    calls = []
    original = PBAMOEnc.auto_leq

    def wrapped(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(PBAMOEnc, "auto_leq", staticmethod(wrapped))
    monkeypatch.setattr(weighted, "encode_thresholds", no_threshold_attempt)
    m &= 2 * bs[0] + 3 * bs[1] + 5 * bs[2] + 7 * bs[3] <= 8
    cnf = m.to_cnf()
    assert calls
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product([False, True], repeat=4):
            expected = (
                sum(values[:2]) <= 1
                and sum(c * v for c, v in zip([2, 3, 5, 7], values)) <= 8
            )
            assert (
                solver.solve(
                    assumptions=[b.id if v else -b.id for b, v in zip(bs, values)]
                )
                == expected
            )


def test_amo_binary_route_reuses_views_and_works_after_incremental_binding(monkeypatch):
    m = Model()
    xs = [m.int(f"x{i}", 0, 3) for i in range(3)]
    bs = m.bool_vector("b", 2)
    m &= bs.at_most_one()
    assert m.solve(incremental=True, backend="sat").ok
    try:
        monkeypatch.setattr(weighted, "encode_thresholds", no_threshold_attempt)
        m &= 2 * xs[0] + 3 * xs[1] + 5 * xs[2] + bs[0] + bs[1] <= 10
        assert m.solve(incremental=True, backend="sat").ok
        views = tuple(x._binary_view for x in xs)
        assert all(v is not None for v in views)
        m &= 2 * xs[0] + 3 * xs[1] + 5 * xs[2] + bs[0] + bs[1] >= 11
        assert tuple(x._binary_view for x in xs) == views
        assert m.solve(incremental=True, backend="sat").status == "unsat"
    finally:
        m.close_incremental()


def test_reported_amo_case_builds_without_a_speculative_attempt():
    import subprocess
    import sys

    pytest.importorskip("resource")
    code = """
import resource
resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
from hermax.model import Model
from hermax.encoder._integer_sum import weighted
m=Model();xs=[m.int(f'x{i}',0,512) for i in range(6)];bs=m.bool_vector('b',2)
m &= bs.at_most_one()
m.to_cnf()
def fail(*args,**kwargs):
    raise AssertionError('must not attempt the threshold encoding')
weighted.encode_thresholds=fail
m &= sum(c*x for c,x in zip([5,11,17,23,31,49],xs))+sum(bs)<=34816
cnf=m.to_cnf()
assert all(x._binary_view is not None for x in xs)
assert len(cnf.clauses)<35000
assert frozenset([-bs[0].id,-bs[1].id]) in [frozenset(c) for c in cnf.clauses]
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0, result.stderr


def test_amo_binary_ids_clear_incremental_backend_reserved_range(monkeypatch):
    from tests.model.test_model_incremental_native import FakeIPSolver

    m = Model()
    xs = [m.int(f"x{i}", 0, 3) for i in range(3)]
    bs = m.bool_vector("b", 2)
    m &= bs.at_most_one()
    m.obj[1] += m.bool("soft")
    assert m.solve(incremental=True, backend="maxsat", solver=FakeIPSolver()).ok
    try:
        m._inc_state.ip_next_vid = 500
        monkeypatch.setattr(weighted, "encode_thresholds", no_threshold_attempt)
        m &= 2 * xs[0] + 3 * xs[1] + 5 * xs[2] + sum(bs) <= 12
        m.to_wcnf()
        assert min(bit for x in xs for bit in x._binary_view) > 500
    finally:
        m.close_incremental()
