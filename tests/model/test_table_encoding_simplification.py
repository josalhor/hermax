import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


@pytest.mark.parametrize("mode,variables,clauses", [("post", 20, 241),
                                                 ("implies", 0, 20), ("iff", 20, 261)])
def test_set_tables_encode_membership_patterns_directly(mode, variables, clauses):
    m = Model()
    sets = m.int_set_vector("sets", 3, values=[1, 2, 3, 4])
    flag = m.bool("flag")
    rows = [tuple({v + 1 for v in range(4) if mask & (1 << (4 * i + v))}
                  for i in range(3)) for mask in range(20)]
    before = m._top_id(), len(m._hard)
    condition = sets.is_in(rows)
    assert (m._top_id(), len(m._hard)) == before
    m &= condition if mode == "post" else getattr(condition, mode)(flag)
    formula = m.to_cnf()
    assert m._top_id() - before[0] == variables
    assert len(formula.clauses) - before[1] == clauses


@pytest.mark.parametrize("mode", ["post", "only_if", "implies", "iff", "gated_iff"])
@pytest.mark.parametrize("shape", ["mixed", "repeated", "empty", "empty_universes"])
@pytest.mark.parametrize("rows_kind", ["valid", "impossible", "none"])
def test_set_table_simplifications_preserve_truth_tables(mode, shape, rows_kind):
    m = Model()
    if shape == "mixed":
        a = m.int_set("a", values=[1])
        b = m.int_set("b", values=[1, 2])
        objects = [a, b]
        rows = [({1}, {2}), (set(), {1, 2})]
    elif shape == "repeated":
        a = m.int_set("a", values=[1, 2])
        objects = [a, a]
        rows = [({1}, {1}), ({1}, {2})]
    elif shape == "empty":
        objects, rows = [], [()]
    else:
        objects = [m.int_set("a", values=[]), m.int_set("b", values=[])]
        rows = [(set(), set())]
    if rows_kind == "impossible":
        rows = [tuple({99} for _ in objects)] if objects else []
    elif rows_kind == "none":
        rows = []
    elif rows:
        rows = rows + [rows[0]]
        if objects:
            rows += [tuple({99} for _ in objects)]
    # Empty typed vectors are a supported constructor result.
    vector = m.vector(objects) if objects else m.int_set_vector("empty", 0, values=[])
    flag, gate = m.bool("flag"), m.bool("gate")
    condition = vector.is_in(rows)
    if mode == "gated_iff":
        condition = condition.only_if(gate)
    m &= condition if mode == "post" else getattr(condition, "iff" if mode == "gated_iff" else mode)(flag)
    literals = {lit.id: lit for obj in objects for lit in obj._member_lits.values()}
    literals = list(literals.values()) + [flag, gate]
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for states in itertools.product([False, True], repeat=len(literals)):
            values = dict(zip((lit.id for lit in literals), states))
            actual_row = tuple({v for v, lit in obj._member_lits.items() if values[lit.id]}
                               for obj in objects)
            expected = actual_row in rows
            f, g = states[-2:]
            if mode == "only_if":
                expected = not f or expected
            elif mode == "implies":
                expected = not expected or f
            elif mode == "gated_iff":
                expected = not g or expected
            if mode in {"iff", "gated_iff"}:
                expected = f == expected
            fixed = [m._lit_to_dimacs(lit if on else ~lit) for lit, on in zip(literals, states)]
            assert solver.solve(assumptions=fixed) is expected, (actual_row, f, g)


def test_set_tables_snapshot_the_rows_before_later_mutation():
    m = Model()
    sets = m.int_set_vector("sets", 1, values=[1, 2])
    value = {1}
    rows = [(value,)]
    condition = sets.is_in(iter(rows))
    value.add(2)
    rows.clear()
    m &= condition
    result = m.solve()
    assert result.ok and result[sets] == [{1}]


def test_binary_tables_omit_support_clauses_subsumed_by_allowed_values():
    m = Model()
    a, b = m.enum("a", list(range(100))), m.enum("b", list(range(100)))
    baseline = m.to_cnf()
    top = m._top_id()
    m &= m.table([a, b], allowed=itertools.product(range(100), repeat=2))
    clauses = m.to_cnf().clauses[len(baseline.clauses):]
    assert m._top_id() == top
    assert len(clauses) == 2
    assert sum(map(len, clauses)) == 200


def test_binary_tables_only_remove_supports_that_cover_every_partner():
    m = Model()
    a, b = m.int("a", 0, 2), m.int("b", 0, 2)
    rows = [(0, 0), (0, 1), (0, 2), (1, 0), (2, 0)]
    condition = m.table([a, b], allowed=rows)
    assert len(condition) == 6
    m &= condition
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for left, right in itertools.product(range(3), repeat=2):
            fixed = [m._lit_to_dimacs(lit) for var, val in [(a, left), (b, right)]
                     for lit in var._exact_value_atoms(val)]
            assert solver.solve(assumptions=fixed) is ((left, right) in rows)
