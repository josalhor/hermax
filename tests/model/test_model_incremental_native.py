from __future__ import annotations

from typing import Optional, List

import pytest

from hermax.model import Model, SoftRef
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus


class FakeIPSolver(IPAMIRSolver):
    """Minimal IPAMIR-compatible fake for routing tests."""

    def __init__(self, formula=None):
        super().__init__()
        self.clauses: list[list[int]] = []
        self.soft_updates: list[tuple[int, int]] = []
        self.soft_relaxed: list[tuple[list[int], int, int]] = []
        self.soft_map: dict[int, int] = {}
        self._status = SolveStatus.UNKNOWN
        self._nv = 0
        self.last_assumptions: list[int] = []
        self.last_raise_on_abnormal = False
        if formula is not None:
            self._nv = max(self._nv, int(getattr(formula, "nv", 0)))

    def add_clause(self, clause: list[int]) -> None:
        self.clauses.append(list(clause))
        for l in clause:
            self._nv = max(self._nv, abs(int(l)))

    def set_soft(self, lit: int, weight: int) -> None:
        self.soft_map[int(lit)] = int(weight)
        self.soft_updates.append((int(lit), int(weight)))

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), int(weight))

    def add_soft_relaxed(self, clause: list[int], weight: int, relaxation_lit: int) -> None:
        self.soft_relaxed.append((list(clause), int(weight), int(relaxation_lit)))
        self.set_soft(-int(relaxation_lit), int(weight))

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self.last_assumptions = list(assumptions or [])
        self.last_raise_on_abnormal = bool(raise_on_abnormal)
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
        return "fakeip"

    def close(self) -> None:
        return None

    def new_var(self) -> int:
        self._nv += 1
        return self._nv


def test_incremental_sat_assumptions_and_streamed_hard_updates():
    m = Model()
    a = m.bool("a")

    r1 = m.solve(incremental=True, backend="auto", assumptions=[a.id])
    assert r1.ok

    # Add hard clause after first solve; should be routed to bound SAT backend.
    m &= ~a

    r2 = m.solve(incremental=True, backend="auto", assumptions=[a.id])
    assert r2.status == "unsat"


def test_incremental_sat_lock_upgrades_backend_by_default():
    m = Model()
    a = m.bool("a")
    m.solve(incremental=True, backend="auto")
    assert m._inc_state.mode == "sat"

    m.solve(incremental=True, backend="maxsat", solver=FakeIPSolver)
    assert m._inc_state.mode == "maxsat"


def test_incremental_sat_lock_can_reject_backend_change_in_strict_mode():
    m = Model()
    a = m.bool("a")
    m.solve(incremental=True, backend="auto")
    with pytest.raises(ValueError):
        m.solve(incremental=True, backend="maxsat", solver=FakeIPSolver, sat_upgrade="error")


def test_incremental_maxsat_routes_updates_realtime_and_keeps_solver_instance():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a | b)
    m.obj[3] += ~a

    s = FakeIPSolver()
    r1 = m.solve(incremental=True, backend="maxsat", solver=s)
    assert r1.ok
    hard0 = len(s.clauses)
    soft0 = len(s.soft_updates)

    # Realtime routing after lock.
    m &= (~b)
    m.obj[2] += b

    r2 = m.solve(incremental=True, backend="maxsat")
    assert r2.ok
    assert len(s.clauses) > hard0
    assert len(s.soft_updates) > soft0


def test_incremental_maxsat_update_soft_weight_tracked_id_calls_set_soft():
    m = Model()
    a = m.bool("a")
    ref = m.add_soft(~a, 5)
    assert isinstance(ref, SoftRef)

    s = FakeIPSolver()
    m.solve(incremental=True, backend="maxsat", solver=s)
    before = len(s.soft_updates)

    m.update_soft_weight(ref, 9)

    assert len(s.soft_updates) == before + 1
    assert any(w == 9 for _lit, w in s.soft_updates)


def test_incremental_sat_to_maxsat_after_bind_upgrades_by_default():
    m = Model()
    a = m.bool("a")

    m.solve(incremental=True, backend="auto")  # bind SAT
    m.obj[4] += ~a

    m.solve(incremental=True, backend="auto", solver=FakeIPSolver)
    assert m._inc_state.mode == "maxsat"


def test_incremental_sat_to_maxsat_after_bind_can_fail_in_strict_mode():
    m = Model()
    a = m.bool("a")
    m.solve(incremental=True, backend="auto")  # bind SAT
    m.obj[4] += ~a
    with pytest.raises(ValueError):
        m.solve(incremental=True, backend="auto", solver=FakeIPSolver, sat_upgrade="error")


def test_incremental_invalid_backend_raises():
    m = Model()
    m.bool("a")
    with pytest.raises(ValueError):
        m.solve(incremental=True, backend="weird")


def test_incremental_maxsat_without_solver_uses_default_rc2():
    m = Model()
    a = m.bool("a")
    m.add_soft(a, 1)
    r = m.solve(incremental=True, backend="maxsat", solver=None)
    assert r.status in {"optimum", "sat", "unsat", "unknown", "interrupted", "interrupted_sat"}
    assert m._inc_state.mode == "maxsat"


def test_incremental_solver_factory_must_return_ipamir():
    m = Model()
    a = m.bool("a")
    m.add_soft(a, 1)

    def _bad_factory(*args, **kwargs):
        return object()

    with pytest.raises(TypeError):
        m.solve(incremental=True, backend="maxsat", solver=_bad_factory)


def test_incremental_backend_switch_maxsat_to_sat_rejected():
    m = Model()
    a = m.bool("a")
    m.add_soft(a, 1)
    m.solve(incremental=True, backend="maxsat", solver=FakeIPSolver)
    with pytest.raises(ValueError):
        m.solve(incremental=True, backend="sat")


def test_incremental_backend_switch_sat_to_maxsat_without_soft_upgrades_by_default():
    m = Model()
    m.bool("a")
    m.solve(incremental=True, backend="sat")
    m.solve(incremental=True, backend="maxsat", solver=FakeIPSolver)
    assert m._inc_state.mode == "maxsat"


def test_incremental_backend_switch_sat_to_maxsat_without_soft_can_fail_in_strict_mode():
    m = Model()
    m.bool("a")
    m.solve(incremental=True, backend="sat")
    with pytest.raises(ValueError):
        m.solve(incremental=True, backend="maxsat", solver=FakeIPSolver, sat_upgrade="error")


def test_incremental_sat_backend_rejected_when_soft_exists():
    m = Model()
    a = m.bool("a")
    m.add_soft(a, 1)
    with pytest.raises(ValueError):
        m.solve(incremental=True, backend="sat")


def test_incremental_bound_mode_persists_even_without_flag():
    m = Model()
    a = m.bool("a")
    m.solve(incremental=True, backend="sat")
    assert m._inc_state.mode == "sat"
    m &= ~a
    r = m.solve(assumptions=[a.id])
    assert r.status == "unsat"


def test_close_incremental_unbinds_and_allows_rebind():
    m = Model()
    a = m.bool("a")
    m.solve(incremental=True, backend="sat")
    assert m._inc_state.mode == "sat"
    m.close_incremental()
    assert m._inc_state.mode is None
    m.add_soft(a, 1)
    m.solve(incremental=True, backend="maxsat", solver=FakeIPSolver)
    assert m._inc_state.mode == "maxsat"


def test_incremental_maxsat_assumptions_and_raise_on_abnormal_passthrough():
    m = Model()
    a = m.bool("a")
    m.add_soft(~a, 1)
    s = FakeIPSolver()
    m.solve(incremental=True, backend="maxsat", solver=s, assumptions=[a.id], raise_on_abnormal=True)
    assert s.last_assumptions == [a.id]
    assert s.last_raise_on_abnormal is True


def test_incremental_soft_update_unknown_id_raises():
    m = Model()
    with pytest.raises(KeyError):
        m.update_soft_weight(9999, 3)


def test_incremental_soft_update_while_sat_bound_raises():
    m = Model()
    a = m.bool("a")
    m.solve(incremental=True, backend="sat")
    ref = m.add_soft(~a, 2)
    with pytest.raises(ValueError):
        m.update_soft_weight(ref, 5)


def test_incremental_routes_preexisting_soft_when_binding_maxsat():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    ref1 = m.add_soft(a, 2)
    ref2 = m.add_soft(a | b, 4)
    s = FakeIPSolver()
    m.solve(incremental=True, backend="maxsat", solver=s)
    assert ref1.group_id in m._soft_group_to_ids
    assert ref2.group_id in m._soft_group_to_ids
    assert len(s.soft_updates) >= 2
    assert len(s.soft_relaxed) >= 1


def test_incremental_routes_new_soft_after_maxsat_bind():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    s = FakeIPSolver()
    m.solve(incremental=True, backend="maxsat", solver=s)
    before_soft = len(s.soft_updates)
    m.add_soft(a | b, 7)
    assert len(s.soft_updates) == before_soft + 1
    assert s.soft_updates[-1][1] == 7


def test_incremental_update_soft_weight_after_relaxed_mapping():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    ref = m.add_soft(a | b, 6)
    s = FakeIPSolver()
    m.solve(incremental=True, backend="maxsat", solver=s)
    m.update_soft_weight(ref, 11)
    assert s.soft_updates[-1][1] == 11


def test_incremental_sat_assumptions_empty_defaults_ok():
    m = Model()
    a = m.bool("a")
    m &= a
    r = m.solve(incremental=True, backend="sat")
    assert r.ok


@pytest.mark.parametrize("backend", ["auto", "sat"])
def test_incremental_sat_backends_bind_sat_mode(backend):
    m = Model()
    m.bool("a")
    m.solve(incremental=True, backend=backend)
    assert m._inc_state.mode == "sat"


@pytest.mark.parametrize("backend", ["auto", "maxsat"])
def test_incremental_soft_model_binds_maxsat_mode(backend):
    m = Model()
    a = m.bool("a")
    m.add_soft(a, 1)
    m.solve(incremental=True, backend=backend, solver=FakeIPSolver)
    assert m._inc_state.mode == "maxsat"


def test_incremental_default_is_on_without_passing_incremental_flag():
    m = Model()
    m.bool("a")
    m.solve(backend="auto")
    assert m._inc_state.mode == "sat"


def test_assumptions_accept_literals_and_terms_in_sat_mode():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a | b)
    r = m.solve(assumptions=[~a, 1 * b])
    assert r.ok


def test_assumptions_accept_terms_in_maxsat_mode_and_are_forwarded():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.add_soft(a | b, 2)
    s = FakeIPSolver()
    m.solve(backend="maxsat", solver=s, assumptions=[1 * a, -1 * b])
    assert s.last_assumptions == [a.id, -b.id]


def test_assumption_term_requires_unit_coefficient():
    m = Model()
    a = m.bool("a")
    with pytest.raises(TypeError):
        m.solve(assumptions=[2 * a])


def test_assumption_zero_int_rejected():
    m = Model()
    m.bool("a")
    with pytest.raises(ValueError):
        m.solve(assumptions=[0])


def test_assumption_bool_rejected():
    m = Model()
    m.bool("a")
    with pytest.raises(TypeError):
        m.solve(assumptions=[True])


def test_assumption_cross_model_literal_rejected():
    m1 = Model()
    m2 = Model()
    a1 = m1.bool("a")
    m2.bool("b")
    with pytest.raises(ValueError):
        m2.solve(assumptions=[a1])


def test_update_soft_weight_by_group_id_updates_all_members():
    m = Model()
    x = m.int("x", 0, 4)
    ref = m.add_soft(x, 3)  # expands into multiple soft clauses
    assert len(ref.soft_ids) > 1
    m.update_soft_weight(ref, 9)
    for sid in ref.soft_ids:
        idx = m._soft_id_to_index[sid]
        assert m._soft[idx][0] == 9


def test_update_soft_weight_by_soft_id_updates_single_member_only():
    m = Model()
    x = m.int("x", 0, 4)
    ref = m.add_soft(x, 3)
    sid0 = ref.soft_ids[0]
    sid1 = ref.soft_ids[1]
    m.update_soft_weight(sid0, 8)
    assert m._soft[m._soft_id_to_index[sid0]][0] == 8
    assert m._soft[m._soft_id_to_index[sid1]][0] == 3


def test_update_soft_weight_by_sequence_of_soft_ids():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    ra = m.add_soft(a, 1)
    rb = m.add_soft(b, 2)
    m.update_soft_weight([ra.soft_ids[0], rb.soft_ids[0]], 7)
    assert m._soft[m._soft_id_to_index[ra.soft_ids[0]]][0] == 7
    assert m._soft[m._soft_id_to_index[rb.soft_ids[0]]][0] == 7


def test_update_soft_weight_unknown_soft_id_raises():
    m = Model()
    with pytest.raises(KeyError):
        m.update_soft_weight(123456, 2)


def test_update_soft_weight_invalid_target_type_raises():
    m = Model()
    with pytest.raises(TypeError):
        m.update_soft_weight(object(), 2)


def test_update_soft_weight_rejects_non_positive_values():
    m = Model()
    a = m.bool("a")
    ref = m.add_soft(a, 1)
    with pytest.raises(ValueError):
        m.update_soft_weight(ref, 0)
    with pytest.raises(ValueError):
        m.update_soft_weight(ref, -1)


def test_incremental_bound_sat_upgrades_when_soft_added_even_with_backend_sat():
    m = Model()
    a = m.bool("a")
    m.solve(backend="sat")
    m.add_soft(a, 1)
    m.solve(backend="sat")
    assert m._inc_state.mode == "maxsat"


def test_incremental_bound_sat_can_fail_on_upgrade_in_strict_mode():
    m = Model()
    a = m.bool("a")
    m.solve(backend="sat")
    m.add_soft(a, 1)
    with pytest.raises(ValueError):
        m.solve(backend="sat", sat_upgrade="error")


def test_incremental_maxsat_soft_weight_group_update_pushes_all_to_solver():
    m = Model()
    x = m.int("x", 0, 5)
    ref = m.add_soft(x, 2)
    s = FakeIPSolver()
    m.solve(backend="maxsat", solver=s)
    before = len(s.soft_updates)
    m.update_soft_weight(ref, 11)
    assert len(s.soft_updates) >= before + len(ref.soft_ids)


def test_incremental_assumptions_mixed_int_literal_term_sat():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a | b)
    r = m.solve(assumptions=[a.id, ~b, 1 * a])
    assert r.ok


def test_incremental_sat_upgrade_parameter_validation():
    m = Model()
    m.bool("a")
    with pytest.raises(ValueError):
        m.solve(sat_upgrade="invalid-mode")
