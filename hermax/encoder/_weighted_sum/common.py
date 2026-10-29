"""CNF construction and normalization shared by weighted-sum encoders."""
from collections.abc import Sequence
from dataclasses import dataclass
from math import gcd

Choice = tuple[int, int]
Layer = tuple[Choice, ...]
Signal = int | bool


@dataclass(frozen=True)
class SizeBounds:
    """Upper bounds on one sum encoding's size."""

    auxiliary_variables: int
    clauses: int


@dataclass
class CNFBuilder:
    clauses: list[tuple[int, ...]]
    nv: int

    def fresh(self) -> int:
        self.nv += 1
        return self.nv

    def add(self, *lits: Signal) -> None:
        if any(lit is True for lit in lits):
            return
        clause = tuple(dict.fromkeys(lit for lit in lits if lit is not False))
        present = set(clause)
        if not any(-lit in present for lit in clause):
            self.clauses.append(clause)


def negate(lit: Signal) -> Signal:
    return not lit if isinstance(lit, bool) else -lit


def normalize_terms(
    lits: Sequence[int],
    weights: Sequence[int],
    upper: int,
    exactly_one: Sequence[Sequence[int]] = (),
) -> tuple[list[Layer], int] | None:
    """Build independent choice layers using unconditional exactly-one facts.

    Each layer contributes one cost. Constant layers become an offset, and the
    output domain must cover every remaining combination of choices.
    """
    if (
        len(lits) != len(weights)
        or upper < 2
        or not weights
        or any(w <= 0 for w in weights)
        or len({abs(lit) for lit in lits}) != len(lits)
    ):
        return None
    costs = dict(zip(lits, weights))
    grouped = set()
    layers = []
    shift = 0
    for group in exactly_one:
        if (
            not group
            or len(set(map(abs, group))) != len(group)
            or any(lit not in costs or abs(lit) in grouped for lit in group)
        ):
            return None
        grouped.update(map(abs, group))
        base = min(costs[lit] for lit in group)
        shift += base
        options = tuple((lit, costs[lit] - base) for lit in group)
        if any(weight for _, weight in options):
            layers.append(options)
    layers.extend(
        ((-lit, 0), (lit, weight))
        for lit, weight in sorted(costs.items())
        if abs(lit) not in grouped
    )
    if shift + sum(max(w for _, w in layer) for layer in layers) > upper:
        return None
    return layers, shift


def exclude_value_gaps(thresholds: Sequence[int], values, cnf: CNFBuilder) -> None:
    possible = sorted(values)
    if not possible:
        cnf.add()
        return
    if possible[0] > 0:
        cnf.add(thresholds[possible[0] - 1])
    for lower, upper in zip(possible, possible[1:]):
        if upper > lower + 1:
            cnf.add(-thresholds[lower], thresholds[upper - 1])
    if possible[-1] < len(thresholds):
        cnf.add(-thresholds[possible[-1]])


def define_value_literals(thresholds: Sequence[int], cnf: CNFBuilder) -> dict[int, int]:
    """Define exact integer values from the caller's ordered threshold literals."""
    upper = len(thresholds)
    values = {0: -thresholds[0], upper: thresholds[-1]}
    for value in range(1, upper):
        literal = cnf.fresh()
        values[value] = literal
        lower, higher = thresholds[value - 1], thresholds[value]
        cnf.add(-literal, lower)
        cnf.add(-literal, -higher)
        cnf.add(literal, -lower, higher)
    return values


def graph_bounds(cost_layers: Sequence[Sequence[int]], upper: int) -> tuple[int, int, int, int]:
    """Bound states, edges, auxiliary variables and clauses without building a graph."""
    widths = [1]
    product = 1
    span = divisor = edges = 0
    for costs in cost_layers:
        edges += widths[-1] * len(costs)
        product = min(upper + 1, product * len(set(costs)))
        span += max(costs)
        divisor = gcd(divisor, *costs)
        widths.append(min(product, span // divisor + 1))
    states = sum(widths)
    variables = sum(widths[1:-1]) + edges + upper - 1
    clauses = 3 * edges + 2 * states + sum(map(len, cost_layers)) + 4 * upper + 1
    return states, edges, variables, clauses
