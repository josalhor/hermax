import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.model.encoders import _EncoderDispatch


@pytest.mark.parametrize("n", [32, 33])
def test_direct_addition_cutoff(n, monkeypatch):
    calls = []
    original = _EncoderDispatch._compile_addition_eq_direct

    def record(*args):
        calls.append(True)
        return original(*args)

    monkeypatch.setattr(_EncoderDispatch, "_compile_addition_eq_direct", staticmethod(record))
    m = Model()
    x, y, z = [m.int(name, 0, n - 1) for name in ("x", "y", "z")]
    before = m._top_id()
    m &= x + y == z
    cnf = m.to_cnf()
    assert bool(calls) == (n == 32)
    if n == 32:
        assert cnf.nv == before


def test_direct_addition_propagates_every_fixed_input_pair():
    m = Model()
    x, y = m.int("x", 0, 31), m.int("y", 0, 31)
    d = m.int("d", 1, 31)
    m &= x + d == y
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b in itertools.combinations(range(32), 2):
            assumptions = []
            for variable, value in ((x, a), (y, b)):
                if value:
                    assumptions.append(variable._threshold_lits[value - 1].id)
                if value < 31:
                    assumptions.append(-variable._threshold_lits[value].id)
            ok, forced = solver.propagate(assumptions=assumptions)
            expected = {
                lit.id if index < b - a - 1 else -lit.id
                for index, lit in enumerate(d._threshold_lits)
            }
            assert ok and expected <= set(forced)


@pytest.mark.parametrize("mode", ["plain", "only_if", "iff"])
@pytest.mark.parametrize("offset", [-8, 0, 2, 8])
def test_direct_addition_shifted_truth_table(mode, offset):
    m = Model()
    x, y, z = m.int("x", -2, 2), m.int("y", 1, 3), m.int("z", -1, 4)
    flag = m.bool()
    condition = x + y == z + offset
    m &= condition if mode == "plain" else condition.only_if(flag) if mode == "only_if" else condition.iff(flag)
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, c, fv in itertools.product(range(-2, 3), range(1, 4), range(-1, 5), (False, True)):
            truth = a + b == c + offset
            expected = truth if mode == "plain" else (not fv or truth) if mode == "only_if" else fv == truth
            assumptions = [
                lit.id if index < value - variable.lb else -lit.id
                for variable, value in ((x, a), (y, b), (z, c))
                for index, lit in enumerate(variable._threshold_lits)
            ]
            assumptions.append(flag.id if fv else -flag.id)
            assert solver.solve(assumptions=assumptions) == expected
