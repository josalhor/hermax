"""Integer-sum encoder selection."""
from collections.abc import Sequence
from math import sqrt

from .encoding import BINARY, LEAF, WHOLE, Costs, channel_cost


def features(
    widths: Sequence[int],
    bound: int,
    costs: Costs,
    cached: Sequence[bool] = (),
    *,
    orientations: Sequence[int] = ()
) -> dict[str, float]:
    """Input and cost features used by the fitted policy."""
    n = len(widths)
    if not n:
        raise ValueError("selection requires an integer sum")
    cached = cached or (False,) * n
    orientations = orientations or (1,) * n
    if len(cached) != n or len(orientations) != n:
        raise ValueError("integer-sum metadata has the wrong length")
    total = sum(widths)
    mean = total / n
    bits = [w.bit_length() for w in widths]
    padded = [(1 << b) - 1 for b in bits]
    padding = sum(padded) - total
    negative_padding = sum(
        p - w for p, w, c in zip(padded, widths, orientations) if c < 0
    )
    channels = sum(channel_cost(w) for w, exists in zip(widths, cached) if not exists)
    fresh_bits = sum(
        b for b, w, exists in zip(bits, widths, cached) if w > 1 and not exists
    )
    return {
        "count": n,
        "total_width": total,
        "max_width": max(widths),
        "mean_width": mean,
        "width_variation": sqrt(sum((w - mean) ** 2 for w in widths) / n)
        / max(1, mean),
        "boolean_fraction": sum(w <= 1 for w in widths) / n,
        "bound": bound,
        "bound_fraction": bound / max(1, total),
        "edge_distance": min(bound, total - bound),
        "binary_inputs": sum(bits),
        "fresh_binary_bits": fresh_bits,
        "fresh_channel_clauses": channels,
        "binary_padding_fraction": padding / max(1, total),
        "binary_bound_fraction": (bound + negative_padding) / max(1, sum(padded)),
        "negative_fraction": sum(c < 0 for c in orientations) / n,
        "cached_fraction": sum(cached) / n,
        "whole_variables": costs.whole.variables,
        "whole_clauses": costs.whole.clauses,
        "whole_to_leaf_variables": (costs.whole.variables + 1)
        / (costs.leaf.variables + 1),
        "whole_to_leaf_clauses": (costs.whole.clauses + 1) / (costs.leaf.clauses + 1),
        "channels_to_whole_clauses": channels / (costs.whole.clauses + 1),
        "fresh_bits_to_whole_variables": fresh_bits / (costs.whole.variables + 1),
    }


def choose(
    widths: Sequence[int],
    bound: int,
    costs: Costs,
    cached: Sequence[bool] = (),
    *,
    orientations: Sequence[int] = ()
) -> str:
    """Depth-four policy fitted to size, propagation and search cost."""
    if (
        len(widths) <= 1
        or max(widths, default=0) <= 1
        or bound <= 0
        or bound >= sum(widths) - 1
    ):
        return LEAF
    f = features(widths, bound, costs, cached, orientations=orientations)
    if f["whole_to_leaf_clauses"] <= 0.4646734050531779:
        if f["fresh_bits_to_whole_variables"] <= 0.1669570267131243:
            if f["fresh_binary_bits"] <= 78.5:
                if f["whole_to_leaf_variables"] <= 0.47332859174964437:
                    return BINARY
                else:
                    return WHOLE
            else:
                if f["whole_to_leaf_clauses"] <= 0.14636862156555988:
                    return BINARY
                else:
                    return WHOLE
        else:
            if f["bound_fraction"] <= 0.6928571428571428:
                return WHOLE
            else:
                return BINARY
    else:
        if f["binary_bound_fraction"] <= 0.748015873015873:
            if f["negative_fraction"] <= 0.0625:
                if f["binary_inputs"] <= 38.5:
                    return BINARY
                else:
                    return WHOLE
            else:
                if f["boolean_fraction"] <= 0.8125:
                    return WHOLE
                else:
                    return BINARY
        else:
            return BINARY
