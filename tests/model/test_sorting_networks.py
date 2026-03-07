import itertools
import random

import pytest

from hermax.utils import (
    apply_sorting_network,
    apply_sorting_network_layers,
    batcher_odd_even_sorting_network,
    batcher_odd_even_sorting_network_layers,
)


def _assert_sorted(xs):
    assert all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1))


def _exhaustive_boolean_inputs(n):
    for bits in itertools.product([0, 1], repeat=n):
        yield list(bits)


def test_network_invalid_n_raises():
    with pytest.raises(ValueError):
        batcher_odd_even_sorting_network(0)
    with pytest.raises(ValueError):
        batcher_odd_even_sorting_network(-3)


def test_layers_invalid_n_raises():
    with pytest.raises(ValueError):
        batcher_odd_even_sorting_network_layers(0)


def test_n1_network_is_empty():
    assert batcher_odd_even_sorting_network(1) == []
    assert batcher_odd_even_sorting_network_layers(1) == []


def test_n2_network_single_comparator():
    assert batcher_odd_even_sorting_network(2) == [(0, 1)]


def test_comparators_are_normalized_and_in_range():
    for n in range(2, 17):
        net = batcher_odd_even_sorting_network(n)
        for i, j in net:
            assert isinstance(i, int) and isinstance(j, int)
            assert 0 <= i < j < n


def test_network_is_deterministic():
    assert batcher_odd_even_sorting_network(13) == batcher_odd_even_sorting_network(13)
    assert batcher_odd_even_sorting_network_layers(13) == batcher_odd_even_sorting_network_layers(13)


def test_layers_have_no_wire_conflicts():
    for n in range(2, 20):
        for layer in batcher_odd_even_sorting_network_layers(n):
            used = set()
            for i, j in layer:
                assert i not in used
                assert j not in used
                used.add(i)
                used.add(j)


def test_flattened_layers_is_valid_topological_reordering():
    rng = random.Random(909)
    for n in range(2, 20):
        layers = batcher_odd_even_sorting_network_layers(n)
        flat = [c for layer in layers for c in layer]
        assert len(flat) == len(batcher_odd_even_sorting_network(n))
        for _ in range(10):
            xs = [rng.randrange(-30, 31) for _ in range(n)]
            assert apply_sorting_network(xs, flat) == apply_sorting_network(xs, batcher_odd_even_sorting_network(n))


def test_apply_network_does_not_mutate_input():
    xs = [3, 1, 2]
    net = batcher_odd_even_sorting_network(3)
    out = apply_sorting_network(xs, net)
    assert xs == [3, 1, 2]
    assert out == [1, 2, 3]


def test_apply_layers_does_not_mutate_input():
    xs = [5, 2, 4, 1]
    layers = batcher_odd_even_sorting_network_layers(4)
    out = apply_sorting_network_layers(xs, layers)
    assert xs == [5, 2, 4, 1]
    assert out == [1, 2, 4, 5]


def test_apply_network_matches_python_sorted_on_random_integers():
    rng = random.Random(1337)
    for n in range(2, 18):
        net = batcher_odd_even_sorting_network(n)
        for _ in range(20):
            xs = [rng.randrange(-50, 51) for _ in range(n)]
            assert apply_sorting_network(xs, net) == sorted(xs)


def test_apply_layers_matches_python_sorted_on_random_integers():
    rng = random.Random(2024)
    for n in range(2, 18):
        layers = batcher_odd_even_sorting_network_layers(n)
        for _ in range(10):
            xs = [rng.randrange(-20, 21) for _ in range(n)]
            assert apply_sorting_network_layers(xs, layers) == sorted(xs)


def test_boolean_exhaustive_n3():
    net = batcher_odd_even_sorting_network(3)
    for xs in _exhaustive_boolean_inputs(3):
        out = apply_sorting_network(xs, net)
        _assert_sorted(out)
        assert out == sorted(xs)


def test_boolean_exhaustive_n4():
    net = batcher_odd_even_sorting_network(4)
    for xs in _exhaustive_boolean_inputs(4):
        out = apply_sorting_network(xs, net)
        assert out == sorted(xs)


def test_boolean_exhaustive_n5_non_power_of_two():
    net = batcher_odd_even_sorting_network(5)
    for xs in _exhaustive_boolean_inputs(5):
        out = apply_sorting_network(xs, net)
        assert out == sorted(xs)


def test_boolean_exhaustive_n7_non_power_of_two():
    net = batcher_odd_even_sorting_network(7)
    for xs in _exhaustive_boolean_inputs(7):
        out = apply_sorting_network(xs, net)
        assert out == sorted(xs)


def test_key_function_support():
    xs = ["bbb", "a", "cc"]
    net = batcher_odd_even_sorting_network(len(xs))
    assert apply_sorting_network(xs, net, key=len) == ["a", "cc", "bbb"]


def test_network_size_nondecreasing_with_n():
    sizes = [len(batcher_odd_even_sorting_network(n)) for n in range(1, 17)]
    assert all(sizes[i] <= sizes[i + 1] for i in range(len(sizes) - 1))


def test_depth_nondecreasing_for_powers_of_two():
    depths = [len(batcher_odd_even_sorting_network_layers(2**k)) for k in range(0, 7)]
    assert all(depths[i] <= depths[i + 1] for i in range(len(depths) - 1))


def test_non_power_of_two_network_uses_no_out_of_range_comparators():
    for n in [3, 5, 6, 7, 9, 10, 13, 15]:
        for i, j in batcher_odd_even_sorting_network(n):
            assert i < n and j < n


def test_apply_network_length_mismatch_raises():
    net = batcher_odd_even_sorting_network(4)
    with pytest.raises(ValueError):
        apply_sorting_network([1, 2, 3], net)


def test_apply_layers_length_mismatch_raises():
    layers = batcher_odd_even_sorting_network_layers(4)
    with pytest.raises(ValueError):
        apply_sorting_network_layers([1, 2, 3], layers)


def test_apply_layers_matches_apply_network_for_random_cases():
    rng = random.Random(77)
    for n in range(2, 15):
        net = batcher_odd_even_sorting_network(n)
        layers = batcher_odd_even_sorting_network_layers(n)
        for _ in range(15):
            xs = [rng.randrange(100) for _ in range(n)]
            assert apply_sorting_network(xs, net) == apply_sorting_network_layers(xs, layers)
