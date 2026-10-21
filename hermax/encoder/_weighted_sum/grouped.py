"""Compress interchangeable Boolean terms before building a support graph."""
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .common import CNFBuilder, Layer, SizeBounds, graph_bounds, negate, normalize_terms
from .graph import GraphPlan, encode_graph
from .networks import ComparatorNetwork, comparator_count


@dataclass(frozen=True)
class GroupedPlan:
    choices: tuple[Layer, ...]
    buckets: tuple[tuple[tuple[int, ...], int], ...]
    order: tuple[int, ...]
    shift: int
    states: int
    edges: int
    cost: SizeBounds


def plan_grouped(
    lits: Sequence[int], weights: Sequence[int], upper: int,
    exactly_one: Sequence[Sequence[int]] = (),
) -> GroupedPlan | None:
    """Count equal-weight inputs, retaining existing exactly-one choice layers."""
    normalized = normalize_terms(lits, weights, upper, exactly_one)
    if normalized is None:
        return None
    layers, shift = normalized
    buckets, choices = defaultdict(list), []
    for layer in layers:
        if len(layer) == 2 and layer[0][0] == -layer[1][0] and layer[0][1] == 0:
            buckets[layer[1][1]].append(layer[1][0])
        else:
            choices.append(layer)
    if not any(len(group) > 1 for group in buckets.values()):
        return None
    private_vars = private_clauses = 0
    # Use deterministic coefficient order, without enumerating sums.
    specs = [(tuple(group), weight) for weight, group in sorted(buckets.items())]
    cost_layers = [tuple(weight for _, weight in layer) for layer in choices]
    for group, weight in specs:
        n = len(group)
        compares = comparator_count(n)
        private_vars += 2 * compares + max(0, n - 1)
        private_clauses += 6 * compares + 4 * max(0, n - 1)
        cost_layers.append(tuple(weight * k for k in range(n + 1)))
    natural = tuple(range(len(cost_layers)))
    orders = [natural]
    for key in (lambda i: max(cost_layers[i]), lambda i: len(cost_layers[i])):
        orders.extend(
            tuple(sorted(natural, key=key, reverse=reverse))
            for reverse in (False, True)
        )
    plans = []
    for order in dict.fromkeys(orders):
        states, edges, variables, clauses = graph_bounds([cost_layers[i] for i in order], upper)
        variables += private_vars
        clauses += private_clauses
        cost = SizeBounds(variables, clauses)
        plans.append(GroupedPlan(
            tuple(choices), tuple(specs), order, shift, states, edges, cost,
        ))
    return min(plans, key=lambda p: (p.cost.clauses, p.cost.auxiliary_variables), default=None)


def encode_grouped(
    plan: GroupedPlan, thresholds: Sequence[int], top_id: int,
    values: Mapping[int, int] | None = None,
) -> CNFBuilder:
    """Connect each group's exact count to the shared weighted-sum graph."""
    cnf = CNFBuilder([], top_id)
    network = ComparatorNetwork(cnf)
    layers = list(plan.choices)
    for group, weight in plan.buckets:
        outputs = network.sort(list(group))
        for a, b in zip(outputs, outputs[1:]):
            cnf.add(negate(b), a)
        count_values = [negate(outputs[0])]
        count_values.extend(
            network.conjunction(a, negate(b)) for a, b in zip(outputs, outputs[1:])
        )
        count_values.append(outputs[-1])
        layers.append(tuple((literal, weight * k) for k, literal in enumerate(count_values)))
    graph_plan = GraphPlan(
        tuple(layers[i] for i in plan.order), plan.shift, plan.states, plan.edges, plan.cost,
    )
    graph = encode_graph(graph_plan, thresholds, cnf.nv, values)
    cnf.clauses.extend(graph.clauses)
    cnf.nv = graph.nv
    assert cnf.nv - top_id <= plan.cost.auxiliary_variables
    assert len(cnf.clauses) <= plan.cost.clauses
    return cnf
