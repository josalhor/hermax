import pytest

from hermax.model import Clause, ClauseGroup, Model


@pytest.mark.parametrize("choices", [3, 10, 100, 500, 1000])
@pytest.mark.parametrize("nullable", [False, True])
def test_enum_domain_definition_is_posted_once(choices, nullable):
    m = Model()
    value = m.enum("value", choices=list(range(choices)), nullable=nullable)
    definition = next(iter(m._pending_literal_defs.values()))
    expected = tuple(definition.iter_dimacs())
    formula = m.to_cnf()
    assert tuple(map(tuple, formula.clauses)) == expected
    assert m.to_cnf().clauses == formula.clauses
    m &= value == choices - 1
    result = m.solve()
    assert result.ok and result[value] == choices - 1
    m &= value != choices - 1
    assert not m.solve().ok


def test_posting_an_enum_choice_realizes_its_shared_domain_once():
    m = Model()
    value = m.enum("value", choices=list(range(500)))
    definition = next(iter(m._pending_literal_defs.values()))
    m &= value == 42
    assert len(m.to_cnf().clauses) == len(definition) + 1
    assert m.solve()[value] == 42


def test_shared_definitions_still_realize_external_dependencies():
    m = Model()
    x = m.int("x", 0, 4)
    dependency = x == 1
    a, b = m.bool("a"), m.bool("b")
    definition = ClauseGroup(m, [Clause(m, [~a, dependency]), Clause(m, [~b, a])])
    m._register_literal_definition(a, definition)
    m._register_literal_definition(b, definition)
    before = len(m._hard)
    m &= b
    m &= ~dependency
    assert len(m.to_cnf().clauses) - before == 7
    assert not m.solve().ok


def test_cyclic_shared_definitions_are_each_posted_once():
    m = Model()
    a, b, c = m.bool("a"), m.bool("b"), m.bool("c")
    shared = ClauseGroup(m, [Clause(m, [~a, c]), Clause(m, [~b, a])])
    dependent = ClauseGroup(m, [Clause(m, [~c, b])])
    m._register_literal_definition(a, shared)
    m._register_literal_definition(b, shared)
    m._register_literal_definition(c, dependent)
    assert len(m.to_cnf().clauses) == 3
    m &= a
    m &= ~b
    assert not m.solve().ok
