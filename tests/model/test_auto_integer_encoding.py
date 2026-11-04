"""Automatic integer representation and its model-wide cutoff setting."""
import pytest

from hermax.model import Model


@pytest.mark.parametrize('lb,ub,expected', [(0,62,'order'), (0,63,'binary'),
                                         (-32,30,'order'), (-32,31,'binary'),
                                         (100,163,'binary'), (9,9,'order')])
def test_default_cutoff_counts_domain_values(lb, ub, expected):
    assert Model().int('x', lb, ub).encoding == expected


def test_setting_applies_to_collections_and_only_new_variables():
    m = Model()
    before = m.int('before', 0, 63)
    m.set_integer_binary_threshold(65)
    vector = m.int_vector('v', 2, 0, 63)
    matrix = m.int_matrix('a', 2, 2, 0, 64)
    assert all(x.encoding == 'order' for x in vector)
    assert all(matrix[i][j].encoding == 'binary' for i in range(2) for j in range(2))
    assert before.encoding == 'binary'
    m.set_integer_binary_threshold(None)
    assert m.int('ordered', 0, 100).encoding == 'order'
    m.set_integer_binary_threshold()
    assert m.int('reset', 0, 63).encoding == 'binary'


def test_mixed_derived_integers_follow_the_cutoff_and_keep_arithmetic():
    m = Model()
    x = m.int('x', 0, 127)
    q = m.floor_div(x, 8)
    r = m.modulo(x, 8)
    scaled = m.scale(q, 10)
    total = m.sum_var([x, q, r])
    smallest = m.min([x, q])
    assert x.encoding == scaled.encoding == total.encoding == 'binary'
    assert q.encoding == r.encoding == smallest.encoding == 'order'
    m &= x == 85
    result = m.solve()
    assert result.ok
    assert [result[v] for v in [x,q,r,scaled,total,smallest]] == [85,10,5,100,100,10]


def test_set_cardinality_uses_automatic_integer_policy():
    m = Model()
    values = m.int_set('s', lb=0, ub=63)
    count = values.card()
    assert count.encoding == 'binary'
    m &= count == 3
    result = m.solve()
    assert result.ok and result[count] == 3 and len(result[values]) == 3


def test_removed_constructor_encoding_keywords_are_rejected():
    with pytest.raises(TypeError):
        Model(integer_encoding='binary')
    with pytest.raises(TypeError):
        Model(binary_min_domain=64)
    with pytest.raises(TypeError):
        Model().int('x', 0, 100, encoding='order')
