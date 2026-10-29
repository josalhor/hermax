import pytest
from hermax.model import Model


@pytest.mark.parametrize('values', [(3,), (0, 0), (3, -3), (-7, 2)])
def test_fixed_inputs_share_thresholds_without_clauses(values):
    m = Model()
    x = m.int('x', -2, 8)
    fixed = [m.int(f'c{i}', v, v) for i, v in enumerate(values)]
    before = len(m.to_cnf().clauses)
    out = m.sum_var([x, *fixed])
    assert (out.lb, out.ub) == (x.lb + sum(values), x.ub + sum(values))
    assert len(m.to_cnf().clauses) == before
    for v in range(x.lb, x.ub + 1):
        result = m.solve(assumptions=[x == v])
        assert result[out] == v + sum(values)


@pytest.mark.parametrize('name', [None, 'total'])
def test_all_fixed_sum_and_multiple_varying_inputs(name):
    m = Model()
    a = m.int('a', 3, 3)
    b = m.int('b', -5, -5)
    out = m.sum_var([a, b], name=name)
    assert out.lb == out.ub == -2
    x, y = m.int('x', 0, 2), m.int('y', -1, 1)
    total = m.sum_var([x, a, y, b])
    for xv in range(3):
        for yv in range(-1, 2):
            r = m.solve(assumptions=[x == xv, y == yv])
            assert r[total] == xv + yv - 2


def test_fixed_merges_preserve_step_names_and_add_no_clauses():
    m = Model()
    x = m.int('x', 0, 100)
    a, b = m.int('a', 3, 3), m.int('b', -3, -3)
    before = len(m.to_cnf().clauses)
    total = m.sum_var([x, a, b], name='total')
    assert total.name == 'total_step1'
    assert (total.lb, total.ub) == (0, 100)
    assert len(m.to_cnf().clauses) == before
