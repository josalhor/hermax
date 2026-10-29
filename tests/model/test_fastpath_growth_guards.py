import itertools
from unittest.mock import patch

import pytest
from pysat.solvers import Solver

from hermax.encoder import _weighted_sum
from hermax.model import Model
from hermax.model import _integer_sum
from hermax.model.encoders import _EncoderDispatch


@pytest.mark.parametrize("warm", [False, True])
def test_large_weighted_equality_delegates_before_allocating_value_helpers(warm):
    model = Model()
    bits = model.bool_vector("b", 12)
    total = model.int("total", 0, 4095)
    if warm:
        for dim in total._get_binary_view():
            model._ensure_literal_def_realized(model._dimacs_to_lit(dim))
    before = len(model.to_cnf().clauses)
    with patch.object(_weighted_sum, "encode_best", side_effect=AssertionError("oversized fast path")):
        model &= total == sum((1 << i) * bit for i, bit in enumerate(bits))
    assert not total._eq_lits
    assert len(model.to_cnf().clauses) - before < 12000
    with Solver(bootstrap_with=model.to_cnf().clauses) as solver:
        for value in [0, 1, 137, 2048, 4095]:
            fixed = [bit.id if value & (1 << i) else -bit.id for i, bit in enumerate(bits)]
            for candidate in [value, (value + 1) % 4096]:
                cuts = [model._lit_to_dimacs(atom) for atom in total._exact_value_atoms(candidate)]
                assert solver.solve(assumptions=fixed + cuts) is (candidate == value)


def test_sparse_large_weights_keep_the_cheap_specialized_construction():
    model = Model()
    bits = model.bool_vector("b", 8)
    weights = [1001, 1002] * 4
    total = model.int("total", 0, sum(weights))
    before = len(model.to_cnf().clauses)
    with patch.object(_weighted_sum, "encode_best", wraps=_weighted_sum.encode_best) as encode:
        model &= total == sum(w * bit for w, bit in zip(weights, bits))
    assert encode.called
    assert len(model.to_cnf().clauses) - before < 1000


@pytest.mark.parametrize("warm", [False, True])
def test_weighted_growth_fallback_preserves_gating_and_reification(warm, monkeypatch):
    monkeypatch.setattr(_weighted_sum, "STATE_LIMIT", 1)
    monkeypatch.setattr(_weighted_sum, "CLAUSE_LIMIT", 1)
    model = Model()
    bits = model.bool_vector("b", 3)
    total = model.int("total", 0, 10)
    gate, flag = model.bool("gate"), model.bool("flag")
    if warm:
        for dim in total._get_binary_view():
            model._ensure_literal_def_realized(model._dimacs_to_lit(dim))
    with patch.object(_weighted_sum, "encode_best", side_effect=AssertionError("fast path should decline")):
        model &= (total == 2 * bits[0] + 3 * ~bits[1] + 5 * bits[2]).only_if(gate).iff(flag)
    with Solver(bootstrap_with=model.to_cnf().clauses) as solver:
        for values, value, g, f in itertools.product(
            itertools.product([False, True], repeat=3), range(11), [False, True], [False, True]
        ):
            numeric = 2 * values[0] + 3 * (not values[1]) + 5 * values[2]
            expected = f == (not g or value == numeric)
            atoms = [*total._exact_value_atoms(value), gate if g else ~gate, flag if f else ~flag]
            fixed = [bit.id if on else -bit.id for bit, on in zip(bits, values)]
            fixed.extend(model._lit_to_dimacs(atom) for atom in atoms)
            assert solver.solve(assumptions=fixed) is expected


@pytest.mark.parametrize("equality", [False, True])
def test_narrow_large_addition_stays_small(equality):
    model = Model()
    x, y = model.int("x", 0, 2048), model.int("y", 0, 2048)
    z = model.int("z", 0, 1)
    before = len(model.to_cnf().clauses)
    with patch("hermax.model.encoders.compile_sum", side_effect=AssertionError("tiny fast path was rejected")):
        model &= (x + y == z) if equality else (x + y <= z)
    formula = model.to_cnf()
    assert len(formula.clauses) - before < 30
    assert x._binary_view is y._binary_view is z._binary_view is None
    with Solver(bootstrap_with=formula.clauses) as solver:
        for xv, yv, zv in itertools.product([0, 1, 2, 2048], [0, 1, 2, 2048], [0, 1]):
            atoms = [atom for var, value in [(x, xv), (y, yv), (z, zv)]
                     for atom in var._exact_value_atoms(value)]
            expected = xv + yv == zv if equality else xv + yv <= zv
            assert solver.solve(assumptions=[model._lit_to_dimacs(atom) for atom in atoms]) is expected


@pytest.mark.parametrize("nx,ny,nz,bound", [(2, 3, 2, -1), (8, 8, 1, 1), (4, 4, 8, 8), (16, 8, 4, 13)])
def test_direct_addition_cost_matches_emitted_clauses(nx, ny, nz, bound):
    model = Model()
    x, y, z = model.int("x", 0, nx), model.int("y", 0, ny), model.int("z", 0, nz)
    result = _EncoderDispatch._compile_trivariate_int_pairwise_leq(model, x, y, z, bound - nz)
    assert _integer_sum.direct_addition_clause_count(nx, ny, nz, bound) == len(result)
