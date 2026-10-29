import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


def _fixed(model, variable, value):
    return [model._lit_to_dimacs(lit) for lit in variable._exact_value_atoms(value)]


@pytest.mark.parametrize("name", [None, "result"])
@pytest.mark.parametrize("lb,ub,divisor", [
    (0, 8, 10), (11, 18, 10), (-9, -1, 10), (-18, -11, 10),
    (10, 10, 10), (0, 0, 1),
])
def test_modulo_without_wrap_reuses_thresholds(lb, ub, divisor, name):
    m = Model()
    x = m.int("x", lb, ub)
    bits = x._get_binary_view()
    before = m._top_id(), len(m.to_cnf().clauses)
    out = m.modulo(x, divisor, name=name)
    assert (m._top_id(), len(m.to_cnf().clauses)) == before
    assert out._threshold_lits is x._threshold_lits
    assert out._get_binary_view() is bits
    assert (out.lb, out.ub) == (lb % divisor, ub % divisor)
    assert m.modulo(x, divisor) is m.modulo(x, divisor)
    if name is not None:
        assert out.name == name
        with pytest.raises(ValueError, match="already registered"):
            m.bool(name)
    elif lb // divisor == 0:
        assert out is x
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for value, remainder in itertools.product(range(lb, ub + 1), range(out.lb, out.ub + 1)):
            assert solver.solve(assumptions=_fixed(m, x, value) + _fixed(m, out, remainder)) is (
                remainder == value % divisor
            )
    m &= x == ub
    result = m.solve()
    assert result.ok and result[out] == ub % divisor


@pytest.mark.parametrize("lb,ub,divisor", [(2, 8, 3), (-4, 2, 3), (-3, 0, 3)])
def test_modulo_crossing_boundary_still_encodes_exact_remainder(lb, ub, divisor):
    m = Model()
    x = m.int("x", lb, ub)
    out = m.modulo(x, divisor)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for value, remainder in itertools.product(range(lb, ub + 1), range(divisor)):
            assert solver.solve(assumptions=_fixed(m, x, value) + _fixed(m, out, remainder)) is (
                remainder == value % divisor
            )


@pytest.mark.parametrize("operation", ["max", "min"])
@pytest.mark.parametrize("name", [None, "result"])
@pytest.mark.parametrize("touching", [False, True])
def test_domain_determined_extrema_reuse_winner(operation, name, touching):
    m = Model()
    low = m.int("low", -3, 0)
    high = m.int("high", 0 if touching else 1, 4)
    winner = high if operation == "max" else low
    bits = winner._get_binary_view()
    before = m._top_id(), len(m.to_cnf().clauses)
    out = getattr(m, operation)([low, high], name=name)
    assert (m._top_id(), len(m.to_cnf().clauses)) == before
    assert out._threshold_lits is winner._threshold_lits
    assert out._get_binary_view() is bits
    if name is None:
        assert out is winner
        assert getattr(m, operation)([high, low]) is out
    else:
        assert out.name == name and out is not winner
        with pytest.raises(ValueError, match="already registered"):
            m.bool(name)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, c in itertools.product(range(low.lb, low.ub + 1), range(high.lb, high.ub + 1),
                                         range(out.lb, out.ub + 1)):
            expected = max(a, b) if operation == "max" else min(a, b)
            assert solver.solve(assumptions=_fixed(m, low, a) + _fixed(m, high, b) + _fixed(m, out, c)) is (
                c == expected
            )


@pytest.mark.parametrize("operation", ["max", "min"])
def test_overlapping_domains_do_not_select_an_unproven_winner(operation):
    m = Model()
    x, y = m.int("x", -1, 2), m.int("y", 0, 3)
    out = getattr(m, operation)([x, y])
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, c in itertools.product(range(-1, 3), range(4), range(out.lb, out.ub + 1)):
            expected = max(a, b) if operation == "max" else min(a, b)
            assert solver.solve(assumptions=_fixed(m, x, a) + _fixed(m, y, b) + _fixed(m, out, c)) is (
                c == expected
            )


@pytest.mark.parametrize("operation", ["modulo", "max", "min"])
def test_domain_aliases_preserve_validation(operation):
    m = Model()
    x, y = m.int("x", 0, 2), m.int("y", 3, 5)
    m.bool("taken")
    before = m._top_id(), len(m._hard)
    with pytest.raises(ValueError, match="already registered"):
        if operation == "modulo":
            m.modulo(x, 10, name="taken")
        else:
            getattr(m, operation)([x, y], name="taken")
    assert (m._top_id(), len(m._hard)) == before
    foreign = Model().int("foreign", 0, 1)
    with pytest.raises(ValueError, match="different models"):
        if operation == "modulo":
            m.modulo(foreign, 10)
        else:
            getattr(m, operation)([x, foreign])


def test_modulo_alias_of_shifted_source_preserves_binary_owner_and_objective():
    m = Model()
    source = m.interval("job", start=0, duration=10, end=18).end
    bits = source._get_binary_view()
    before = m._top_id(), len(m.to_cnf().clauses)
    out = m.modulo(source, 10, name="remainder")
    assert out._get_binary_view() is bits
    assert (m._top_id(), len(m.to_cnf().clauses)) == before
    m &= source >= 13
    m.obj = out
    result = m.solve()
    assert result.ok and result[source] == 13 and result[out] == result.cost == 3


@pytest.mark.parametrize("operation", ["max", "min"])
@pytest.mark.parametrize("source_kind", ["boolean", "constant", "offset"])
def test_extreme_aliases_preserve_existing_integer_views(operation, source_kind):
    m = Model()
    if source_kind == "boolean":
        winner = m.as_int(~m.bool("flag"))
    elif source_kind == "constant":
        winner = m.as_int(3)
    else:
        winner = m.interval("job", start=0, duration=5, end=8).end
    boundary = winner.lb if operation == "max" else winner.ub
    lb, ub = (boundary - 2, boundary) if operation == "max" else (boundary, boundary + 2)
    other = m.int("other", lb, ub)
    before = m._top_id(), len(m.to_cnf().clauses)
    out = getattr(m, operation)([other, winner], name="result")
    assert out._threshold_lits is winner._threshold_lits
    assert (m._top_id(), len(m.to_cnf().clauses)) == before
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, c in itertools.product(range(winner.lb, winner.ub + 1), range(lb, ub + 1),
                                         range(out.lb, out.ub + 1)):
            assert solver.solve(assumptions=_fixed(m, winner, a) + _fixed(m, other, b) + _fixed(m, out, c)) is (c == a)
