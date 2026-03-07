from __future__ import annotations

from typing import List, Optional

import pytest

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus
from hermax.model import Model, SoftRef


class FakeIPSoft(IPAMIRSolver):
    """Minimal IPAMIR fake focused on soft-term behavior."""

    def __init__(self, formula=None):
        super().__init__()
        self.clauses: list[list[int]] = []
        self.soft_updates: list[tuple[int, int]] = []
        self.soft_map: dict[int, int] = {}
        self.soft_relaxed: list[tuple[list[int], int, int]] = []
        self._status = SolveStatus.UNKNOWN
        self._nv = int(getattr(formula, "nv", 0) if formula is not None else 0)

    def add_clause(self, clause: list[int]) -> None:
        self.clauses.append(list(clause))
        for l in clause:
            self._nv = max(self._nv, abs(int(l)))

    def set_soft(self, lit: int, weight: int) -> None:
        # IPAMIR-style semantics: set/replace by literal (not accumulation).
        self.soft_map[int(lit)] = int(weight)
        self.soft_updates.append((int(lit), int(weight)))

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), int(weight))

    def add_soft_relaxed(self, clause: list[int], weight: int, relaxation_lit: int) -> None:
        self.soft_relaxed.append((list(clause), int(weight), int(relaxation_lit)))
        self.set_soft(-int(relaxation_lit), int(weight))

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._status = SolveStatus.OPTIMUM
        return True

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        return 0

    def val(self, lit: int) -> int:
        return 1

    def get_model(self) -> Optional[List[int]]:
        return list(range(1, self._nv + 1))

    def signature(self) -> str:
        return "fake-soft"

    def close(self) -> None:
        return None

    def new_var(self) -> int:
        self._nv += 1
        return self._nv


def test_add_soft_returns_softref_single_clause():
    m = Model()
    a = m.bool("a")
    ref = m.add_soft(a, 3)
    assert isinstance(ref, SoftRef)
    assert len(ref.soft_ids) == 1


def test_add_soft_returns_grouped_ids_for_int_objective_lowering():
    m = Model()
    x = m.int("x", 0, 5)
    ref = m.add_soft(x, 2)
    assert len(ref.soft_ids) == len(x._threshold_lits)
    # grouped handle should be usable as one update target
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    before = len(s.soft_updates)
    m.update_soft_weight(ref, 9)
    assert len(s.soft_updates) >= before + len(ref.soft_ids)


def test_obj_bucket_adds_soft_entries():
    m = Model()
    a = m.bool("a")
    m.obj[4] += a
    r = m.solve()
    assert r.status in {"optimum", "interrupted_sat"}


def test_obj_bucket_repeated_add_is_additive_at_model_level():
    m = Model()
    a = m.bool("a")
    m.obj[2] += a
    m.obj[2] += a
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    # each objective addition creates its own soft registration
    assert len(s.soft_updates) == 2


def test_targeted_relaxation_for_multiclause_group_uses_single_soft_penalty():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    grp = (a | b).implies(~a | ~b)  # multi-clause group
    ref = m.add_soft(grp, 7)
    assert len(ref.soft_ids) == 1
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    # one penalty registration for the logical group
    assert len(s.soft_updates) == 1
    # and gated network appears as hard clauses in replay
    assert len(s.clauses) > 0


def test_targeted_relaxation_for_pbconstraint_uses_single_soft_penalty():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    ref = m.add_soft(a + b <= 1, 5)
    assert len(ref.soft_ids) == 1


def test_update_soft_weight_by_softref_updates_all_group_members():
    m = Model()
    x = m.int("x", 0, 5)
    ref = m.add_soft(x, 3)
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    m.update_soft_weight(ref, 9)
    # group update touches every lowered soft
    assert sum(1 for _lit, w in s.soft_updates if w == 9) >= len(ref.soft_ids)


def test_update_soft_weight_by_single_soft_id_updates_only_that_member():
    m = Model()
    x = m.int("x", 0, 5)
    ref = m.add_soft(x, 3)
    sid0, sid1 = ref.soft_ids[0], ref.soft_ids[1]
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    before = len(s.soft_updates)
    m.update_soft_weight(sid0, 8)
    # single-id update issues one set_soft call
    assert len(s.soft_updates) == before + 1
    assert s.soft_updates[-1][1] == 8


def test_update_soft_weight_by_id_list_updates_selected_members():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    ra = m.add_soft(a, 1)
    rb = m.add_soft(b, 2)
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    before = len(s.soft_updates)
    m.update_soft_weight([ra.soft_ids[0], rb.soft_ids[0]], 6)
    assert len(s.soft_updates) == before + 2
    assert s.soft_updates[-1][1] == 6


def test_update_soft_weight_unknown_id_raises():
    m = Model()
    with pytest.raises(KeyError):
        m.update_soft_weight(99999, 5)


def test_update_soft_weight_invalid_target_type_raises():
    m = Model()
    with pytest.raises(TypeError):
        m.update_soft_weight(object(), 4)


def test_update_soft_weight_rejects_nonpositive():
    m = Model()
    a = m.bool("a")
    ref = m.add_soft(a, 2)
    with pytest.raises(ValueError):
        m.update_soft_weight(ref, 0)
    with pytest.raises(ValueError):
        m.update_soft_weight(ref, -1)


def test_incremental_update_uses_set_semantics_not_accumulate_for_same_lit():
    m = Model()
    a = m.bool("a")
    ref = m.add_soft(~a, 5)
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    lit = s.soft_updates[-1][0]
    m.update_soft_weight(ref, 9)
    m.update_soft_weight(ref, 11)
    assert s.soft_map[lit] == 11
    # two updates recorded; same key overwritten in map
    assert s.soft_updates[-1] == (lit, 11)


def test_incremental_add_soft_after_bind_routes_new_soft_immediately():
    m = Model()
    a = m.bool("a")
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    before = len(s.soft_updates)
    m.add_soft(a, 4)
    assert len(s.soft_updates) == before + 1
    assert s.soft_updates[-1][1] == 4


def test_incremental_multiclause_soft_uses_relaxation_literal_mapping():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    ref = m.add_soft(a | b, 3)  # single clause OR => unit soft over clause, still one id
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    assert len(ref.soft_ids) == 1
    # Clause with 2 lits should route via relaxed form in incremental adapter.
    assert len(s.soft_relaxed) == 1


def test_prebind_weight_update_persists_and_is_used_when_binding_solver():
    m = Model()
    a = m.bool("a")
    ref = m.add_soft(~a, 2)
    m.update_soft_weight(ref, 7)  # before any backend bind
    s = FakeIPSoft()
    m.solve(backend="maxsat", solver=s)
    lit = s.soft_updates[-1][0]
    assert s.soft_map[lit] == 7


def test_sat_bound_model_rejects_soft_weight_updates():
    m = Model()
    a = m.bool("a")
    m.solve(backend="sat")
    ref = m.add_soft(a, 1)
    with pytest.raises(ValueError):
        m.update_soft_weight(ref, 2)


def test_add_soft_group_keeps_group_mapping_integrity():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    r1 = m.add_soft(a, 1)
    r2 = m.add_soft(b, 2)
    assert r1.group_id != r2.group_id
    assert len(r1.soft_ids) == 1
    assert len(r2.soft_ids) == 1
