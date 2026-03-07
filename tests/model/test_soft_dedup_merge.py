from __future__ import annotations

from hermax.model import Model
from tests.model.test_soft_behavior import FakeIPSoft


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok
    return r


def test_add_soft_duplicate_literal_accumulates_weight_and_merges_storage():
    m = Model()
    a = m.bool("a")
    r1 = m.add_soft(a, 5)
    r2 = m.add_soft(a, 10)
    assert len(m._soft) == 1
    assert m._soft[0][0] == 15
    # Both handles should point to the same physical soft id after merge.
    assert len(r1.soft_ids) == 1 and len(r2.soft_ids) == 1
    assert r1.soft_ids[0] == r2.soft_ids[0]


def test_add_soft_duplicate_clause_accumulates_weight():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.add_soft(a | b, 4)
    m.add_soft(b | a, 6)  # same clause up to literal order
    assert len(m._soft) == 1
    assert m._soft[0][0] == 10


def test_add_soft_duplicate_literal_solver_cost_matches_accumulated_weight():
    m = Model()
    a = m.bool("a")
    m &= ~a  # force violation of soft(a)
    m.add_soft(a, 5)
    m.add_soft(a, 10)
    r = _solve_ok(m)
    assert r.cost == 15


def test_add_soft_duplicate_literal_incremental_routes_as_set_update():
    m = Model()
    a = m.bool("a")
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    m.add_soft(a, 5)
    m.add_soft(a, 10)
    # same lit updated from 5 -> 15
    assert len(s.soft_updates) >= 2
    lit0, w0 = s.soft_updates[-2]
    lit1, w1 = s.soft_updates[-1]
    assert lit0 == lit1
    assert w0 == 5 and w1 == 15


def test_add_soft_and_obj_paths_are_independent_for_duplicate_literals():
    m = Model()
    a = m.bool("a")
    m.add_soft(a, 3)
    m.obj[2] += a  # additive objective path intentionally not deduped here
    # one from add_soft, one from obj bucket path
    assert len(m._soft) == 2
    assert sorted(w for w, _ in m._soft) == [2, 3]

