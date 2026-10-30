import pytest

from hermax.model import Model
from hermax.model._cumulative import _CumulativeEncoding
from hermax.model.expressions import PBExpr


def test_load_avoids_repeated_expression_merges(monkeypatch):
    m = Model()
    starts = [m.int(f's{i}', 0, 2) for i in range(12)]
    encoding = _CumulativeEncoding(m, list(zip(starts, [1] * 12, range(1, 13))), 100, 'time')

    def forbidden(*args, **kwargs):
        raise AssertionError('load construction repeatedly merges growing expressions')

    with monkeypatch.context() as patch:
        patch.setattr(PBExpr, '_merge', forbidden)
        load = encoding._load(1)
    for time in (0, 1, 2):
        result = m.solve(assumptions=[s == time for s in starts])
        expected = sum(range(1, 13)) if time == 1 else 0
        assert result[load] == expected


def test_empty_load_is_numeric_zero():
    m = Model()
    encoding = _CumulativeEncoding(m, [], 1, 'time')
    assert encoding._load(0) == 0
