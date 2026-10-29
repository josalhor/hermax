from typing import TYPE_CHECKING

from hermax.encoder._integer_sum.encoding import bit_channels
from .expressions import ClauseGroup

if TYPE_CHECKING:
    from .variables import IntVar


def binary_view(owner: "IntVar") -> tuple[int, ...]:
    view = owner._binary_view
    if view is not None:
        return view
    model = owner._model
    chain = [model._lit_to_dimacs(lit) for lit in owner._threshold_lits]
    if len(chain) <= 1:
        view = tuple(chain)
    else:
        literals = [model.fresh_internal_bool() for _ in range(len(chain).bit_length())]
        bits = tuple(lit.id for lit in literals)
        definitions = dict(bit_channels(chain, bits))
        # Definitions stay unconditional when the arithmetic constraint is guarded.
        for lit in literals:
            group = ClauseGroup._from_dimacs_trusted(model, definitions[lit.id])
            model._register_literal_definition(lit, group)
        view = bits
    owner._binary_view = view
    return view


def binary_view_ready(owner: "IntVar") -> bool:
    owner = owner._encoding_owner()
    if owner.ub - owner.lb <= 1:
        return True
    view = owner._binary_view
    return view is not None and all(
        bit in owner._model._realized_literal_defs for bit in view
    )
