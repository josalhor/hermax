"""Internal weighted-sum equality compiler.

The Model supplies shared threshold/value literals. Candidate encoders use
private CNF buffers; only the smaller result is committed to the Model.
"""
from collections.abc import Iterable, Mapping, Sequence

from .common import CNFBuilder, exclude_value_gaps
from .graph import GraphPlan, plan_graph, encode_graph
from .grouped import GroupedPlan, plan_grouped, encode_grouped
from .sorting import SortingPlan, plan_sorting, encode_sorting
from .networks import comparator_count

Plan = GraphPlan | GroupedPlan | SortingPlan

__all__ = ['plan_candidates', 'encode_best']

STATE_LIMIT = 20_000
CLAUSE_LIMIT = 50_000


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


def _cost_layers(plan: Plan):
    if isinstance(plan, GroupedPlan):
        costs = [tuple(weight for _, weight in layer) for layer in plan.choices]
        costs.extend(tuple(weight * k for k in range(len(group) + 1))
                     for group, weight in plan.buckets)
        return [costs[i] for i in plan.order]
    return [tuple(weight for _, weight in layer) for layer in plan.layers]


def _reachability(plan: Plan):
    reachable = states = 1
    edges = choices = 0
    for costs in _cost_layers(plan):
        edges += reachable.bit_count() * len(costs)
        choices += len(costs)
        following = 0
        for weight in set(costs):
            following |= reachable << weight
        reachable = following
        states += reachable.bit_count()
    return reachable, states, edges, choices


def _values(shift, reachable):
    values = []
    # Decode bytes rather than repeatedly shifting a potentially large integer.
    for block, byte in enumerate(reachable.to_bytes((reachable.bit_length() + 7) // 8, "little")):
        while byte:
            bit = byte & -byte
            values.append(shift + 8 * block + bit.bit_length() - 1)
            byte ^= bit
    return tuple(values)


def reachable_values(plan: Plan) -> tuple[int, ...]:
    return _values(plan.shift, _reachability(plan)[0])


def bounded_candidates(plans: Iterable[Plan]):
    """Preflight support-graph growth before allocating value literals or CNF."""
    accepted, possible = [], ()
    for plan in plans:
        reachable, states, edges, choices = _reachability(plan)
        if isinstance(plan, GraphPlan) and plan.construction == 'count':
            states, clauses = 0, plan.cost.clauses
        else:
            clauses = 3 * edges + 2 * states + choices + 4 * reachable.bit_count() + 1
            if isinstance(plan, GroupedPlan):
                clauses += sum(6 * comparator_count(len(group)) + 4 * (len(group) - 1)
                               for group, _ in plan.buckets)
        if states > STATE_LIMIT or clauses > CLAUSE_LIMIT:
            continue
        accepted.append(plan)
        if not possible:
            possible = _values(plan.shift, reachable)
    return tuple(accepted), possible


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
    if best is not None and values is not None:
        exclude_value_gaps(thresholds, values, best)
    return best
