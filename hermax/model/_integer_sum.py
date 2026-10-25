from typing import TYPE_CHECKING

from hermax.encoder._integer_sum import BINARY, LEAF, assess, encode_order, selection
from hermax.encoder._integer_sum.encoding import binary_pb
from ._integer_views import binary_view_ready
from .expressions import ClauseGroup

if TYPE_CHECKING:
    from .core import Model
    from .variables import IntVar


UNARY_CLAUSE_LIMIT = 50_000


def unary_sum_too_large(left: int, right: int, *, equality: bool = False) -> bool:
    if not left or not right:
        return False
    padded = 1 << (max(left, right) - 1).bit_length()
    comparisons = padded * (padded.bit_length() - 1) + 1
    links = 2 * (left + right + 2) if equality else left + right + 1
    merge = 6 * comparisons + links
    cost = merge if equality else min(merge, (left + 1) * (right + 1))
    return cost > UNARY_CLAUSE_LIMIT


def compile_binary_sum(
    model: "Model", items: list[tuple["IntVar", int]], bound: int, comparator: str
) -> ClauseGroup:
    if model._inc_state.bound:
        model._reserve_literal_ids_up_to(int(model._inc_state.ip_next_vid))
    views = [owner._get_binary_view() for owner, _ in items]
    cnf = binary_pb(views, [c for _, c in items], bound, comparator, model._top_id())
    return model._cnfplus_to_clausegroup(cnf)


def compile_sum(
    model: "Model", items: list[tuple["IntVar", int]], constant: int, comparator: str
) -> ClauseGroup:
    """Compile sum(c*(x-lb)) + constant OP 0, retaining the public order view."""
    if comparator == "<":
        comparator, bound = "<=", -constant - 1
    elif comparator == ">":
        comparator, bound = ">=", -constant + 1
    else:
        bound = -constant
    widths = [owner.ub - owner.lb for owner, _ in items]
    coefficients = [coefficient for _, coefficient in items]
    lower = -sum(w for w, c in zip(widths, coefficients) if c < 0)
    upper = sum(w for w, c in zip(widths, coefficients) if c > 0)
    satisfied = (comparator == "<=" and bound >= upper) or (
        comparator == ">=" and bound <= lower
    )
    impossible = (
        (comparator == "<=" and bound < lower)
        or (comparator == ">=" and bound > upper)
        or (comparator == "==" and not lower <= bound <= upper)
    )
    if satisfied or impossible:
        return ClauseGroup._from_dimacs_trusted(model, [[]] if impossible else [])
    if comparator == "==":
        return compile_sum(model, items, constant, "<=") & compile_sum(
            model, items, constant, ">="
        )
    if comparator not in ("<=", ">="):
        raise ValueError("unsupported integer-sum comparison")

    # Convert to an at-most sum of nonnegative, possibly complemented chains.
    total = sum(widths)
    order_bound = bound - lower
    orientations = coefficients
    if comparator == ">=":
        order_bound = total - order_bound
        orientations = [-c for c in coefficients]
    costs = assess(widths, order_bound)
    cached = [binary_view_ready(owner) for owner, _ in items]
    kind = selection.choose(
        widths, order_bound, costs, cached, orientations=orientations
    )

    # Respect IDs already owned by an attached incremental backend as well.
    if model._inc_state.bound:
        model._reserve_literal_ids_up_to(int(model._inc_state.ip_next_vid))
    if kind == BINARY:
        views = [owner._get_binary_view() for owner, _ in items]
        cnf = binary_pb(views, coefficients, bound, comparator, model._top_id())
    else:
        chains = []
        for (owner, _), sign in zip(items, orientations):
            row = [model._lit_to_dimacs(lit) for lit in owner._threshold_lits]
            chains.append(row if sign > 0 else [-lit for lit in reversed(row)])
        cnf = encode_order(
            chains,
            order_bound,
            model._top_id(),
            kind,
            costs.modulus if kind != LEAF else 0,
        )
    model._debug(
        model.DEBUG_COMPILE,
        f"encode path=integer_sum_{kind} op={comparator} clauses={len(cnf.clauses)}",
    )
    return model._cnfplus_to_clausegroup(cnf)
