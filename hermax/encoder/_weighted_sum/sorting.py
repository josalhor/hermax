"""Experimental direct weighted counter; no PBLib call or binary expansion.

Each contribution is a run of aliases of its Boolean literal. A common divisor
and disjoint exactly-one offsets reduce the runs before sorting. The sorted
outputs are the integer's thresholds. This is a different propagation tradeoff
from the support graph, so it is not silently selected by production routing.
"""
from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from math import gcd

from .common import CNFBuilder, Layer, SizeBounds, define_value_literals, negate, normalize_terms
from .networks import ComparatorNetwork, comparator_count


@dataclass(frozen=True)
class SortingPlan:
    layers: tuple[Layer, ...]
    shift: int
    scale: int
    tokens: int
    cost: SizeBounds


def plan_sorting(
    lits: Sequence[int], weights: Sequence[int], upper: int,
    exactly_one: Sequence[Sequence[int]] = (),
) -> SortingPlan | None:
    normalized = normalize_terms(lits, weights, upper, exactly_one)
    if normalized is None:
        return None
    layers, shift = normalized
    scale = gcd(*(weight for layer in layers for _, weight in layer)) or 1
    size = sum(weight // scale for layer in layers for _, weight in layer)
    comparators = comparator_count(size)
    cost = SizeBounds(2 * comparators + upper - 1, 6 * comparators + 6 * upper + 1)
    return SortingPlan(tuple(layers), shift, scale, size, cost)


def encode_sorting(
    plan: SortingPlan, thresholds: Sequence[int], top_id: int,
    values: Mapping[int, int] | None = None,
) -> CNFBuilder:
    cnf = CNFBuilder([], top_id)
    upper = len(thresholds)
    if values is None:
        values = define_value_literals(thresholds, cnf)
    inputs = [
        lit for layer in plan.layers for lit, weight in layer
        for _ in range(weight // plan.scale)
    ]
    outputs = ComparatorNetwork(cnf).sort(inputs)
    for value, literal in enumerate(thresholds, 1):
        rank = (value - plan.shift + plan.scale - 1) // plan.scale
        signal = True if rank <= 0 else outputs[rank-1] if rank <= len(outputs) else False
        cnf.add(-literal, signal)
        cnf.add(literal, negate(signal))
    # Preserve the graph's root exclusions, including those from EO facts.
    reachable = 1
    for layer in plan.layers:
        following = 0
        for _, weight in layer:
            following |= reachable << (weight // plan.scale)
        reachable = following
    for value, literal in values.items():
        delta = value - plan.shift
        if delta < 0 or delta % plan.scale or not (reachable >> (delta // plan.scale)) & 1:
            cnf.add(-literal)
    assert cnf.nv - top_id <= plan.cost.auxiliary_variables
    assert len(cnf.clauses) <= plan.cost.clauses
    return cnf
