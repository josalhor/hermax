from __future__ import annotations

import pytest

from hermax.model import Clause, ClauseGroup, Model, Term


def test_literal_or_supports_clause_rhs():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    out = a | Clause(m, [b, c])
    assert isinstance(out, Clause)
    assert [l.id if l.polarity else -l.id for l in out.literals] == [b.id, c.id, a.id]


def test_literal_and_supports_clause_and_clausegroup_rhs():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    d = m.bool("d")

    g1 = a & Clause(m, [b, c])
    assert isinstance(g1, ClauseGroup)
    assert len(g1.clauses) == 2

    g2 = a & ClauseGroup(m, [Clause(m, [d])])
    assert isinstance(g2, ClauseGroup)
    assert len(g2.clauses) == 2


def test_literal_eq_ne_general_behavior():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    eq = (a == b)
    assert isinstance(eq, ClauseGroup)
    assert len(eq.clauses) == 2

    assert (a == "x") is False
    assert (a != "x") is True
    assert (a != b) is True
    assert (a != a) is False


def test_literal_implies_supports_all_targets_and_rejects_unknown():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    x = m.int("x", 0, 3)

    out_lit = a.implies(b)
    assert isinstance(out_lit, Clause)

    out_clause = a.implies(Clause(m, [~b]))
    assert isinstance(out_clause, Clause)

    out_group = a.implies(ClauseGroup(m, [Clause(m, [b]), Clause(m, [~b])]))
    assert isinstance(out_group, ClauseGroup)
    assert len(out_group.clauses) == 2

    out_pb = a.implies(x <= 1)
    assert isinstance(out_pb, (Clause, ClauseGroup))

    with pytest.raises(TypeError, match="Unsupported implication target"):
        a.implies(object())


def test_literal_and_term_repr_and_validation_errors():
    m = Model()
    a = m.bool("a")
    assert repr(a) == "a"
    assert repr(~a) == "~a"

    with pytest.raises(TypeError, match="coefficient"):
        Term(True, a)
    with pytest.raises(TypeError, match="literal must be Literal"):
        Term(1, object())


def test_term_arithmetic_paths_and_nonlinear_errors():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    t = 2 * a

    # Immutable operator behavior via iadd/isub and radd/rsub.
    e1 = t + b
    e2 = t - b
    e3 = 3 + t
    e4 = 3 - t
    assert e1 is not None and e2 is not None and e3 is not None and e4 is not None

    with pytest.raises(TypeError, match="Non-linear arithmetic"):
        _ = t * b
    with pytest.raises(TypeError, match="Non-linear arithmetic"):
        _ = b * t


def test_lazy_expr_mul_scale_floordiv_and_eq_paths():
    m = Model()
    x = m.int("x", 0, 6)
    y = m.int("y", 0, 6)
    d = x // 2

    # __mul__/__rmul__ for lazy expr.
    pb = 3 * d
    assert pb is not None
    with pytest.raises(TypeError, match="Only integer scaling"):
        _ = 1.5 * d
    with pytest.raises(TypeError, match="Non-linear arithmetic"):
        _ = d * y

    # lazy scale validation.
    with pytest.raises(ValueError, match="strictly positive"):
        d.scale(True)
    with pytest.raises(TypeError, match="integer"):
        d.scale(2.5)
    with pytest.raises(ValueError, match="strictly positive"):
        d.scale(0)

    # lazy floordiv nonlinear guard.
    with pytest.raises(TypeError, match="Non-linear arithmetic"):
        _ = d // y

    # __eq__ fallback on unsupported type.
    assert (d == object()) is False
