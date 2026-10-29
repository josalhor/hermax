import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model


def _identity(model, source, operation, name):
    if operation in {"floor_div", "scale"}:
        return getattr(model, operation)(source, 1, name=name)
    return getattr(model, operation)([source, source, source], name=name)


@pytest.mark.parametrize("operation", ["floor_div", "scale", "max", "min"])
@pytest.mark.parametrize("name", [None, "result"])
@pytest.mark.parametrize("source_kind", ["integer", "offset", "boolean", "constant"])
def test_identity_operations_share_encoding_and_preserve_values(operation, name, source_kind):
    m = Model()
    if source_kind == "integer":
        source = m.int("x", -3, 5)
    elif source_kind == "offset":
        source = m.interval("job", start=-3, duration=2, end=7).end
    elif source_kind == "boolean":
        source = m.as_int(~m.bool("flag"))
    else:
        source = m.int("x", -3, -3)
    before = m._top_id(), len(m.to_cnf().clauses)
    result = _identity(m, source, operation, name)
    assert (m._top_id(), len(m.to_cnf().clauses)) == before
    assert result._threshold_lits is source._threshold_lits
    if name is None:
        assert result is source
    else:
        assert result is not source and result.name == name
        with pytest.raises(ValueError, match="already registered"):
            m.bool(name)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for value, candidate in itertools.product(
            range(source.lb, source.ub + 1), repeat=2
        ):
            fixed = [
                m._lit_to_dimacs(lit)
                for obj, val in [(source, value), (result, candidate)]
                for lit in obj._exact_value_atoms(val)
            ]
            assert solver.solve(assumptions=fixed) is (value == candidate)
    m &= source == source.ub
    saved = m.solve()
    assert saved.ok and saved[result] == saved[source] == source.ub


@pytest.mark.parametrize("operation", ["max", "min"])
def test_repeated_extreme_inputs_do_not_duplicate_wiring(operation):
    def build(repeated):
        m = Model()
        x, y = m.int("x", -2, 4), m.int("y", 0, 5)
        items = [x, y, x, y, x] if repeated else [x, y]
        out = getattr(m, operation)(items)
        formula = m.to_cnf()
        with Solver(bootstrap_with=formula.clauses) as solver:
            for a, b, c in itertools.product(range(-2, 5), range(6), range(out.lb, out.ub + 1)):
                fixed = [
                    m._lit_to_dimacs(lit)
                    for var, value in [(x, a), (y, b), (out, c)]
                    for lit in var._exact_value_atoms(value)
                ]
                expected = max(a, b) if operation == "max" else min(a, b)
                assert solver.solve(assumptions=fixed) is (c == expected)
        return formula.nv, len(formula.clauses)
    assert build(True) == build(False)


@pytest.mark.parametrize("operation", ["floor_div", "scale", "max", "min"])
def test_named_identity_operations_share_binary_view(operation):
    m = Model()
    source = m.int("x", 0, 32)
    bits = source._get_binary_view()
    result = _identity(m, source, operation, "result")
    assert result._get_binary_view() is bits
    m &= result >= 20
    m.obj = result
    saved = m.solve()
    assert saved.ok and saved[source] == saved[result] == saved.cost == 20


@pytest.mark.parametrize("operation", ["floor_div", "scale", "max", "min"])
@pytest.mark.parametrize("name", [None, "result"])
def test_identity_operations_reject_inputs_from_another_model(operation, name):
    m = Model()
    foreign = Model().int("x", 0, 8)
    with pytest.raises(ValueError, match="different models"):
        _identity(m, foreign, operation, name)


@pytest.mark.parametrize("operation", ["floor_div", "scale", "max", "min"])
def test_named_identity_operations_reject_duplicate_names(operation):
    m = Model()
    source = m.int("x", 0, 8)
    m.bool("result")
    before = m._top_id(), len(m._hard)
    with pytest.raises(ValueError, match="already registered"):
        _identity(m, source, operation, "result")
    assert (m._top_id(), len(m._hard)) == before
