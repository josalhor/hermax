"""Boolean composition preserves semantics without implicit truth variables."""

import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


def _setup():
    m = Model()
    a, b, c, flag = (m.bool(name) for name in ("a", "b", "c", "flag"))
    x, y = m.int("x", 0, 1), m.int("y", 0, 1)
    formulas = {
        "pb": 2 * a + 3 * b + c <= 3,
        "other_pb": a + 2 * b + 3 * c >= 2,
        "gated_pb": (2 * a + 3 * b + c <= 3).only_if(c),
        "literal": a,
        "clause": a | b,
        "group": (a | b) & (~b | c),
        "relation": x != y,
        "true": x != 7,
        "false": x == 7,
    }
    return m, (a, b, c, flag, x >= 1, y >= 1), formulas


def _truth(kind, a, b, c, x, y):
    return {
        "pb": 2 * a + 3 * b + c <= 3,
        "other_pb": a + 2 * b + 3 * c >= 2,
        "gated_pb": not c or 2 * a + 3 * b + c <= 3,
        "literal": a,
        "clause": a or b,
        "group": (a or b) and (not b or c),
        "relation": x != y,
        "true": True,
        "false": False,
    }[kind]


def _check(m, variables, formula, predicate, mode):
    flag = variables[3]
    if mode == "iff":
        formula = formula.iff(flag)
    elif mode == "only_if":
        formula = formula.only_if(flag)
    m &= formula
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product((False, True), repeat=6):
            a, b, c, f, x, y = values
            truth = predicate(a, b, c, x, y)
            expected = (
                truth == f
                if mode == "iff"
                else (not f or truth)
                if mode == "only_if"
                else truth
            )
            fixed = [
                m._lit_to_dimacs(v if value else ~v)
                for v, value in zip(variables, values)
            ]
            assert solver.solve(assumptions=fixed) is bool(expected), values


@pytest.mark.parametrize(
    "left,right",
    [
        ("pb", "other_pb"),
        ("pb", "literal"),
        ("literal", "pb"),
        ("pb", "clause"),
        ("clause", "pb"),
        ("pb", "group"),
        ("group", "pb"),
        ("pb", "relation"),
        ("relation", "pb"),
        ("pb", "true"),
        ("false", "pb"),
        ("gated_pb", "other_pb"),
    ],
)
def test_pb_conjunction_requires_separate_posting(left, right):
    m, variables, formulas = _setup()
    top, hard = m._next_id, len(m._hard)
    with pytest.raises(TypeError):
        _ = formulas[left] & formulas[right]
    assert (m._next_id, len(m._hard)) == (top, hard)


@pytest.mark.parametrize(
    "kind", ["pb", "gated_pb"]
)
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("mode", ["post", "only_if", "iff"])
def test_disjunction_with_a_literal_truth_table(kind, reverse, mode):
    m, variables, formulas = _setup()
    literal = variables[0]
    top, hard = m._next_id, len(m._hard)
    formula = literal | formulas[kind] if reverse else formulas[kind] | literal
    assert m._next_id == top and len(m._hard) == hard
    _check(
        m, variables, formula, lambda *values: _truth(kind, *values) or values[0], mode
    )


def test_committed_integer_composition_reification_is_preserved():
    m = Model()
    x, y, z = (m.int(name, 0, 2) for name in ("x", "y", "z"))
    flag = m.bool()
    m &= ((x <= y) & (y <= z)).iff(flag)
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for xv, yv, zv, fv in itertools.product(range(3), range(3), range(3), (False, True)):
            fixed = [
                m._lit_to_dimacs(lit)
                for var, value in ((x, xv), (y, yv), (z, zv))
                for lit in var._exact_value_atoms(value)
            ]
            fixed.append(m._lit_to_dimacs(flag if fv else ~flag))
            assert solver.solve(assumptions=fixed) is (fv == (xv <= yv <= zv))


@pytest.mark.parametrize(
    "kind", ["pb", "gated_pb"]
)
def test_or_literal_has_the_same_size_as_explicit_gating(kind):
    results = []
    for combined in (False, True):
        m, variables, formulas = _setup()
        formula, literal = formulas[kind], variables[0]
        m &= formula | literal if combined else formula.only_if(~literal)
        cnf = m.to_cnf()
        results.append((cnf.nv, len(cnf.clauses)))
    assert results[0] == results[1]


def test_pb_disjunction_rejects_foreign_literal_without_mutation():
    m, variables, formulas = _setup()
    foreign = Model().bool("foreign")
    before = m._next_id, len(m._hard)
    with pytest.raises(ValueError, match="different models"):
        _ = formulas["pb"] | foreign
    assert (m._next_id, len(m._hard)) == before


@pytest.mark.parametrize("kind", ["pb", "group"])
def test_general_disjunction_remains_explicit(kind):
    _, _, formulas = _setup()
    with pytest.raises(TypeError):
        _ = formulas[kind] | formulas["other_pb"]




@pytest.mark.parametrize("kind", ["group", "relation", "true", "false"])
@pytest.mark.parametrize("reverse", [False, True])
def test_clausegroup_disjunction_is_rejected_without_compilation(kind, reverse):
    m, variables, formulas = _setup()
    before = m._next_id, len(m._hard)
    with pytest.raises(TypeError):
        if reverse:
            _ = variables[0] | formulas[kind]
        else:
            _ = formulas[kind] | variables[0]
    assert (m._next_id, len(m._hard)) == before
