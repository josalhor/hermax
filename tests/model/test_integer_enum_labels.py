import itertools
from pathlib import Path
import runpy

import pytest
from pysat.solvers import Solver

from hermax.model import Model


@pytest.mark.parametrize("backend", ["auto", "pairwise", "bipartite"])
def test_integer_enum_all_different_and_decoding(backend):
    m = Model()
    values = m.enum_vector("v", 3, choices=[1, 3, 7])
    m &= values.all_different(backend)
    m &= values[0] == 3
    m &= values[1].is_in([1])
    result = m.solve()
    assert result[values] == [3, 1, 7]
    assert all(type(v) is int for v in result[values])


def test_integer_enum_uses_the_same_encoding_as_string_labels():
    results = []
    for choices in ([1, 2, 3], ["1", "2", "3"]):
        m = Model()
        grid = m.enum_matrix("cell", 2, 2, choices=choices)
        m &= grid.row(0).all_different()
        m &= grid[0, 0] == choices[1]
        cnf = m.to_cnf()
        results.append((cnf.nv, cnf.clauses))
    assert results[0] == results[1]


@pytest.mark.parametrize("mode", ["table", "vector", "membership"])
def test_nullable_integer_enum_table_and_membership(mode):
    m = Model()
    xs = m.enum_vector("v", 2, choices=[1, 2], nullable=True)
    if mode == "table":
        condition = m.table(xs, allowed=[(1, None), (2, 1)])
    elif mode == "vector":
        condition = xs.is_in([(1, None), (2, 1)])
    else:
        condition = xs[0].is_in_or_none([1]) & (xs[1] != 1)
    m &= condition
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b in itertools.product([None, 1, 2], repeat=2):
            fixed = []
            for var, value in zip(xs, [a, b]):
                fixed += [
                    m._lit_to_dimacs(lit if choice == value else ~lit)
                    for choice, lit in var._choice_lits.items()
                ]
            expected = (
                ((a, b) in ((1, None), (2, 1)))
                if mode != "membership"
                else (a in (1, None) and b != 1)
            )
            assert solver.solve(assumptions=fixed) is expected


@pytest.mark.parametrize(
    "choices", [[1, "1"], [True, False], [None, 1], [1, 1], [1.5, 2.5]]
)
def test_enum_rejects_mixed_boolean_and_invalid_labels_before_reserving_name(choices):
    m = Model()
    before = m._next_id, len(m._hard)
    with pytest.raises((TypeError, ValueError)):
        m.enum("e", choices)
    assert (m._next_id, len(m._hard)) == before
    m.enum("e", [1, 2])


def test_integer_enum_label_types_are_not_coerced():
    m = Model()
    e = m.enum("e", [1, 2])
    for value in ("1", True):
        with pytest.raises(TypeError):
            _ = e == value
        with pytest.raises(TypeError):
            e.is_in([value])
        with pytest.raises(TypeError):
            m.table([e], allowed=[(value,)])
    with pytest.raises(TypeError):
        _ = e + 1


def test_sudoku_example_uses_and_decodes_integer_labels():
    example = (
        Path(__file__).resolve().parents[2] / "examples/model/09_sudoku9_single_clue.py"
    )
    namespace = runpy.run_path(str(example))
    result, grid = namespace["r"], namespace["grid"]
    assert result.ok
    values = [result[grid[row, :]] for row in range(9)]
    expected = set(range(1, 10))
    for row in values:
        assert set(row) == expected
        assert all(type(value) is int for value in row)
    for col in range(9):
        assert {values[row][col] for row in range(9)} == expected
    for br, bc in itertools.product((0, 3, 6), repeat=2):
        assert {
            values[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3)
        } == expected
    for r, row in enumerate(namespace["puzzle"]):
        for c, digit in enumerate(row):
            if digit != 0:
                assert values[r][c] == digit
