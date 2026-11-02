"""Disjoint-sum shortcuts must preserve immutable and explicit mutable arithmetic."""
import pytest

from hermax.model import Model, PBExpr, Term


def signature(expr):
    return [(t.literal.id, t.literal.polarity, t.coefficient) for t in expr.terms]


def test_growing_sum_does_not_rescan_its_prefix(monkeypatch):
    m = Model()
    literals = m.bool_vector('b', 256)
    original = PBExpr._terms_disjoint
    scanned = 0

    def check(left, right):
        nonlocal scanned
        scanned += len(left) + len(right)
        return original(left, right)

    monkeypatch.setattr(PBExpr, '_terms_disjoint', staticmethod(check))
    result = sum(literals)
    assert signature(result) == [(lit.id, True, 1) for lit in literals]
    assert scanned <= 2 * len(literals)


@pytest.mark.parametrize('inplace', ['add', 'sub'])
def test_explicit_mutation_updates_bound_before_reusing_a_literal(inplace):
    m = Model()
    a, b, c = m.bool_vector('b', 3)
    expr = a + b
    getattr(expr, inplace)(c, inplace=True)
    result = expr + c
    expected = [(a.id, True, 1), (b.id, True, 1)]
    if inplace == 'add':
        expected.append((c.id, True, 2))
    assert signature(result) == expected
    assert signature(expr) == [(a.id, True, 1), (b.id, True, 1), (c.id, True, 1 if inplace == 'add' else -1)]


def test_bulk_expressions_branching_and_cancellation_keep_their_meaning():
    m = Model()
    a, b, c, d = m.bool_vector('b', 4)
    expr = PBExpr(m, [Term(2, d), Term(3, a)], 7)
    snapshot = signature(expr)
    assert signature(expr + d) == [(d.id, True, 3), (a.id, True, 3)]
    assert signature(expr - 2*d) == [(a.id, True, 3)]
    assert signature(expr) == snapshot
    expr.sub(2*d, inplace=True)
    expr.add(c, inplace=True)
    assert signature(expr + c) == [(a.id, True, 3), (c.id, True, 2)]
    assert (expr + ~c).constant == 7
    assert signature(sum([b, a, b])) == [(b.id, True, 2), (a.id, True, 1)]
