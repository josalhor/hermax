from dataclasses import dataclass
from typing import TYPE_CHECKING

from hermax.encoder._integer_sum import BINARY, LEAF, assess, encode_order, selection
from hermax.encoder._integer_sum.encoding import binary_pb
from ._integer_views import binary_view_ready
from .expressions import ClauseGroup

if TYPE_CHECKING:
    from .core import Model
    from .variables import IntVar


UNARY_CLAUSE_LIMIT = 50_000


def _merge_clause_upper(left: int, right: int, *, equality: bool) -> int:
    comparisons = 0
    if left and right:
        padded = 1 << (max(left, right) - 1).bit_length()
        comparisons = padded * (padded.bit_length() - 1) + 1
    links = 2 * (left + right + 2) if equality else left + right + 1
    return 6 * comparisons + links


def direct_addition_clause_count(left: int, right: int, result: int, bound: int) -> int:
    """Count the useful threshold pairs in a diagonal band of the input grid."""
    if bound < 0:
        return 1

    def below(total):
        def triangle(k):
            return max(0, k + 1) * max(0, k + 2) // 2
        return (triangle(total) - triangle(total - left - 1)
                - triangle(total - right - 1) + triangle(total - left - right - 2))

    return below(bound + 1) - below(bound - result)


def addition_encoding(left: int, right: int, result: int, delta: int, *, equality=False) -> str:
    last = min(left + right, max(0, delta + result + 1))
    merge = _merge_clause_upper(min(left, last), min(right, last), equality=equality)
    if equality:
        return 'general' if merge > UNARY_CLAUSE_LIMIT else 'merge'
    direct = direct_addition_clause_count(left, right, result, delta + result)
    if min(direct, merge) > UNARY_CLAUSE_LIMIT:
        return 'general'
    return 'direct' if direct <= merge else 'merge'


def compile_binary_sum(
    model: "Model", items: list[tuple["IntVar", int]], bound: int, comparator: str
) -> ClauseGroup:
    if model._inc_state.bound:
        model._reserve_literal_ids_up_to(int(model._inc_state.ip_next_vid))
    views = [owner._get_binary_view() for owner, _ in items]
    cnf = binary_pb(views, [c for _, c in items], bound, comparator, model._top_id())
    model._debug(
        model.DEBUG_COMPILE,
        f"encode path=integer_sum_binary op={comparator} clauses={len(cnf.clauses)}",
    )
    return model._cnfplus_to_clausegroup(cnf)


@dataclass(frozen=True, slots=True)
class _OrderPlan:
    kind: str
    bound: int
    orientations: list[int]
    modulus: int


def _plan_order_sum(widths, coefficients, bound, comparator, cached):
    lower = -sum(w for w, c in zip(widths, coefficients) if c < 0)
    order_bound = bound - lower
    orientations = coefficients
    if comparator == ">=":
        order_bound = sum(widths) - order_bound
        orientations = [-c for c in coefficients]
    costs = assess(widths, order_bound)
    kind = selection.choose(widths, order_bound, costs, cached, orientations=orientations)
    return _OrderPlan(kind, order_bound, orientations, costs.modulus)


def _encode_order_plan(model, items, bound, comparator, plan):
    if plan.kind == BINARY:
        return compile_binary_sum(model, items, bound, comparator)
    if model._inc_state.bound:
        model._reserve_literal_ids_up_to(int(model._inc_state.ip_next_vid))
    chains = []
    for (owner, _), sign in zip(items, plan.orientations):
        row = [model._lit_to_dimacs(lit) for lit in owner._threshold_lits]
        chains.append(row if sign > 0 else [-lit for lit in reversed(row)])
    cnf = encode_order(
        chains, plan.bound, model._top_id(), plan.kind,
        plan.modulus if plan.kind != LEAF else 0, _packed=True,
    )
    model._debug(
        model.DEBUG_COMPILE,
        f"encode path=integer_sum_{plan.kind} op={comparator} clauses={len(cnf.clauses)}",
    )
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
    if comparator not in ("<=", ">=", "=="):
        raise ValueError("unsupported integer-sum comparison")
    cached = [binary_view_ready(owner) for owner, _ in items]
    if comparator == "==":
        upper_plan = _plan_order_sum(widths, coefficients, bound, "<=", cached)
        lower_plan = _plan_order_sum(widths, coefficients, bound, ">=", cached)
        if upper_plan.kind == lower_plan.kind == BINARY:
            return compile_binary_sum(model, items, bound, "==")
        return _encode_order_plan(model, items, bound, "<=", upper_plan) & _encode_order_plan(
            model, items, bound, ">=", lower_plan
        )
    plan = _plan_order_sum(widths, coefficients, bound, comparator, cached)
    return _encode_order_plan(model, items, bound, comparator, plan)
