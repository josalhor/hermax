import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import ClauseGroup, Model


@pytest.mark.parametrize("compare", [operator.eq, operator.ne])
def test_enum_relation_reification_reuses_the_opposite_relation(compare):
    m = Model()
    left = m.enum("left", choices=list(range(100)))
    right = m.enum("right", choices=list(range(100)))
    flag = m.bool("flag")
    before = m._top_id(), len(m.to_cnf().clauses)
    m &= compare(left, right).iff(flag)
    formula = m.to_cnf()
    assert m._top_id() == before[0]
    assert len(formula.clauses) - before[1] == 300


@pytest.mark.parametrize("compare", [operator.eq, operator.ne])
@pytest.mark.parametrize("nullable_left,nullable_right", itertools.product([False, True], repeat=2))
@pytest.mark.parametrize("mode", ["post", "iff", "gated_iff", "choice_indicator"])
def test_enum_relation_truth_tables(compare, nullable_left, nullable_right, mode):
    m = Model()
    left = m.enum("left", choices=[1, 2, 3], nullable=nullable_left)
    right = m.enum("right", choices=[1, 2, 3], nullable=nullable_right)
    flag = left == 1 if mode == "choice_indicator" else m.bool("flag")
    gate = m.bool("gate")
    relation = compare(left, right)
    if mode == "gated_iff":
        relation = relation.only_if(gate)
    m &= relation if mode == "post" else relation.iff(flag)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, enabled, guarded in itertools.product(
            [1, 2, 3] + ([None] if nullable_left else []),
            [1, 2, 3] + ([None] if nullable_right else []), [False, True], [False, True]
        ):
            if mode == "choice_indicator" and enabled != (a == 1):
                continue
            fixed = [m._lit_to_dimacs(lit if choice == value else ~lit)
                     for obj, value in [(left, a), (right, b)]
                     for choice, lit in obj._choice_lits.items()]
            fixed += [m._lit_to_dimacs(flag if enabled else ~flag), gate.id if guarded else -gate.id]
            expected = compare(a, b)
            if mode == "gated_iff":
                expected = not guarded or expected
            if mode != "post":
                expected = enabled == expected
            assert solver.solve(assumptions=fixed) is expected, (a, b, enabled, guarded)


@pytest.mark.parametrize("nullable_left,nullable_right", itertools.product([False, True], repeat=2))
def test_enum_equality_propagates_at_least_as_strongly_as_generic_reification(nullable_left, nullable_right):
    solvers = []
    try:
        for generic in [True, False]:
            m = Model()
            left = m.enum("left", [1, 2, 3], nullable=nullable_left)
            right = m.enum("right", [1, 2, 3], nullable=nullable_right)
            flag = m.bool("flag")
            original_top = m._top_id()
            relation = left == right
            m &= ClauseGroup.iff(relation, flag) if generic else relation.iff(flag)
            solvers.append(Solver(bootstrap_with=m.to_cnf().clauses))
        for states in itertools.product([0, -1, 1], repeat=original_top):
            assumptions = [i * sign for i, sign in enumerate(states, 1) if sign]
            old_ok, old_propagated = solvers[0].propagate(assumptions=assumptions)
            new_ok, new_propagated = solvers[1].propagate(assumptions=assumptions)
            if not old_ok:
                assert not new_ok
            elif new_ok:
                old_values = {lit for lit in old_propagated if abs(lit) <= original_top}
                new_values = {lit for lit in new_propagated if abs(lit) <= original_top}
                assert old_values <= new_values
    finally:
        for solver in solvers:
            solver.delete()


@pytest.mark.parametrize("compare", [operator.eq, operator.ne])
def test_enum_relation_equivalences_can_be_reified_again(compare):
    m = Model()
    left = m.enum("left", [1, 2], nullable=True)
    right = m.enum("right", [1, 2], nullable=True)
    inner, outer = m.bool("inner"), m.bool("outer")
    m &= compare(left, right).iff(inner).iff(outer)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for a, b, i, o in itertools.product([1, 2, None], [1, 2, None], [False, True], [False, True]):
            fixed = [m._lit_to_dimacs(lit if label == value else ~lit)
                     for obj, value in [(left, a), (right, b)] for label, lit in obj._choice_lits.items()]
            fixed += [inner.id if i else -inner.id, outer.id if o else -outer.id]
            assert solver.solve(assumptions=fixed) is (o == (i == compare(a, b)))


@pytest.mark.parametrize("compare", [operator.eq, operator.ne])
@pytest.mark.parametrize("nullable", [False, True])
def test_enum_self_comparisons_reify_as_constants(compare, nullable):
    m = Model()
    value = m.enum("value", choices=list(range(10)), nullable=nullable)
    flag = m.bool("flag")
    before = m._top_id(), len(m.to_cnf().clauses)
    m &= compare(value, value).iff(flag)
    assert m._top_id() == before[0]
    assert len(m.to_cnf().clauses) - before[1] == 1
    assert m.solve()[flag] is compare(0, 0)


@pytest.mark.parametrize("compare", [operator.eq, operator.ne])
def test_enum_relations_preserve_explicit_reification_and_clause_group_operators(compare):
    m = Model()
    a, b = m.enum("a", [1, 2]), m.enum("b", [1, 2])
    flag = m.bool("flag")
    relation = compare(a, b)
    before = m._top_id(), len(m._hard)
    assert isinstance(relation, ClauseGroup)
    for operation in [lambda: relation | flag, lambda: flag | relation,
                      lambda: flag == relation, lambda: relation.implies(flag)]:
        with pytest.raises(TypeError):
            operation()
    assert (m._top_id(), len(m._hard)) == before
    combined = relation & flag
    assert type(combined) is ClauseGroup


@pytest.mark.parametrize("compare", [operator.eq, operator.ne])
@pytest.mark.parametrize("extend_first", [False, True])
def test_extended_enum_relations_reify_the_modified_clauses(compare, extend_first):
    m = Model()
    a, b = m.enum("a", [1, 2]), m.enum("b", [1, 2])
    flag, extra = m.bool("flag"), m.bool("extra")
    relation = compare(a, b)
    if extend_first:
        relation.extend(extra, inplace=True)
    reified = relation.iff(flag)
    if not extend_first:
        relation.extend(extra, inplace=True)
    m &= reified
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for av, bv, fv, ev in itertools.product([1, 2], [1, 2], [False, True], [False, True]):
            fixed = [m._lit_to_dimacs(lit if label == value else ~lit)
                     for obj, value in [(a, av), (b, bv)] for label, lit in obj._choice_lits.items()]
            fixed += [flag.id if fv else -flag.id, extra.id if ev else -extra.id]
            assert solver.solve(assumptions=fixed) is (fv == (compare(av, bv) and ev))
