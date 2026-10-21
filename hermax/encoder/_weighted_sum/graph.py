"""Support-graph encoding of a full-range weighted sum onto order bits.

A layer chooses one (literal, cost) pair. States are reachable prefix sums;
transition, state and choice supports encode both directions of the relation.
Arithmetic size bounds guide ordering and check the emitted construction.
"""
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .common import (
    CNFBuilder, Layer, SizeBounds, define_value_literals, graph_bounds,
    negate, normalize_terms,
)
from .networks import ComparatorNetwork, comparator_count


@dataclass(frozen=True)
class GraphPlan:
    layers: tuple[Layer, ...]
    shift: int
    states: int
    edges: int
    cost: SizeBounds
    construction: str = 'graph'


def plan_graph(
    lits: Sequence[int], weights: Sequence[int], upper: int,
    exactly_one: Sequence[Sequence[int]] = (),
) -> GraphPlan | None:
    """Bound the support graph without enumerating any sums."""
    normalized = normalize_terms(lits, weights, upper, exactly_one)
    if normalized is None or not normalized[0]:
        return None
    layers, shift = normalized

    orders = (
        layers,
        sorted(layers, key=lambda row: max(w for _, w in row)),
        sorted(layers, key=lambda row: max(w for _, w in row), reverse=True),
    )
    plans = []
    for order in orders:
        states, edges, variables, clauses = graph_bounds(
            [tuple(weight for _, weight in layer) for layer in order], upper,
        )
        cost = SizeBounds(variables, clauses)
        plans.append(GraphPlan(tuple(order), shift, states, edges, cost))
    if not exactly_one and len(set(weights)) == 1:
        size = len(lits)
        comparators = comparator_count(size)
        cost = SizeBounds(
            2 * comparators + upper - 1,
            6 * comparators + 6 * upper + 1,
        )
        plans.append(GraphPlan(tuple(layers), shift, 0, 0, cost, 'count'))
    return min(plans, key=lambda p: (p.cost.clauses, p.cost.auxiliary_variables))


def encode_graph(
    plan: GraphPlan, thresholds: Sequence[int], top_id: int,
    values: Mapping[int, int] | None = None,
) -> CNFBuilder:
    """Emit the selected graph once, in local IDs; never mutate a Model."""
    cnf = CNFBuilder([], top_id)
    if values is None:
        values = define_value_literals(thresholds, cnf)

    if plan.construction == 'count':
        _encode_count(plan, thresholds, values, cnf)
    else:
        _encode_support_graph(plan, values, cnf)
    assert cnf.nv - top_id <= plan.cost.auxiliary_variables
    assert len(cnf.clauses) <= plan.cost.clauses
    return cnf


def _build_transitions(layers: Sequence[Layer]):
    """Enumerate reachable prefix sums and their labelled transitions."""
    states = [(0,)]
    transitions = []
    for layer in layers:
        row = tuple((source, source + weight, lit)
                    for source in states[-1] for lit, weight in layer)
        transitions.append(row)
        states.append(tuple(sorted({destination for _, destination, _ in row})))
    return states, transitions


def _encode_support_graph(plan: GraphPlan, values: Mapping[int, int], cnf: CNFBuilder) -> None:
    states, transitions = _build_transitions(plan.layers)
    nodes = [{0: True}]
    nodes.extend({value: cnf.fresh() for value in row} for row in states[1:-1])
    nodes.append({value: values[value + plan.shift] for value in states[-1]})

    incoming, outgoing = _encode_transitions(plan.layers, nodes, transitions, cnf)
    for index, row in enumerate(nodes):
        for value, node in row.items():
            if index:
                cnf.add(negate(node), *incoming[index, value])
            if index < len(plan.layers):
                cnf.add(negate(node), *outgoing[index, value])
    possible = {value + plan.shift for value in states[-1]}
    for value, literal in values.items():
        if value not in possible:
            cnf.add(-literal)


def _encode_transitions(layers, nodes, transitions, cnf: CNFBuilder):
    """Define edges and choice supports, returning incoming/outgoing supports."""
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for index, row in enumerate(transitions):
        in_counts, out_counts = defaultdict(int), defaultdict(int)
        for source, destination, _ in row:
            in_counts[destination] += 1
            out_counts[source] += 1
        labels = {lit: [] for lit, _ in layers[index]}
        for source, destination, label in row:
            # Single-edge supports identify edge and node: substitute that
            # existing signal, preserving every support clause in both directions.
            if in_counts[destination] == 1:
                edge = nodes[index + 1][destination]
            elif out_counts[source] == 1:
                edge = nodes[index][source]
            else:
                edge = cnf.fresh()
            cnf.add(negate(edge), nodes[index][source])
            cnf.add(negate(edge), nodes[index + 1][destination])
            cnf.add(negate(edge), label)
            incoming[index + 1, destination].append(edge)
            outgoing[index, source].append(edge)
            labels[label].append(edge)
        for label, support in labels.items():
            cnf.add(-label, *support)
    return incoming, outgoing


def _encode_count(
    plan: GraphPlan, thresholds: Sequence[int], values: Mapping[int, int], cnf: CNFBuilder,
) -> None:
    """Exact comparator network for identical weights, with full channeling."""
    inputs = [next(lit for lit, weight in layer if weight) for layer in plan.layers]
    weight = max(weight for _, weight in plan.layers[0])

    size = len(inputs)
    outputs = ComparatorNetwork(cnf).sort(inputs)

    for threshold, literal in enumerate(thresholds, 1):
        count = (threshold + weight - 1) // weight
        signal = outputs[count - 1] if count <= size else False
        cnf.add(-literal, signal)
        cnf.add(literal, negate(signal))
    for value, literal in values.items():
        if value % weight or value > size * weight:
            cnf.add(-literal)
