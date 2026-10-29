import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


@pytest.mark.parametrize("mode", ["post", "only_if", "iff", "zero", "one", "negated"])
def test_bool_element_truth_table_without_implicit_variables(mode):
    m = Model()
    flags = m.bool_vector("flags", 4)
    index = m.int("index", 1, 3)
    indicator = m.bool("indicator")
    top, hard = m._next_id, len(m._hard)
    selected = flags[index]
    assert (m._next_id, len(m._hard)) == (top, hard)
    if mode == "negated":
        formula = ~selected
    elif mode == "iff":
        formula = selected.iff(indicator)
    elif mode == "only_if":
        formula = selected.only_if(indicator)
    elif mode in ("zero", "one"):
        formula = selected == int(mode == "one")
    else:
        formula = selected
    m &= formula
    cnf = m.to_cnf()
    assert m._next_id == top
    if mode == "iff":
        assert len(cnf.clauses) - hard == 2 * (index.ub - index.lb + 1)
    with Solver(name="g4", bootstrap_with=cnf.clauses) as solver:
        for values, iv, bv in itertools.product(
            itertools.product((False, True), repeat=4), range(1, 4), (False, True)
        ):
            expected = values[iv]
            if mode == "iff":
                expected = expected == bv
            elif mode == "only_if":
                expected = not bv or expected
            elif mode in ("zero", "negated"):
                expected = not expected
            fixed = [
                m._lit_to_dimacs(lit if value else ~lit)
                for lit, value in zip(flags, values)
            ]
            fixed += [m._lit_to_dimacs(v) for v in index._exact_value_atoms(iv)]
            fixed.append(m._lit_to_dimacs(indicator if bv else ~indicator))
            assert solver.solve(assumptions=fixed) is expected


def test_bool_element_decodes_without_materializing_a_result():
    m = Model()
    flags = m.bool_vector("b", 3)
    index = m.int("i", 0, 2)
    m &= index == 1
    m &= flags[1]
    result = m.solve()
    top = m._next_id
    assert result[flags[index]] is True
    assert result[~flags[index]] is False
    assert m._next_id == top


@pytest.mark.parametrize("kind", ["negative", "large", "foreign"])
def test_bool_element_rejects_invalid_index_without_allocations(kind):
    m = Model()
    flags = m.bool_vector("b", 2)
    index = (
        Model().int("i", 0, 1)
        if kind == "foreign"
        else m.int("i", -1, 1)
        if kind == "negative"
        else m.int("i", 0, 2)
    )
    before = m._next_id, len(m._hard)
    with pytest.raises(ValueError):
        _ = flags[index]
    assert (m._next_id, len(m._hard)) == before


def test_bool_element_does_not_enable_implicit_equivalence():
    m = Model()
    flags = m.bool_vector("b", 2)
    index = m.int("i", 0, 1)
    flag = m.bool()
    with pytest.raises(TypeError):
        _ = flags[index] == flag
    with pytest.raises(TypeError):
        _ = flag == flags[index]
    with pytest.raises(TypeError):
        _ = flags[index] == True


def test_boolean_lookups_share_immutable_vector_storage():
    m = Model()
    flags = m.bool_vector("flags", 1000)
    index = m.int("i", 0, 1)
    lookups = [flags[index] for _ in range(100)]
    assert isinstance(flags._items, tuple)
    assert all(lookup._items is flags._items for lookup in lookups)
    assert (~lookups[0])._items is flags._items


@pytest.mark.parametrize("kind", ["bool", "int", "enum", "set"])
def test_vector_storage_change_preserves_public_slices(kind):
    m = Model()
    vector = {
        "bool": lambda: m.bool_vector("v", 3),
        "int": lambda: m.int_vector("v", 3, 0, 2),
        "enum": lambda: m.enum_vector("v", 3, [1, 2]),
        "set": lambda: m.int_set_vector("v", 3, values=[1, 2]),
    }[kind]()
    sliced = vector[1:]
    assert isinstance(sliced, list)
    assert sliced[0] is vector[1]
    assert vector[-1] is list(vector)[-1]
    sliced.clear()
    assert len(vector) == 3
