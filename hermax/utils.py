"""Utility algorithms used across Hermax.

Currently includes pure-Python sorting network generation helpers (Batcher's
odd-even merge sort network) and execution helpers for testing/experiments.
"""

from __future__ import annotations

from typing import Callable, Iterable, List, Sequence, Tuple, TypeVar

T = TypeVar("T")
Comparator = Tuple[int, int]


class SortingNetwork(list[Comparator]):
    """List of comparators annotated with the intended input width."""

    __slots__ = ("n",)

    def __init__(self, n: int, comps: Iterable[Comparator] = ()):  # type: ignore[override]
        super().__init__(comps)
        self.n = int(n)


class SortingNetworkLayers(list[list[Comparator]]):
    """Layered sorting network annotated with the intended input width."""

    __slots__ = ("n",)

    def __init__(self, n: int, layers: Iterable[list[Comparator]] = ()):  # type: ignore[override]
        super().__init__(layers)
        self.n = int(n)


def _next_power_of_two(n: int) -> int:
    p = 1
    while p < n:
        p <<= 1
    return p


def _odd_even_merge(lo: int, n: int, r: int, out: list[Comparator]) -> None:
    step = r * 2
    if step < n:
        _odd_even_merge(lo, n, step, out)
        _odd_even_merge(lo + r, n, step, out)
        for i in range(lo + r, lo + n - r, step):
            a, b = i, i + r
            out.append((a, b) if a < b else (b, a))
    else:
        a, b = lo, lo + r
        out.append((a, b) if a < b else (b, a))


def _odd_even_merge_sort(lo: int, n: int, out: list[Comparator]) -> None:
    if n > 1:
        m = n // 2
        _odd_even_merge_sort(lo, m, out)
        _odd_even_merge_sort(lo + m, n - m, out)
        _odd_even_merge(lo, n, 1, out)


def _greedy_layers(comparators: Sequence[Comparator]) -> list[list[Comparator]]:
    # Dependency-safe layering: preserve wire causality by placing each comparator
    # strictly after the last comparator that touched either wire.
    layers: list[list[Comparator]] = []
    if not comparators:
        return layers
    max_wire = max(max(i, j) for i, j in comparators)
    last_layer_for_wire = [-1] * (max_wire + 1)
    for i, j in comparators:
        layer_idx = max(last_layer_for_wire[i], last_layer_for_wire[j]) + 1
        while len(layers) <= layer_idx:
            layers.append([])
        layers[layer_idx].append((i, j))
        last_layer_for_wire[i] = layer_idx
        last_layer_for_wire[j] = layer_idx
    return layers


def batcher_odd_even_sorting_network(n: int) -> SortingNetwork:
    """Return a Batcher odd-even merge sorting network for width ``n``.

    Supports arbitrary ``n >= 1`` by generating the next power-of-two network and
    pruning comparators that touch padded wires.
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError("n must be a positive integer")
    if n == 1:
        return SortingNetwork(1, [])
    p = _next_power_of_two(n)
    comps: list[Comparator] = []
    _odd_even_merge_sort(0, p, comps)
    # Prune comparators touching padded wires and preserve first occurrence order.
    pruned = [(i, j) for (i, j) in comps if i < n and j < n and i != j]
    return SortingNetwork(n, pruned)


def batcher_odd_even_sorting_network_layers(n: int) -> SortingNetworkLayers:
    """Return a layered Batcher odd-even sorting network for width ``n``."""
    net = batcher_odd_even_sorting_network(n)
    return SortingNetworkLayers(n, _greedy_layers(net))


def batcher_odd_even_unary_add_network(n_left: int, n_right: int) -> SortingNetwork:
    """Return a compare-swap network for unary addition via sorting/merging.

    Inputs are interpreted as two *already sorted* unary vectors with widths
    ``n_left`` and ``n_right``. The output width is ``n_left + n_right`` and
    contains the sorted concatenation of both inputs.

    Uses conceptual padding to ``p2 = next_power_of_two(max(n_left, n_right))``
    and generates a single odd-even merge network over width ``2*p2``. This
    preserves the merge topology for unequal sizes.
    """
    if not isinstance(n_left, int) or not isinstance(n_right, int):
        raise ValueError("n_left and n_right must be non-negative integers")
    if n_left < 0 or n_right < 0:
        raise ValueError("n_left and n_right must be non-negative integers")

    total = n_left + n_right
    if total == 0:
        return SortingNetwork(0, [])
    if n_left == 0 or n_right == 0:
        # One side is empty: concatenation is already sorted unary.
        return SortingNetwork(total, [])

    p2 = _next_power_of_two(max(n_left, n_right))
    width = 2 * p2
    comps: list[Comparator] = []
    _odd_even_merge(0, width, 1, comps)
    pruned = [(i, j) for (i, j) in comps if 0 <= i < j < width]
    return SortingNetwork(width, pruned)


def batcher_odd_even_unary_add_network_layers(n_left: int, n_right: int) -> SortingNetworkLayers:
    """Return layered representation of :func:`batcher_odd_even_unary_add_network`."""
    net = batcher_odd_even_unary_add_network(n_left, n_right)
    return SortingNetworkLayers(net.n, _greedy_layers(net))


def apply_unary_add_network(
    left: Sequence[int | bool],
    right: Sequence[int | bool],
    network: Sequence[Comparator] | None = None,
) -> list[int]:
    """Apply a unary-add compare-swap network to two unary sorted vectors.

    The returned list has length ``len(left) + len(right)`` and is sorted
    ascending (all ``0`` first, then ``1``), matching
    ``sorted(left + right)``.
    """
    vals_left: list[int] = []
    vals_right: list[int] = []
    for x in left:
        if x not in (0, 1, False, True):
            raise ValueError("Unary inputs must contain only 0/1 values.")
        vals_left.append(1 if bool(x) else 0)
    for x in right:
        if x not in (0, 1, False, True):
            raise ValueError("Unary inputs must contain only 0/1 values.")
        vals_right.append(1 if bool(x) else 0)

    def _is_non_decreasing(xs: Sequence[int]) -> bool:
        return all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1))

    if not _is_non_decreasing(vals_left) or not _is_non_decreasing(vals_right):
        raise ValueError("Unary inputs must be sorted in non-decreasing (ascending) order.")

    nl = len(vals_left)
    nr = len(vals_right)
    total = nl + nr
    if total == 0:
        return []

    net = network if network is not None else batcher_odd_even_unary_add_network(nl, nr)
    width = _network_width(net, explicit_n=getattr(net, "n", None))

    if width == total:
        out_direct = apply_sorting_network([*vals_left, *vals_right], net)
        return [int(v) for v in out_direct]

    p2 = _next_power_of_two(max(nl, nr))
    expected_width = 2 * p2
    if width != expected_width:
        raise ValueError(
            f"Network width {width} is incompatible with unary-add padded width {expected_width} for lengths ({nl}, {nr})."
        )

    # Keep each half individually sorted (ascending) as required by merge.
    padded = [*([0] * (p2 - nl)), *vals_left, *([0] * (p2 - nr)), *vals_right]
    out = apply_sorting_network(padded, net)
    return [int(v) for v in out[-total:]]


def _network_width(network: Sequence[Comparator], explicit_n: int | None = None) -> int:
    if explicit_n is not None:
        return explicit_n
    n_attr = getattr(network, "n", None)
    if isinstance(n_attr, int):
        return n_attr
    if not network:
        return 0
    return max(max(i, j) for i, j in network) + 1


def apply_sorting_network(values: Sequence[T], network: Sequence[Comparator], *, key: Callable[[T], object] | None = None) -> list[T]:
    """Apply a compare-swap network to a sequence and return a sorted copy."""
    out = list(values)
    n = _network_width(network)
    if len(out) != n:
        raise ValueError(f"Input length {len(out)} does not match network width {n}")
    key_fn = (lambda x: x) if key is None else key
    for i, j in network:
        if key_fn(out[j]) < key_fn(out[i]):
            out[i], out[j] = out[j], out[i]
    return out


def apply_sorting_network_layers(
    values: Sequence[T],
    layers: Sequence[Sequence[Comparator]],
    *,
    key: Callable[[T], object] | None = None,
) -> list[T]:
    """Apply a layered compare-swap network and return a sorted copy."""
    out = list(values)
    n = _network_width(layers, explicit_n=getattr(layers, "n", None))
    if len(out) != n:
        raise ValueError(f"Input length {len(out)} does not match network width {n}")
    key_fn = (lambda x: x) if key is None else key
    for layer in layers:
        for i, j in layer:
            if key_fn(out[j]) < key_fn(out[i]):
                out[i], out[j] = out[j], out[i]
    return out


__all__ = [
    "Comparator",
    "SortingNetwork",
    "SortingNetworkLayers",
    "batcher_odd_even_sorting_network",
    "batcher_odd_even_sorting_network_layers",
    "batcher_odd_even_unary_add_network",
    "batcher_odd_even_unary_add_network_layers",
    "apply_sorting_network",
    "apply_sorting_network_layers",
    "apply_unary_add_network",
]
