"""Preserve small weighted PB encodings; use cached binary views on budget overflow."""
from functools import reduce
from math import gcd
from itertools import chain
from typing import TYPE_CHECKING

from hermax.encoder._integer_sum import weighted
from .expressions import ClauseGroup
from ._integer_sum import compile_binary_sum

if TYPE_CHECKING:
    from .core import Model
    from .variables import IntVar


def compile_weighted_sum(
    model: "Model", items: list[tuple["IntVar", int]], bound: int, comparator: str
) -> ClauseGroup:
    """Compile weighted integer counts, retaining any separate AMO/EO clauses."""
    divisor = reduce(gcd, (abs(c) for _, c in items))
    if comparator == "==" and bound % divisor:
        return ClauseGroup._from_dimacs_trusted(model, [[]])
    bound = -((-bound) // divisor) if comparator == ">=" else bound // divisor
    coefficients = [c // divisor for _, c in items]
    widths = [x.ub - x.lb for x, _ in items]
    minimum = sum(min(0, c * w) for c, w in zip(coefficients, widths))
    maximum = sum(max(0, c * w) for c, w in zip(coefficients, widths))
    impossible = (comparator in ("<=", "==") and bound < minimum) or (
        comparator in (">=", "==") and bound > maximum
    )
    satisfied = (comparator == "<=" and bound >= maximum) or (
        comparator == ">=" and bound <= minimum
    )
    if impossible or satisfied:
        return ClauseGroup._from_dimacs_trusted(model, [[]] if impossible else [])

    chains = [
        [model._lit_to_dimacs(lit) for lit in owner._threshold_lits]
        for owner, _ in items
    ]
    reason = None
    if model._known_amo_groups or model._known_eo_groups:
        literals = {
            lit if c > 0 else -lit
            for row, c in zip(chains, coefficients)
            for lit in row
        }
        groups = chain(
            model._known_amo_groups.values(), model._known_eo_groups.values()
        )
        if any(len(literals.intersection(group)) > 1 for group in groups):
            reason = "amo"

    if reason is None:
        if model._inc_state.bound:
            model._reserve_literal_ids_up_to(int(model._inc_state.ip_next_vid))
        try:
            cnf = weighted.encode_thresholds(
                chains, coefficients, bound, comparator, model._top_id(), _packed=True
            )
        except weighted.BudgetExceeded as error:
            reason = f"budget={error}"
        else:
            model._debug(
                model.DEBUG_COMPILE,
                f"encode path=weighted_integer_thresholds op={comparator} clauses={len(cnf.clauses)}",
            )
            return model._cnfplus_to_clausegroup(cnf)

    model._debug(model.DEBUG_COMPILE, f"encode path=weighted_integer_binary reason={reason}")
    normalized = [(x, c) for (x, _), c in zip(items, coefficients)]
    return compile_binary_sum(model, normalized, bound, comparator)
