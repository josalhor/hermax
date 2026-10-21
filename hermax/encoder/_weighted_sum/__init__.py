"""Internal weighted-sum equality compiler.

The Model supplies shared threshold/value literals. Candidate encoders use
private CNF buffers; only the smaller result is committed to the Model.
"""
from collections.abc import Iterable, Mapping, Sequence

from .common import CNFBuilder
from .graph import GraphPlan, plan_graph, encode_graph
from .grouped import GroupedPlan, plan_grouped, encode_grouped
from .sorting import SortingPlan, plan_sorting, encode_sorting

Plan = GraphPlan | GroupedPlan | SortingPlan

__all__ = ['plan_candidates', 'encode_best']


def plan_candidates(
    lits: Sequence[int], weights: Sequence[int], upper: int,
    exactly_one: Sequence[Sequence[int]] = (),
) -> tuple[Plan, ...]:
    """Return each applicable construction, without size-based rejection."""
    candidates = [
        plan_graph(lits, weights, upper, exactly_one),
        plan_grouped(lits, weights, upper, exactly_one),
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    if not candidates:
        constant = plan_sorting(lits, weights, upper, exactly_one)
        # A sum of constant EO choices needs no support graph. Never select
        # the experimental weighted sorter for a nonconstant production sum.
        if constant is not None and not constant.tokens:
            candidates.append(constant)
    return tuple(candidates)


def plan_by_estimate(lits, weights, upper, exactly_one=()):
    """Keep the estimate-only reference available for isolated encoder studies."""
    return min(plan_candidates(lits, weights, upper, exactly_one),
               key=lambda p: (p.cost.clauses, p.cost.auxiliary_variables),
               default=None)


def encode_candidate(
    plan: Plan, thresholds: Sequence[int], top_id: int,
    values: Mapping[int, int] | None = None,
) -> CNFBuilder:
    if isinstance(plan, SortingPlan):
        return encode_sorting(plan, thresholds, top_id, values)
    if isinstance(plan, GroupedPlan):
        return encode_grouped(plan, thresholds, top_id, values)
    return encode_graph(plan, thresholds, top_id, values)


def encode_best(
    plans: Iterable[Plan], thresholds: Sequence[int], top_id: int,
    values: Mapping[int, int] | None = None,
) -> CNFBuilder | None:
    """Use identical input IDs for both candidates; allocate nothing in a Model.

    Minimize actual clause count, then auxiliary IDs. Exact ties retain the
    first candidate. Only the returned CNF may be committed to the Model.
    """
    best = None
    for plan in plans:
        candidate = encode_candidate(plan, thresholds, top_id, values)
        if best is None or (len(candidate.clauses), candidate.nv) < (len(best.clauses), best.nv):
            best = candidate
    return best
