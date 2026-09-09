"""Canonicalization primitives shared by PB modelling and encoding layers.

The structured PB encoders require strictly positive coefficients.  This
module owns the semantic rewrite that makes a signed Boolean sum canonical:
``-w * literal == w * ~literal - w``.
"""

from dataclasses import dataclass
from typing import Callable, Hashable, Iterable, TypeVar


_Literal = TypeVar("_Literal")


@dataclass(frozen=True)
class NormalizedPBTerms:
    """A positive-coefficient Boolean sum plus its constant offset."""

    terms: tuple[tuple[int, object], ...]
    constant: int


def normalize_signed_terms(
    terms: Iterable[tuple[int, _Literal]],
    constant: int,
    *,
    flip: Callable[[_Literal], _Literal],
    key: Callable[[_Literal], Hashable] | None = None,
) -> NormalizedPBTerms:
    """Return an equivalent sum with strictly positive coefficients.

    The input represents ``constant + sum(weight * literal)``.  Negative
    terms are rewritten by complementing their literal and adjusting the
    constant.  Terms that become identical are coalesced in first-seen order.

    ``flip`` and ``key`` make the operation independent of the literal
    representation, so it works for both model literals and DIMACS integers.
    """
    if isinstance(constant, bool) or not isinstance(constant, int):
        raise ValueError("PB constant must be an integer.")

    literal_key = key or (lambda literal: literal)  # type: ignore[return-value]
    coefficients: dict[Hashable, int] = {}
    literals: dict[Hashable, _Literal] = {}
    order: list[Hashable] = []
    normalized_constant = int(constant)

    for weight, literal in terms:
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ValueError("PB integer coefficients must be integers.")
        coefficient = int(weight)
        if coefficient == 0:
            continue
        if coefficient < 0:
            literal = flip(literal)
            coefficient = -coefficient
            normalized_constant -= coefficient
        literal_id = literal_key(literal)
        if literal_id not in coefficients:
            coefficients[literal_id] = 0
            literals[literal_id] = literal
            order.append(literal_id)
        coefficients[literal_id] += coefficient

    return NormalizedPBTerms(
        terms=tuple(
            (coefficients[literal_id], literals[literal_id])
            for literal_id in order
            if coefficients[literal_id] > 0
        ),
        constant=normalized_constant,
    )
