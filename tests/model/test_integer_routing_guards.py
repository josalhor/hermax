import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.encoder._integer_sum import selection, weighted
from hermax.model import _integer_sum

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


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("negated_bool", [False, True])
def test_mixed_weighted_budget_fallback_is_exact(op, negated_bool, monkeypatch):
    monkeypatch.setattr(weighted, "STATE_LIMIT", 1)
    m = Model()
    xs = [m.int("x", -2, 0), m.int("y", 1, 3), m.int("z", 0, 2)]
    b = m.bool("b")
    g = m.bool("g")
    r = m.bool("r")
    expr = 2 * xs[0] - 3 * xs[1] + 7 * xs[2] + 5 * (~b if negated_bool else b) + 7
    m &= OPS[op](expr, 1).only_if(g).iff(r)
    cnf = m.to_cnf()
    assert all(x._binary_view is not None for x in xs)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for xv, yv, zv, bv, gv, rv in itertools.product(
            range(-2, 1),
            range(1, 4),
            range(3),
            [False, True],
            [False, True],
            [False, True],
        ):
            numeric = OPS[op](
                2 * xv - 3 * yv + 7 * zv + 5 * (not bv if negated_bool else bv) + 7, 1
            )
            expected = rv == (not gv or numeric)
            assert (
                solver.solve(
                    assumptions=fixed(xs, [xv, yv, zv])
                    + [
                        b.id if bv else -b.id,
                        g.id if gv else -g.id,
                        r.id if rv else -r.id,
                    ]
                )
                == expected
            )


@pytest.mark.parametrize("op", OPS)
def test_three_term_uniform_sums_reach_selector(op, monkeypatch):
    calls = []

    def choose(*args, **kwargs):
        calls.append(args)
        return "binary"

    monkeypatch.setattr(selection, "choose", choose)
    m = Model()
    xs = [m.int(f"x{i}", 0, 2) for i in range(3)]
    m &= OPS[op](sum(xs), 2)
    cnf = m.to_cnf()
    assert calls
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product(range(3), repeat=3):
            assert solver.solve(assumptions=fixed(xs, values)) == OPS[op](
                sum(values), 2
            )


@pytest.mark.parametrize("op", ["==", "<=", "<"])
def test_large_adder_budget_routes_to_binary_with_correct_offsets(op, monkeypatch):
    monkeypatch.setattr(_integer_sum, "UNARY_CLAUSE_LIMIT", 1)
    m = Model()
    xs = [m.int("x", -2, 0), m.int("y", 1, 3), m.int("z", -1, 3)]
    g = m.bool("g")
    b = m.bool("b")
    m &= OPS[op](xs[0] + xs[1] + 1, xs[2]).only_if(g).iff(b)
    cnf = m.to_cnf()
    assert all(x._binary_view is not None for x in xs)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for x, y, z, gv, bv in itertools.product(
            range(-2, 1), range(1, 4), range(-1, 4), [False, True], [False, True]
        ):
            expected = bv == (not gv or OPS[op](x + y + 1, z))
            assert (
                solver.solve(
                    assumptions=fixed(xs, [x, y, z])
                    + [g.id if gv else -g.id, b.id if bv else -b.id]
                )
                == expected
            )


def test_reported_mixed_weighted_case_has_bounded_construction():
    import subprocess
    import sys

    pytest.importorskip("resource")
    code = """
import resource
resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
from hermax.model import Model
m=Model()
xs=[m.int(f'x{i}',0,512) for i in range(6)]
b=m.bool('b')
m &= sum(c*x for c,x in zip([5,11,17,23,31,49],xs))+b<=34816
cnf=m.to_cnf()
assert all(x._binary_view is not None for x in xs)
assert len(cnf.clauses)<40000
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("op", OPS)
def test_uniform_sum_with_raw_boolean_reaches_selector(op, monkeypatch):
    calls = []

    def choose(*args, **kwargs):
        calls.append(args)
        return "binary"

    monkeypatch.setattr(selection, "choose", choose)
    m = Model()
    xs = [m.int(f"x{i}", 0, 2) for i in range(3)]
    b = m.bool("b")
    m &= OPS[op](sum(xs) + b, 3)
    cnf = m.to_cnf()
    assert calls
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product(range(3), repeat=3):
            for bv in (False, True):
                assert solver.solve(
                    assumptions=fixed(xs, values) + [b.id if bv else -b.id]
                ) == OPS[op](sum(values) + bv, 3)


def test_complemented_complete_threshold_chain_uses_binary_safely(monkeypatch):
    monkeypatch.setattr(weighted, "STATE_LIMIT", 1)
    m = Model()
    xs = [m.int("x", -2, 1), m.int("y", 1, 4), m.int("z", 0, 3)]
    b = m.bool("b")
    expr = sum(~lit for lit in xs[0]._threshold_lits) + 2 * xs[1] + 3 * xs[2] + 5 * b
    m &= expr <= 9
    cnf = m.to_cnf()
    assert all(x._binary_view is not None for x in xs)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for x, y, z, bv in itertools.product(
            range(-2, 2), range(1, 5), range(4), [False, True]
        ):
            assert solver.solve(
                assumptions=fixed(xs, [x, y, z]) + [b.id if bv else -b.id]
            ) == ((1 - x) + 2 * y + 3 * z + 5 * bv <= 9)


def test_unary_guard_matches_network_upper_count_and_is_inclusive(monkeypatch):
    from hermax.utils import batcher_odd_even_unary_add_network

    for left, right in [(1, 1), (2, 7), (31, 32), (128, 128)]:
        comparisons = len(batcher_odd_even_unary_add_network(left, right))
        cost = 6 * comparisons + 2 * (left + right + 2)
        monkeypatch.setattr(_integer_sum, "UNARY_CLAUSE_LIMIT", cost)
        assert not _integer_sum.unary_sum_too_large(left, right, equality=True)
        monkeypatch.setattr(_integer_sum, "UNARY_CLAUSE_LIMIT", cost - 1)
        assert _integer_sum.unary_sum_too_large(left, right, equality=True)


@pytest.mark.parametrize("op", ["==", "<="])
def test_large_adder_switches_before_network_construction(op, monkeypatch):
    import hermax.model.encoders as encoders

    def fail(*args):
        raise AssertionError("large unary network must not be constructed")

    monkeypatch.setattr(encoders, "batcher_odd_even_unary_add_network", fail)
    m = Model()
    x = m.int("x", 0, 2000)
    y = m.int("y", 0, 2000)
    z = m.int("z", 0, 4000)
    m &= OPS[op](x + y, z)
    cnf = m.to_cnf()
    assert all(v._binary_view is not None for v in (x, y, z))
    assert len(cnf.clauses) < 30000


@pytest.mark.parametrize("scale", [1, 7, 2**80])
@pytest.mark.parametrize("op", OPS)
def test_mixed_uniform_gcd_and_negative_boolean_are_exact(scale, op, monkeypatch):
    monkeypatch.setattr(selection, "choose", lambda *args, **kwargs: "binary")
    m = Model()
    xs = [m.int("x", -1, 1), m.int("y", 0, 2), m.int("z", 1, 3)]
    b = m.bool("b")
    m &= OPS[op](scale * (xs[0] - xs[1] + xs[2] - (~b)) + 2, 3)
    cnf = m.to_cnf()
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for x, y, z, bv in itertools.product(
            range(-1, 2), range(3), range(1, 4), [False, True]
        ):
            assert solver.solve(
                assumptions=fixed(xs, [x, y, z]) + [b.id if bv else -b.id]
            ) == OPS[op](scale * (x - y + z - (not bv)) + 2, 3)
