import pytest

from hermax.model import Model
from hermax.model._cumulative import _CumulativeEncoding


@pytest.mark.parametrize("demands,capacity", [([1] * 4, 1), ([2, 3, 2, 3], 3)])
def test_exclusive_tasks_skip_time_loads_only_when_posted(monkeypatch, demands, capacity):
    def unexpected_load(*args):
        raise AssertionError("pairwise posting must not construct time loads")

    monkeypatch.setattr(_CumulativeEncoding, "_load", unexpected_load)
    m = Model()
    starts = m.int_vector("s", 4, 0, 8)
    m &= m.cumulative(starts, [2] * 4, demands, capacity)
    assert m.solve().ok


def test_posting_then_reifying_same_constraint_retains_overload_propagation():
    m = Model()
    starts = m.int_vector("s", 2, 0, 2)
    condition = m.cumulative(starts, [2, 2], [1, 1], 1)
    m &= condition
    flag = m.bool()
    m &= condition.iff(flag)
    m &= ~flag
    assert not m.solve().ok


def test_pairwise_posting_removes_redundant_circuit():
    def build(full):
        m = Model()
        starts = m.int_vector("s", 10, 0, 100)
        condition = m.cumulative(starts, [5] * 10, [1] * 10, 1)
        m &= condition._realize() if full else condition
        return m.to_cnf()

    compact, full = build(False), build(True)
    assert compact.nv < full.nv
    assert len(compact.clauses) < len(full.clauses)
