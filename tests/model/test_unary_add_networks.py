import itertools
import random

import pytest

from hermax.utils import (
    apply_sorting_network,
    apply_unary_add_network,
    batcher_odd_even_sorting_network,
    batcher_odd_even_unary_add_network,
    batcher_odd_even_unary_add_network_layers,
)


def _unary(k: int, n: int) -> list[int]:
    return [0] * (n - k) + [1] * k


def test_unary_add_network_invalid_sizes_raise():
    with pytest.raises(ValueError):
        batcher_odd_even_unary_add_network(-1, 2)
    with pytest.raises(ValueError):
        batcher_odd_even_unary_add_network(2, -1)


def test_unary_add_network_fast_path_width_and_range():
    net = batcher_odd_even_unary_add_network(4, 4)
    assert getattr(net, "n", None) == 8
    for i, j in net:
        assert isinstance(i, int) and isinstance(j, int)
        assert 0 <= i < j < 8


def test_unary_add_network_fast_path_uses_fewer_comparators_than_full_sort():
    for n in [2, 4, 8, 16]:
        fast = batcher_odd_even_unary_add_network(n, n)
        full = batcher_odd_even_sorting_network(2 * n)
        assert len(fast) < len(full)


def test_unary_add_network_uses_padded_merge_width_for_unequal_sizes():
    # max(1200,500)=1200 -> p2=2048 -> padded merge width = 4096
    net = batcher_odd_even_unary_add_network(1200, 500)
    assert getattr(net, "n", None) == 4096


def test_unary_add_network_unequal_sizes_beats_full_sort_total():
    for nl, nr in [(1200, 500), (200, 60), (45, 11)]:
        net = batcher_odd_even_unary_add_network(nl, nr)
        full = batcher_odd_even_sorting_network(nl + nr)
        assert len(net) < len(full)


def test_unary_add_network_skewed_sizes_correctness_only():
    # Highly skewed pairs are valid even when comparator-count dominance
    # over exact-size full sort is not guaranteed.
    for nl, nr in [(65, 1), (1200, 1)]:
        net = batcher_odd_even_unary_add_network(nl, nr)
        for a in [0, nl // 2, nl]:
            for b in [0, nr]:
                left = _unary(a, nl)
                right = _unary(b, nr)
                out = apply_unary_add_network(left, right, net)
                assert out == sorted(left + right)
                assert sum(out) == a + b


def test_unary_add_network_tradeoff_padded_merge_can_be_larger():
    # Documented tradeoff: power-of-two padding may over-shoot for small
    # highly skewed shapes.
    nl, nr = 65, 1
    net = batcher_odd_even_unary_add_network(nl, nr)
    full = batcher_odd_even_sorting_network(nl + nr)
    assert len(net) > len(full)


def test_unary_add_network_correct_on_exhaustive_small_equal_power2():
    for n in [1, 2, 4]:
        net = batcher_odd_even_unary_add_network(n, n)
        for a in range(n + 1):
            for b in range(n + 1):
                xs = _unary(a, n) + _unary(b, n)
                out = apply_sorting_network(xs, net)
                assert out == sorted(xs)


def test_apply_unary_add_network_helper_matches_sorted_concat():
    rng = random.Random(1337)
    for n in [2, 4, 8]:
        for _ in range(20):
            a = rng.randrange(n + 1)
            b = rng.randrange(n + 1)
            left = _unary(a, n)
            right = _unary(b, n)
            out = apply_unary_add_network(left, right)
            assert out == sorted(left + right)
            assert sum(out) == a + b


def test_apply_unary_add_network_helper_matches_sorted_concat_unequal_sizes():
    rng = random.Random(4242)
    for nl, nr in [(3, 2), (5, 3), (9, 4)]:
        for _ in range(40):
            a = rng.randrange(nl + 1)
            b = rng.randrange(nr + 1)
            left = _unary(a, nl)
            right = _unary(b, nr)
            out = apply_unary_add_network(left, right)
            assert out == sorted(left + right)
            assert sum(out) == a + b


def test_apply_unary_add_network_rejects_non_binary_values():
    with pytest.raises(ValueError):
        apply_unary_add_network([0, 1, 2], [0, 1])


def test_unary_add_layers_have_no_wire_conflicts():
    layers = batcher_odd_even_unary_add_network_layers(8, 8)
    for layer in layers:
        used = set()
        for i, j in layer:
            assert i not in used and j not in used
            used.add(i)
            used.add(j)


def test_unary_add_layers_match_flat_network_behavior():
    rng = random.Random(2025)
    nl, nr = 8, 8
    net = batcher_odd_even_unary_add_network(nl, nr)
    layers = batcher_odd_even_unary_add_network_layers(nl, nr)
    flat_from_layers = [c for layer in layers for c in layer]
    for _ in range(50):
        a = rng.randrange(nl + 1)
        b = rng.randrange(nr + 1)
        xs = _unary(a, nl) + _unary(b, nr)
        assert apply_unary_add_network(xs[:nl], xs[nl:], net) == apply_unary_add_network(xs[:nl], xs[nl:], flat_from_layers)


def test_unary_add_network_deterministic():
    assert batcher_odd_even_unary_add_network(8, 8) == batcher_odd_even_unary_add_network(8, 8)


def test_unary_add_exhaustive_boolean_sequences_with_pre_sorted_halves():
    nl, nr = 3, 3
    net = batcher_odd_even_unary_add_network(nl, nr)
    lefts = [_unary(k, nl) for k in range(nl + 1)]
    rights = [_unary(k, nr) for k in range(nr + 1)]
    for l, r in itertools.product(lefts, rights):
        out = apply_unary_add_network(l, r, net)
        assert out == sorted(l + r)


def test_apply_unary_add_network_with_incompatible_network_width_raises():
    left = _unary(1, 2)
    right = _unary(1, 2)
    wrong = batcher_odd_even_sorting_network(8)
    with pytest.raises(ValueError):
        apply_unary_add_network(left, right, wrong)


def test_apply_unary_rejects_unsorted_descending_inputs():
    with pytest.raises(ValueError, match="sorted in non-decreasing"):
        apply_unary_add_network([1, 0], [0, 1])


def test_unary_add_handles_zero_width_domains():
    net = batcher_odd_even_unary_add_network(0, 5)
    assert getattr(net, "n", None) == 5
    out = apply_unary_add_network([], _unary(3, 5), net)
    assert out == _unary(3, 5)

    net2 = batcher_odd_even_unary_add_network(4, 0)
    assert getattr(net2, "n", None) == 4
    out2 = apply_unary_add_network(_unary(2, 4), [], net2)
    assert out2 == _unary(2, 4)


def test_apply_unary_accepts_exact_size_custom_network():
    nl, nr = 3, 2
    custom = batcher_odd_even_sorting_network(nl + nr)
    out = apply_unary_add_network(_unary(2, nl), _unary(1, nr), custom)
    assert out == sorted(_unary(2, nl) + _unary(1, nr))


def test_apply_unary_add_network_large_scale():
    nl, nr = 1200, 500
    left = _unary(777, nl)
    right = _unary(211, nr)
    out = apply_unary_add_network(left, right)
    assert len(out) == nl + nr
    assert out == sorted(left + right)
    assert sum(out) == 988
