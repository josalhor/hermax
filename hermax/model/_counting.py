"""Requested thresholds of Boolean counts and order-encoded sums."""

from hermax.utils import batcher_odd_even_unary_add_network, _unary_merge_comparator_count
from .expressions import Clause


def _append_implication(clauses, model, antecedent, consequent):
    if antecedent is False or consequent is True:
        return
    literals = []
    if antecedent is not True:
        literals.append(~antecedent)
    if consequent is not False:
        literals.append(consequent)
    clauses.append(Clause(model, literals))


def count_clause_upper(count, thresholds):
    if not thresholds:
        return 0
    forward, backward = max(thresholds), count - min(thresholds) + 1
    limit = min(forward, backward)
    clauses = max(0, len(thresholds) - 1) if backward < forward else 0
    if limit == 1:
        return clauses + 3 * (count - 1)
    rows, width = count, 1
    while rows > 1:
        size = min(width, limit)
        clauses += (rows // 2) * 6 * _unary_merge_comparator_count(size, size)
        rows = (rows + 1) // 2
        width *= 2
    return clauses


def count_thresholds(model, literals, thresholds, and_gate, or_gate):
    return merge_thresholds(model, [[lit] for lit in literals], thresholds, and_gate, or_gate)


def merge_thresholds(model, chains, thresholds, and_gate, or_gate):
    thresholds = sorted(set(thresholds))
    if not thresholds:
        return [], {}
    limit = max(thresholds)
    total = sum(map(len, chains))
    if thresholds[0] < 1 or limit > total:
        raise ValueError('Count thresholds must be between one and the input count.')
    # For Boolean counts near the upper end, count false inputs instead.
    if (
        total - thresholds[0] + 1 < limit
        and all(len(row) == 1 for row in chains)
    ):
        clauses, outputs = merge_thresholds(
            model, [[~literal for literal in reversed(row)] for row in chains],
            [total - threshold + 1 for threshold in thresholds], and_gate, or_gate,
        )
        inverted = {}
        for threshold in thresholds:
            value = outputs[total - threshold + 1]
            inverted[threshold] = not value if isinstance(value, bool) else ~value
        for lower, upper in zip(thresholds, thresholds[1:]):
            _append_implication(clauses, model, inverted[upper], inverted[lower])
        return clauses, inverted
    nodes = {}
    next_id = max(abs(model._lit_to_dimacs(lit)) for row in chains for lit in row) + 1

    def gate(operation, left, right):
        nonlocal next_id
        if isinstance(left, bool):
            return (right if left else False) if operation == 'and' else (True if left else right)
        if isinstance(right, bool):
            return gate(operation, right, left)
        if left == right:
            return left
        if left == -right:
            return operation == 'or'
        result = next_id
        next_id += 1
        nodes[result] = operation, left, right
        return result

    rows = [[model._lit_to_dimacs(lit) for lit in row[:limit]] for row in chains if len(row)]
    while len(rows) > 1:
        merged = []
        for index in range(0, len(rows), 2):
            if index + 1 == len(rows):
                merged.append(rows[index])
                continue
            left, right = rows[index:index + 2]
            network = batcher_odd_even_unary_add_network(len(left), len(right))
            half = network.n // 2
            wires = ([False] * (half - len(left)) + list(reversed(left))
                     + [False] * (half - len(right)) + list(reversed(right)))
            for i, j in network:
                a, b = wires[i], wires[j]
                wires[i], wires[j] = gate('and', a, b), gate('or', a, b)
            # Counts above the largest requested threshold cannot affect these outputs.
            merged.append(list(reversed(wires))[:min(limit, len(left) + len(right))])
        rows = merged

    clauses, realized = [], {}

    def realize(value):
        if isinstance(value, bool):
            return value
        if value not in nodes:
            return model._dimacs_to_lit(value)
        if value not in realized:
            operation, left, right = nodes[value]
            build = and_gate if operation == 'and' else or_gate
            realized[value] = build(clauses, model, realize(left), realize(right))
        return realized[value]

    outputs = {threshold: realize(rows[0][threshold - 1]) for threshold in thresholds}
    return clauses, outputs
