import operator

import pytest

from hermax.model import Model


COMPARISONS = [
    (operator.eq, True), (operator.ne, False),
    (operator.le, True), (operator.ge, True),
    (operator.lt, False), (operator.gt, False),
]


@pytest.mark.parametrize("compare,expected", COMPARISONS)
def test_integer_self_comparisons_do_not_expand_the_domain(compare, expected):
    m = Model()
    x = m.int("x", -100, 100)
    before = len(m._hard)
    m &= compare(x, x)
    assert len(m._hard) - before == (0 if expected else 1)
    assert m.solve().ok is expected


@pytest.mark.parametrize("compare,expected", COMPARISONS)
def test_constant_self_comparisons_reify_correctly(compare, expected):
    m = Model()
    x = m.int("x", -2, 2)
    flag = m.bool("flag")
    m &= compare(x, x).iff(flag)
    assert m.solve(assumptions=[flag if expected else ~flag]).ok
    assert not m.solve(assumptions=[~flag if expected else flag]).ok


@pytest.mark.parametrize("compare,_", COMPARISONS)
def test_offset_views_of_one_integer_compare_as_constants(compare, _):
    m = Model()
    task = m.interval("job", start=-100, duration=3, end=103)
    expected = compare(0, 3)
    before = len(m._hard)
    m &= compare(task.start, task.end)
    assert len(m._hard) - before == (0 if expected else 1)
    assert m.solve().ok is expected
