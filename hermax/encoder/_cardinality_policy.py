"""Exact (auxiliary variables, clauses) sizes for independent Boolean inputs."""

from functools import cache
from math import isqrt


def modulo_size(count: int, bound: int) -> tuple[int, int]:
    # Size-only recurrence of cardenc/mto.hh's quotient/remainder merges.
    if bound >= count:
        return 0, 0
    if bound == count - 1:
        return 0, 1
    if bound == 0:
        return 0, count
    divisor = max(2, isqrt(bound))

    @cache
    def node(size):
        if size < 2:
            return 0, 0
        left, right = (size + 1) // 2, size // 2
        left_vars, left_clauses = node(left)
        right_vars, right_clauses = node(right)
        if size < divisor:
            return (left_vars + right_vars + size,
                    left_clauses + right_clauses + size + left * right)
        upper = min(size // divisor, bound // divisor)
        lower = divisor - 1
        left_upper = min(left // divisor, bound // divisor)
        right_upper = min(right // divisor, bound // divisor)
        left_lower, right_lower = min(left, lower), min(right, lower)
        variables = left_vars + right_vars + upper + lower + 1
        clauses = (left_clauses + right_clauses + left_lower + right_lower
                   + left_lower * right_lower + 1
                   + 2 * (left_upper + right_upper + left_upper * right_upper))
        return variables, clauses

    variables, clauses = node(count)
    return variables, clauses + divisor - 1 - bound % divisor


def sequential_size(count: int, bound: int) -> tuple[int, int]:
    if bound >= count:
        return 0, 0
    if bound == count - 1:
        return 0, 1
    return bound * (count - bound), (2 * bound + 1) * (count - bound) - bound


def shared_equality_size(count: int, bound: int) -> tuple[int, int]:
    # Unit-weight RGGT after fixed-root support filtering.
    product = bound * (count - bound)
    return product - 1, 5 * product - count - 1


def _dominates(candidate, current):
    variables, clauses = candidate
    return variables <= current[0] and clauses <= current[1] and candidate != current


def prefer_sequential(count: int, bound: int) -> bool:
    return 1 < bound < count - 1 and _dominates(
        sequential_size(count, bound), modulo_size(count, bound),
    )


def _modulo_equality_size(count, bound):
    upper = modulo_size(count, bound)
    lower = modulo_size(count, count - bound)
    return upper[0] + lower[0], upper[1] + lower[1]


def prefer_shared_equality(count: int, bound: int) -> bool:
    return min(bound, count - bound) >= 2 and _dominates(
        shared_equality_size(count, bound), _modulo_equality_size(count, bound),
    )


def reified_equality_lower_bound(count: int, bound: int) -> tuple[int, int]:
    """Lower bound for equality reification with 2 <= bound <= count - 2."""
    equality = (shared_equality_size(count, bound) if prefer_shared_equality(count, bound)
                else _modulo_equality_size(count, bound))
    sizes = [equality]
    for limit in (bound - 1, count - bound - 1):
        if limit == 1:
            # Conservative AMO bound, independent of the native policy cutoff.
            sizes.append((0, count - 1))
        else:
            sizes.append(sequential_size(count, limit) if prefer_sequential(count, limit)
                         else modulo_size(count, limit))
    return 1 + sum(size[0] for size in sizes), sum(size[1] for size in sizes)
