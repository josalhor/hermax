"""
HERMAX MODEL SEMANTICS (ROUND 2)
Focused tests to pin down decisions that were underspecified or contradicted in
earlier drafts (`design.md`, `test1.py`).

This file is intentionally opinionated: it captures the current intended API
surface as discussed with the project author.
"""

import pytest

from hermax.model import Model, Literal, ClauseGroup, PBExpr, PBConstraint


# =====================================================================
# SECTION I: COMPARATORS FINALIZE TO LAZY PBConstraint DESCRIPTORS
# =====================================================================


def test_pb_comparator_finalizes_to_pbconstraint_descriptor():
    model = Model()
    a = model.bool("a")
    b = model.bool("b")

    expr = a + b
    assert isinstance(expr, PBExpr)  # expression stage still exists

    # Finalization stage: comparisons produce addable PBConstraint descriptors.
    for out in [expr <= 1, expr < 2, expr >= 1, expr > 0, expr == 1]:
        assert isinstance(out, PBConstraint)
        assert isinstance(out.clauses(), ClauseGroup)


def test_pbexpr_vs_pbexpr_comparisons_are_supported_and_lazy():
    model = Model()
    a = model.bool("a")
    b = model.bool("b")
    c = model.bool("c")
    d = model.bool("d")

    lhs = 2 * a + b
    rhs = c + d

    # RHS shifting / normalization is implementation detail.
    # Public semantics: valid and returns PBConstraint descriptor.
    for out in [lhs <= rhs, lhs >= rhs, lhs == rhs]:
        assert isinstance(out, PBConstraint)
        assert isinstance(out.clauses(), ClauseGroup)


def test_pbexpr_comparators_remain_cross_model_safe():
    model_a = Model()
    model_b = Model()

    x = model_a.bool("x")
    y = model_b.bool("y")

    with pytest.raises(ValueError, match="different models"):
        _ = (x + 1 * x) <= (y + 1 * y)


def test_pbexpr_offsets_are_allowed_and_normalize_semantically():
    model = Model()
    a = model.bool("a")
    b = model.bool("b")

    # Offsets are now supported as part of the public algebraic PBExpr DSL.
    expr = a + b + 0 - 0
    assert isinstance(expr, PBExpr)

    expr2 = a + b + 1
    expr3 = 1 + a + b
    assert isinstance(expr2, PBExpr)
    assert isinstance(expr3, PBExpr)

    # Equivalent forms should both encode the same semantics.
    m1 = Model()
    x1 = m1.bool("x1")
    y1 = m1.bool("y1")
    m1 &= (x1 + y1 + 2 <= 3)
    r1 = m1.solve()
    assert r1.ok
    # x1+y1 <= 1
    assert int(r1[x1]) + int(r1[y1]) <= 1

    m2 = Model()
    x2 = m2.bool("x2")
    y2 = m2.bool("y2")
    m2 &= (x2 + y2 <= 1)
    r2 = m2.solve()
    assert r2.ok
    assert int(r2[x2]) + int(r2[y2]) <= 1


# =====================================================================
# SECTION II: CLAUSEGROUP IS A REAL IMMUTABLE TYPE (NOT JUST A LIST)
# =====================================================================


def test_clausegroup_is_its_own_type_and_exposes_clauses():
    model = Model()
    a = model.bool("a")
    b = model.bool("b")

    pb = (a + b <= 1)
    assert isinstance(pb, PBConstraint)
    cg = pb.clauses()
    assert isinstance(cg, ClauseGroup)
    assert hasattr(cg, "clauses")
    assert isinstance(cg.clauses, list)


def test_clausegroup_is_immutable_surface():
    model = Model()
    a = model.bool("a")
    b = model.bool("b")
    c = model.bool("c")

    cg = (a + b <= 1).clauses()

    # This should stay a hard failure until/if mutable ops are intentionally added.
    with pytest.raises((TypeError, AttributeError)):
        cg |= c


def test_pbconstraint_only_if_and_implies_literal_are_supported_and_chainable():
    model = Model()
    a = model.bool("a")
    b = model.bool("b")
    c = model.bool("c")
    d = model.bool("d")

    pb = (a + b <= 1)
    assert isinstance(pb.only_if(c), PBConstraint)
    out = pb.implies(d)
    assert isinstance(out, (PBConstraint, ClauseGroup))


# =====================================================================
# SECTION III: INT DOMAIN SEMANTICS (EXCLUSIVE UPPER BOUND)
# =====================================================================


def test_int_domain_is_lb_inclusive_ub_exclusive():
    model = Model()
    speed = model.int("speed", lb=0, ub=4)  # intended domain: {0,1,2,3}

    # Boundary comparisons should map cleanly into literals.
    assert isinstance(speed >= 0, Literal)
    assert isinstance(speed < 4, Literal)

    # "Human" inclusive forms at the top boundary should also be supported.
    assert isinstance(speed <= 3, Literal)


def test_int_unary_width_matches_exclusive_upper_bound_span():
    model = Model()
    speed = model.int("speed", lb=0, ub=4)  # 4 representable values under [lb, ub)
    a = model.bool("a")

    # Current intended unary/ladder interpretation:
    # number of generated threshold literals/terms == (ub - lb)
    expr = a + speed
    assert isinstance(expr, PBExpr)
    assert len(expr.terms) == 1 + (4 - 0)

    scaled = 3 * speed
    assert isinstance(scaled, PBExpr)
    assert len(scaled.terms) == (4 - 0)


def test_int_rejects_empty_or_inverted_domain():
    model = Model()

    with pytest.raises(ValueError):
        model.int("x", lb=5, ub=5)

    with pytest.raises(ValueError):
        model.int("y", lb=6, ub=5)


def test_int_out_of_domain_exact_equality_is_rejected():
    model = Model()
    speed = model.int("speed", lb=0, ub=4)  # {0,1,2,3}

    # Chosen semantics for now (explicit and easy to reason about):
    # exact equality outside the declared domain is an error rather than silently
    # generating tautology/contradiction encodings.
    with pytest.raises(ValueError):
        _ = (speed == 4)

    with pytest.raises(ValueError):
        _ = (speed == -1)


# =====================================================================
# SECTION IV: DEFERRED/TODO AREAS (ENCODING SHAPE NOT FIXED YET)
# =====================================================================


def test_enum_equality_between_two_enums_is_clausegroup_todo_shape():
    model = Model()
    color1 = model.enum("color1", choices=["red", "green", "blue"])
    color2 = model.enum("color2", choices=["red", "green", "blue"])

    eq = (color1 == color2)
    assert isinstance(eq, ClauseGroup)
    # Exact clause shape intentionally unspecified for now.
