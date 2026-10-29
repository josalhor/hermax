import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


def _membership(model, x, allowed, path):
    if path == "table":
        return model.table([x], allowed=((value,) for value in allowed))
    array = [int(value in allowed) for value in range(x.lb, x.ub + 1)]
    return (array @ x) == 1


@pytest.mark.parametrize("path", ["table", "lookup"])
@pytest.mark.parametrize("mode", ["post", "only_if", "implies", "iff", "gated_iff"])
@pytest.mark.parametrize("allowed", [(), (3,), (4, 5), (3, 5, 8), tuple(range(3, 9))])
def test_integer_membership_preserves_boolean_contexts(path, mode, allowed):
    model = Model()
    x = model.int("x", 3, 8)
    flag, gate = model.bool("flag"), model.bool("gate")
    before = model._top_id(), len(model._hard)
    condition = _membership(model, x, allowed, path)
    assert (model._top_id(), len(model._hard)) == before
    if mode == "implies" and path == "lookup":
        with pytest.raises(TypeError):
            condition.implies(flag)
        return
    if mode == "gated_iff":
        condition = condition.only_if(gate)
    model &= condition if mode == "post" else getattr(
        condition, "iff" if mode == "gated_iff" else mode
    )(flag)
    with Solver(bootstrap_with=model.to_cnf().clauses) as solver:
        for value, f, g in itertools.product(range(3, 9), [False, True], [False, True]):
            expected = value in allowed
            if mode == "only_if":
                expected = not f or expected
            elif mode == "implies":
                expected = not expected or f
            elif mode == "gated_iff":
                expected = not g or expected
            if mode in {"iff", "gated_iff"}:
                expected = f == expected
            atoms = [*x._exact_value_atoms(value), flag if f else ~flag, gate if g else ~gate]
            fixed = [model._lit_to_dimacs(atom) for atom in atoms]
            assert solver.solve(assumptions=fixed) is expected


@pytest.mark.parametrize("path", ["table", "lookup"])
def test_integer_membership_excludes_whole_gaps_without_helpers(path):
    model = Model()
    x = model.int("x", 0, 1000)
    before = model._top_id(), len(model._hard)
    model &= _membership(model, x, range(200, 801), path)
    formula = model.to_cnf()
    assert model._top_id() == before[0]
    assert len(formula.clauses) - before[1] == 2
