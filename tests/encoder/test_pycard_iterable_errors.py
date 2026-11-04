"""Native cardinality APIs must propagate iterable failures without retrying."""

import pytest
import hermax_pycard


def _broken():
    yield 1
    yield 2
    raise RuntimeError('input failed')


@pytest.mark.parametrize('method', ['encode_atmost', 'encode_atleast',
                                    '_encode_atmost_packed', '_encode_atleast_packed'])
def test_failed_generator_is_not_retried_or_silently_discarded(method):
    with pytest.raises(RuntimeError, match='input failed'):
        getattr(hermax_pycard, method)(_broken(), 1, 3, 8, 0)


def test_iterative_totalizer_propagates_generator_failure():
    with pytest.raises(RuntimeError, match='input failed'):
        hermax_pycard.itot_new(_broken(), 1, 3, 0)


def test_iterative_totalizer_extension_preserves_tree_on_failure():
    tree, _clauses, _rhs, top = hermax_pycard.itot_new([1, 2], 1, 3, 0)
    try:
        with pytest.raises(RuntimeError, match='input failed'):
            hermax_pycard.itot_ext(tree, _broken(), 1, top, 0)
        assert hermax_pycard.itot_inc(tree, 2, top, 0) is not None
    finally:
        hermax_pycard.itot_del(tree)


@pytest.mark.parametrize('source', [lambda: [1, -2, 3, 4], lambda: (1, -2, 3, 4),
                                    lambda: iter([1, -2, 3, 4]), lambda: (x for x in [1, -2, 3, 4])])
def test_valid_iterables_produce_the_same_encoding(source):
    expected = hermax_pycard.encode_atmost([1, -2, 3, 4], 2, 4, 8, 0)
    assert hermax_pycard.encode_atmost(source(), 2, 4, 8, 0) == expected


def test_iterator_length_hint_failure_is_propagated():
    class BrokenHint:
        def __iter__(self):
            return self
        def __next__(self):
            raise StopIteration
        def __length_hint__(self):
            raise RuntimeError('hint failed')

    with pytest.raises(RuntimeError, match='hint failed'):
        hermax_pycard.encode_atmost(BrokenHint(), 1, 3, 8, 0)
