from typing import TYPE_CHECKING

from .expressions import PBExpr, Term

if TYPE_CHECKING:
    from .core import Model
    from .variables import IntVar


def lower_integer_objective(expr: PBExpr, model: "Model") -> PBExpr:
    expr = expr._realize_int_terms(model)
    groups: dict[int, tuple["IntVar", list[Term]]] = {}
    for term in expr.terms:
        info = model._intvar_threshold_owner_by_litid.get(term.literal.id)
        if info is not None:
            owner, _ = info
            groups.setdefault(id(owner), (owner, []))[1].append(term)

    removed = set()
    replacements = []
    constant = expr.constant
    for owner, terms in groups.values():
        width = owner.ub - owner.lb
        cutoff = 16 if owner._binary_view is not None else 32
        if width < cutoff or len(terms) != width:
            continue
        coefficient = terms[0].coefficient * (1 if terms[0].literal.polarity else -1)
        if any(
            t.coefficient * (1 if t.literal.polarity else -1) != coefficient
            for t in terms
        ):
            continue
        # A complete, uniformly weighted chain equals x - lb.
        for term in terms:
            removed.add(id(term))
            if not term.literal.polarity:
                constant += term.coefficient
        for index, bit in enumerate(owner._get_binary_view()):
            replacements.append(
                Term(coefficient * (1 << index), model._dimacs_to_lit(bit))
            )
    if not removed:
        return expr
    return PBExpr(
        model, [t for t in expr.terms if id(t) not in removed] + replacements, constant
    )
