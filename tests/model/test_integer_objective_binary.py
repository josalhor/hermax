import pytest
from pysat.solvers import Solver

from hermax.model import Model


@pytest.mark.parametrize(
    "width,cached,binary",
    [(15, True, False), (16, True, True), (31, False, False), (32, False, True)],
)
@pytest.mark.parametrize("style", ["direct", "expression", "set", "tier"])
def test_integer_objective_cutoffs(width, cached, binary, style):
    m = Model()
    x = m.int("x", 0, width)
    if cached:
        x._get_binary_view()
    if style == "direct":
        m.obj += x
    elif style == "expression":
        m.obj += 3 * x
    elif style == "set":
        m.obj = x
    else:
        m.tier_obj.add(x, weight=1, tier=0)
    assert (x._binary_view is not None) == (cached or binary)
    if style == "tier":
        count = len(m.tier_obj._tiers[0]["lit_weights"])
    else:
        count = sum(w > 0 for w, _ in m._soft)
    assert count == (width.bit_length() if binary else width)


@pytest.mark.parametrize("lb", [-5, 0, 7])
@pytest.mark.parametrize("coefficient", [-3, 2])
def test_binary_objective_exact_cost_for_every_value(lb, coefficient):
    m = Model()
    x = m.int("x", lb, lb + 32)
    b = m.bool("b")
    m.obj += 2 * (coefficient * x + 5 * b + 9)
    cnf = m.to_wcnf()
    assert x._binary_view is not None
    with Solver(bootstrap_with=cnf.hard) as solver:
        for value in range(x.lb, x.ub + 1):
            for boolean in (False, True):
                assumptions = [
                    lit.id if i < value - lb else -lit.id
                    for i, lit in enumerate(x._threshold_lits)
                ]
                assumptions.append(b.id if boolean else -b.id)
                assert solver.solve(assumptions=assumptions)
                assignment = set(solver.get_model())
                cost = m._objective_constant + sum(
                    w
                    for w, clause in m._soft
                    if not any(lit in assignment for lit in clause)
                )
                assert cost == 2 * (coefficient * value + 5 * boolean + 9)


def test_partial_threshold_expression_keeps_its_meaning():
    m = Model()
    x = m.int("x", 0, 32)
    m.obj += x >= 5
    assert x._binary_view is None
    assert len(m._soft) == 1


def test_binary_objective_reuses_view_and_realizes_channel():
    m = Model()
    x = m.int("x", 0, 16)
    bits = x._get_binary_view()
    top = m._top_id()
    m.obj += x
    assert x._binary_view is bits
    assert m._top_id() == top
    assert all(bit in m._realized_literal_defs for bit in bits)
    m &= x >= 13
    result = m.solve()
    assert result.ok and result[x] == 13 and result.cost == 13


def test_binary_objective_replacement_and_clear():
    m = Model()
    x = m.int("x", 0, 32)
    m &= x >= 13
    m.obj = x
    assert m.solve().cost == 13
    m.obj = -2 * x + 7
    result = m.solve()
    assert result[x] == 32 and result.cost == -57
    m.obj.clear()
    assert not any(w > 0 for w, _ in m._soft)


def test_nonuniform_threshold_cost_is_not_rewritten():
    m = Model()
    x = m.int("x", 0, 32)
    m.obj += x + 3 * (x >= 5)
    assert x._binary_view is None
    assert len(m._soft) == 32


def test_tier_binary_objective_solves_with_shifted_bound():
    m = Model()
    x = m.int("x", -7, 25)
    m &= x >= 13
    m.tier_obj.add(x, weight=2, tier=0)
    result = m.solve()
    assert result.ok and result[x] == 13
