from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Model
    from .expressions import PBExpr, Literal
    from .variables import IntVar


@dataclass(slots=True)
class IntegerSum:
    items: list[tuple["IntVar", int]]
    constant: int
    overlapping: bool


def extract_integer_sum(model: "Model", expr: "PBExpr") -> IntegerSum | None:
    """Recover integer counts and residual literals from a flattened PB sum."""
    terms: dict[int, tuple["Literal", int]] = {}
    constant = expr.constant
    for term in expr.terms:
        if not isinstance(term.coefficient, int):
            return None
        literal, coefficient = term.literal, term.coefficient
        if not literal.polarity:
            constant += coefficient
            literal, coefficient = ~literal, -coefficient
        previous = terms.get(literal.id)
        total = coefficient + (previous[1] if previous else 0)
        if total:
            terms[literal.id] = literal, total
        else:
            terms.pop(literal.id, None)

    owners: dict[int, tuple["IntVar", list[int]]] = {}
    for literal, coefficient in terms.values():
        info = model._intvar_threshold_owner_by_litid.get(literal.id)
        if info is not None:
            owner, _ = info
            owners.setdefault(id(owner), (owner, []))[1].append(coefficient)

    items: list[tuple["IntVar", int]] = []
    overlapping = False
    for owner, coefficients in owners.values():
        width = owner.ub - owner.lb
        frequencies = Counter(coefficients)
        frequencies[0] += width - len(coefficients)
        base, count = max(frequencies.items(), key=lambda pair: pair[1])
        # A strict majority identifies one background coefficient without
        # inventing an integer contribution for sparse threshold predicates.
        if not base or count * 2 <= width:
            continue
        items.append((owner, base))
        for literal in owner._threshold_lits:
            previous = terms.get(literal.id)
            residual = (previous[1] if previous else 0) - base
            if residual:
                terms[literal.id] = literal, residual
                overlapping = True
            else:
                terms.pop(literal.id, None)

    if not items:
        return None
    items.extend(
        (model.as_int(literal), coefficient) for literal, coefficient in terms.values()
    )
    return IntegerSum(items, constant, overlapping)
