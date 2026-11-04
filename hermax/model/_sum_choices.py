"""Size-based alternatives to the general unit-coefficient integer sum circuit."""

from dataclasses import dataclass

from hermax.internal import _encoding_policy as limits
from .expressions import ClauseGroup, PBExpr


def _coefficient(widths, target, cap):
    """Count threshold tuples at one boundary, saturating at the clause budget."""
    total = sum(widths)
    if not 0 <= target <= total:
        return 0
    target = min(target, total - target)
    if limits.STATE_LIMIT and len(widths) * (target + 1) > limits.STATE_LIMIT:
        return cap + 1
    counts = [1]
    for width in widths:
        previous = counts
        counts = []
        window = 0
        for value in range(min(target, len(previous) - 1 + width) + 1):
            if value < len(previous):
                window += previous[value]
            if 0 <= value - width - 1 < len(previous):
                window -= previous[value - width - 1]
            counts.append(min(window, cap + 1))
    return counts[target]


def direct_clause_count(widths, bound, comparator, cap):
    total = sum(widths)
    bounds = (bound, total - bound) if comparator == "==" else (bound,)
    result = 0
    for limit in bounds:
        result += 1 if limit < 0 else _coefficient(widths, limit + 1, cap)
        if result > cap:
            return cap + 1
    return result


def _direct_clauses(rows, bound, comparator):
    total = sum(map(len, rows))
    sides = [(rows, bound)]
    if comparator == "==":
        sides.append(([[-lit for lit in reversed(row)] for row in rows], total - bound))
    for chains, limit in sides:
        if limit < 0:
            yield ()
            continue
        if limit >= total:
            continue
        chains = sorted(chains, key=len)
        capacity = [0] * (len(chains) + 1)
        for i in range(len(chains) - 1, -1, -1):
            capacity[i] = capacity[i + 1] + len(chains[i])
        stack = [(0, limit + 1, ())]
        while stack:
            index, remaining, clause = stack.pop()
            if index == len(chains):
                yield clause
                continue
            row = chains[index]
            for count in range(max(0, remaining - capacity[index + 1]), min(len(row), remaining) + 1):
                stack.append((index + 1, remaining - count,
                              clause + (-row[count - 1],) if count else clause))


@dataclass(frozen=True)
class _Tree:
    begin: int
    end: int
    lower: int
    upper: int
    clauses: int = 0
    variables: int = 0
    left: "_Tree | None" = None
    right: "_Tree | None" = None


def _tree_plan(widths, bound, comparator, cap):
    from ._integer_sum import _merge_clause_upper
    from hermax.utils import _unary_merge_comparator_count

    total = sum(widths)

    def node(begin, end, root=False):
        if end - begin == 1:
            return _Tree(begin, end, 0, widths[begin])
        middle = (begin + end) // 2
        left, right = node(begin, middle), node(middle, end)
        capacity = sum(widths[begin:end])
        lower = max(0, bound - (total - capacity)) if comparator == "==" else 0
        upper = min(capacity, bound)
        a, b = left.upper - left.lower, right.upper - right.lower
        if root:
            clauses = direct_clause_count([a, b], bound - left.lower - right.lower, comparator, cap)
            variables = 0
        else:
            width = upper - lower
            if max(a, b, width) <= 31:
                clauses = direct_clause_count([a, b, width], upper - left.lower - right.lower, "==", cap)
                variables = width
            else:
                clauses = _merge_clause_upper(a, b, equality=True) + 2 * (a + b + 2)
                variables = width + 2 * _unary_merge_comparator_count(a, b)
            clauses += max(0, width - 1)
        return _Tree(begin, end, lower, upper,
                     clauses + left.clauses + right.clauses,
                     variables + left.variables + right.variables, left, right)

    return node(0, len(widths), root=True)


def choose_sum_encoding(widths, bound, comparator, clauses, variables):
    """Keep alternatives within 1.5x clauses, then score clauses + 2*auxiliaries."""
    cap = clauses * 3 // 2
    if limits.CLAUSE_LIMIT:
        cap = min(cap, limits.CLAUSE_LIMIT)
    candidates = [(clauses + 2 * variables, 2, "current", None)]
    direct = direct_clause_count(widths, bound, comparator, cap)
    if direct <= cap:
        candidates.append((direct, 0, "direct", None))
    if len(widths) >= 4:
        tree = _tree_plan(widths, bound, comparator, cap)
        if tree.clauses <= cap:
            candidates.append((tree.clauses + 2 * tree.variables, 1, "tree", tree))
    _, _, kind, tree = min(candidates, key=lambda candidate: candidate[:2])
    return kind, tree


def encode_direct(model, items, orientations, bound, comparator):
    rows = []
    for (owner, _), sign in zip(items, orientations):
        row = list(owner._threshold_ids())
        rows.append(row if sign > 0 else [-lit for lit in reversed(row)])
    return ClauseGroup._from_dimacs_trusted(model, _direct_clauses(rows, bound, comparator))


def encode_tree(model, items, orientations, bound, comparator, tree):
    groups = []

    def build(node, root=False):
        if node.left is None:
            owner = items[node.begin][0]
            return PBExpr.from_item(owner - owner.lb if orientations[node.begin] > 0 else owner.ub - owner)
        left, right = build(node.left), build(node.right)
        if root:
            condition = left + right == bound if comparator == "==" else left + right <= bound
            groups.append(condition.clauses())
            return None
        out = model.int(model._reserve_name(None), node.lower, node.upper)
        groups.append((left + right == out).clauses())
        return PBExpr.from_item(out)

    build(tree, root=True)
    clauses = (row for group in groups for row in group.iter_dimacs())
    return ClauseGroup._from_dimacs_trusted(model, clauses)
