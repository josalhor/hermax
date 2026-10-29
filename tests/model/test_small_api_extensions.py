import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


@pytest.mark.parametrize("value", range(-2, 3))
def test_integer_unary_minus_reuses_scalar_arithmetic(value):
    m = Model()
    x = m.int("x", -2, 2)
    top, hard = m._next_id, len(m._hard)
    negative = -x
    assert m._next_id == top and len(m._hard) == hard
    m &= x == value
    m.obj = negative
    result = m.solve()
    assert result.cost == -value and result[negative] == -value


def test_maximum_accepts_literals_and_constants_with_exact_values():
    m = Model()
    x = m.int("x", -2, 2)
    b = m.bool("b")
    maximum = m.max([x, ~b, 0, False, -1])
    cnf = m.to_cnf()
    with Solver(name="g4", bootstrap_with=cnf.clauses) as solver:
        for xv, bv, mv in itertools.product(
            range(-2, 3), (False, True), range(maximum.lb, maximum.ub + 1)
        ):
            fixed = [
                m._lit_to_dimacs(lit)
                for v, value in [(x, xv), (maximum, mv)]
                for lit in v._exact_value_atoms(value)
            ]
            fixed.append(m._lit_to_dimacs(b if bv else ~b))
            assert solver.solve(assumptions=fixed) is (mv == max(xv, not bv, 0))


def test_normalized_maximum_retains_operation_caching():
    m = Model()
    b = m.bool("b")
    x = m.int("x", -1, 2)
    result = m.max([x, b, 1])
    top, hard = m._next_id, len(m._hard)
    assert m.max([1, x, b]) is result
    assert (m._next_id, len(m._hard)) == (top, hard)


@pytest.mark.parametrize("kind", ["literal", "constant"])
def test_maximum_singleton_conversion_adds_no_sat_variables(kind):
    m = Model()
    b = m.bool("b")
    top, hard = m._next_id, len(m._hard)
    m.max([b if kind == "literal" else 3])
    assert (m._next_id, len(m._hard)) == (top, hard)


def test_maximum_conversion_matches_explicit_integer_views():
    results = []
    for convert in (False, True):
        m = Model()
        b = m.bool("b")
        x = m.int("x", -1, 2)
        items = [m.as_int(b), m.as_int(1), x] if convert else [b, 1, x]
        m.max(items)
        cnf = m.to_cnf()
        results.append((cnf.nv, cnf.clauses))
    assert results[0] == results[1]


def test_maximum_invalid_inputs_do_not_allocate_an_output():
    m = Model()
    x = m.int("x", 0, 3)
    top, hard = m._next_id, len(m._hard)
    with pytest.raises(TypeError):
        m.max([x, x + 1])
    with pytest.raises(TypeError):
        m.max([x, 1.5])
    with pytest.raises(ValueError, match="different models"):
        m.max([x, Model().bool("foreign")])
    assert (m._next_id, len(m._hard)) == (top, hard)


def test_symbolic_column_index_reuses_the_existing_element_view():
    m = Model()
    grid = m.int_matrix("grid", 2, 3, 0, 4)
    index = m.int("index", 0, 2)
    top, hard = m._next_id, len(m._hard)
    element = grid[1, index]
    assert (m._next_id, len(m._hard)) == (top, hard)
    m &= grid[1, 0] == 4
    m &= grid[1, 1] == 2
    m &= grid[1, 2] == 3
    m &= index == 1
    m &= element == 2
    assert m.solve().ok
    m &= grid[1][index] != 2
    assert not m.solve().ok


def test_symbolic_matrix_row_remains_unsupported():
    m = Model()
    grid = m.int_matrix("grid", 2, 3, 0, 4)
    index = m.int("index", 0, 1)
    with pytest.raises(TypeError):
        _ = grid[index, 0]


@pytest.mark.parametrize("kind", ["division", "scale", "aggregate"])
def test_maximum_materializes_existing_lazy_integer_operations(kind):
    m = Model()
    x = m.int("x", 0, 6)
    y = m.int("y", 0, 4)
    operation = (
        x // 2
        if kind == "division"
        else x.scale(-1)
        if kind == "scale"
        else m.vector([x, y]).max()
    )
    maximum = m.max([operation, y])
    assert m.max([operation, y]) is maximum
    if kind == "division":
        assert m.max([x // 2, y]) is maximum
    m &= x == 6
    m &= y == 2
    result = m.solve()
    assert result[maximum] == (3 if kind == "division" else 2 if kind == "scale" else 6)


def test_bad_maximum_inputs_do_not_realize_other_lazy_arguments():
    m = Model()
    x = m.int("x", 0, 6)
    lazy = x // 2
    top, hard = m._next_id, len(m._hard)
    with pytest.raises(TypeError):
        m.max([lazy, x + 1])
    assert lazy._realized is None
    with pytest.raises(ValueError):
        m.max([lazy, Model().int("foreign", 0, 2)])
    assert lazy._realized is None
    assert (m._next_id, len(m._hard)) == (top, hard)


@pytest.mark.parametrize("name", ["taken", "__reserved", 12])
def test_invalid_maximum_name_does_not_realize_lazy_inputs(name):
    m = Model()
    x, y = m.int("x", 0, 100), m.int("y", 0, 100)
    m.bool("taken")
    quotient = x // 2
    before = m._next_id, len(m._hard), len(m._pending_literal_defs)

    with pytest.raises((ValueError, TypeError)):
        m.max([quotient, y], name=name)

    assert (m._next_id, len(m._hard), len(m._pending_literal_defs)) == before
    assert quotient._realized is None


def test_singleton_maximum_still_returns_its_input_without_using_name():
    m = Model()
    x = m.int("x", 0, 4)
    m.bool("taken")
    assert m.max([x], name="taken") is x
