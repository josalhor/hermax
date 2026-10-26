from typing import TYPE_CHECKING

from .expressions import (
    Literal,
    Term,
    PBExpr,
    PBConstraint,
    Clause,
    ClauseGroup,
    _LazyIntExpr,
    FLOAT_ZERO_TOL,
)
from .variables import IntVar
from ._integer_objective import lower_integer_objective

if TYPE_CHECKING:
    from .core import Model


def validate_numeric_objective(model: "Model", expression) -> None:
    if not isinstance(expression, (Literal, Term, PBExpr, IntVar, _LazyIntExpr, int)):
        raise TypeError(
            "Objective terms must be numeric expressions; reify Boolean constraints with iff() and minimize the resulting literal."
        )
    owner = (
        expression.literal._model
        if isinstance(expression, Term)
        else getattr(expression, "_model", None)
    )
    if owner is not None and owner is not model:
        raise ValueError("Variables belong to different models.")


def validate_soft_constraint(model: "Model", constraint) -> None:
    if not isinstance(constraint, (Literal, Clause, ClauseGroup, PBConstraint, bool)):
        raise TypeError(
            "Soft preferences require a Boolean constraint; use obj.add(expression, weight=...) for numeric costs."
        )
    owner = getattr(constraint, "_model", None)
    if owner is not None and owner is not model:
        raise ValueError("Variables belong to different models.")


def prepare_objective(model: "Model", constraint, *, lower=True) -> PBExpr:
    validate_numeric_objective(model, constraint)
    if isinstance(constraint, bool):
        constraint = int(constraint)
    try:
        expr = PBExpr.from_item(constraint)
    except TypeError as exc:
        raise TypeError(
            "Objective terms must be numeric expressions; reify Boolean constraints with iff() and minimize the resulting literal."
        ) from exc
    if expr._model is not None and expr._model is not model:
        raise ValueError("Variables belong to different models.")
    if lower:
        expr = lower_integer_objective(expr, model)
    return PBExpr(
        model, list(expr.terms), expr.constant, int_terms=list(expr.int_terms)
    )


def normalize_objective(model: "Model", constraint, *, weight):
    return normalize_prepared_objective(
        model, prepare_objective(model, constraint), weight=weight
    )


def normalize_prepared_objective(model: "Model", expr: PBExpr, *, weight):
    lit_weights: dict[int, int] = {}
    offset_raw: int | float = weight * int(expr.constant)
    for t in expr.terms:
        coeff_raw = t.coefficient
        coeff_abs: int | float
        if isinstance(coeff_raw, float):
            if abs(coeff_raw) <= FLOAT_ZERO_TOL:
                continue
            coeff_abs = abs(coeff_raw)
        else:
            if coeff_raw == 0:
                continue
            coeff_abs = abs(int(coeff_raw))

        if coeff_raw > 0:
            lit = ~t.literal
            term_raw: int | float = (
                float(weight) * float(coeff_abs)
                if isinstance(coeff_abs, float)
                else weight * int(coeff_abs)
            )
        else:
            lit = t.literal
            term_raw = (
                float(weight) * float(coeff_abs)
                if isinstance(coeff_abs, float)
                else weight * int(coeff_abs)
            )
            offset_raw -= term_raw
        w, _rw = model._coerce_soft_weight(term_raw, allow_zero=False)
        dim = model._lit_to_dimacs(lit)
        lit_weights[dim] = lit_weights.get(dim, 0) + int(w)
    if float(offset_raw) < 0 and not bool(model._allow_negative_objective_offsets):
        raise ValueError(
            "Negative objective offsets are not supported by current model policy."
        )

    # Route positive constants to a native always-violated soft unit on
    # __false so solver-reported cost includes the offset directly.
    offset = 0
    if float(offset_raw) > FLOAT_ZERO_TOL:
        pos_w = int(offset_raw) if isinstance(offset_raw, int) else float(offset_raw)
        pos_off, _ = model._coerce_soft_weight(pos_w, allow_zero=False)
        false_lit = model._get_bool_constant_literal(False)
        dim_false = model._lit_to_dimacs(false_lit)
        lit_weights[dim_false] = lit_weights.get(dim_false, 0) + int(pos_off)
    elif float(offset_raw) < -FLOAT_ZERO_TOL:
        neg_abs = -offset_raw
        neg_w = int(neg_abs) if isinstance(neg_abs, int) else float(neg_abs)
        neg_off, _ = model._coerce_soft_weight(neg_w, allow_zero=False)
        offset = -int(neg_off)

    return lit_weights, int(offset)


class ObjectiveTerm:
    """One numeric objective contribution with an updateable weight."""

    __slots__ = (
        "_objective",
        "_generation",
        "_expression",
        "_weight",
        "_weights",
        "_offset",
        "_tier",
    )

    def __init__(self, objective, expression, weight, weights, offset, *, tier=None):
        self._objective = objective
        self._generation = objective._generation
        self._expression = expression
        self._weight = weight
        self._weights = weights
        self._offset = offset
        self._tier = tier

    def _check_active(self):
        if self._generation != self._objective._generation:
            raise ValueError("This objective term was cleared or replaced.")

    @property
    def weight(self):
        """The non-negative multiplier of this term's fixed expression."""
        self._check_active()
        return self._weight
