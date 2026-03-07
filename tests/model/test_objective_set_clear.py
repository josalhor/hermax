from __future__ import annotations

from typing import Optional

import pytest

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus
from hermax.model import Model


class _FakeIP(IPAMIRSolver):
    def __init__(self, formula=None, *args, **kwargs):
        super().__init__(formula, *args, **kwargs)
        self._status = SolveStatus.OPTIMUM
        self._model = [1]
        self._cost = 0
        self.soft_updates: list[tuple[int, int]] = []
        self.hard: list[list[int]] = []

    def add_clause(self, clause):
        self.hard.append(list(clause))

    def set_soft(self, lit: int, weight: int) -> None:
        self.soft_updates.append((int(lit), int(weight)))

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(lit, weight)

    def solve(self, assumptions: Optional[list[int]] = None, raise_on_abnormal: bool = False) -> bool:
        return True

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        return self._cost

    def val(self, lit: int) -> int:
        return 1 if lit in self._model else -1

    def get_model(self):
        return list(self._model)

    def signature(self) -> str:
        return "fakeip"

    def close(self) -> None:
        return None


def _soft_weights(m: Model):
    return [w for w, _ in m._soft]


def test_obj_assignment_sets_soft_expression_not_accumulate():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj = a
    first_n = len(m._soft)
    m.obj = b
    assert len(m._soft) >= first_n
    # only one active objective unit should remain
    assert sum(1 for w, _ in m._soft if w > 0) == 1


def test_obj_assignment_sugar_equals_set():
    m = Model()
    a = m.bool("a")
    m.obj = a
    assert sum(1 for w, _ in m._soft if w > 0) == 1


def test_obj_clear_disables_all_objective_terms():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj = a + b
    assert sum(1 for w, _ in m._soft if w > 0) == 2
    m.obj.clear()
    assert sum(1 for w, _ in m._soft if w > 0) == 0


def test_obj_clear_resets_objective_constant():
    m = Model()
    x = m.int("x", 3, 7)
    m.obj = x
    # Positive constants are lowered natively through a soft unit on __false.
    assert m._objective_constant == 0
    assert "__false" in m._registry
    m.obj.clear()
    assert m._objective_constant == 0


def test_obj_iadd_still_additive():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj += a
    m.obj += b
    assert sum(1 for w, _ in m._soft if w > 0) == 2


def test_obj_bucket_iadd_still_additive():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj[2] += a
    m.obj[3] += b
    active = [w for w, _ in m._soft if w > 0]
    assert sorted(active) == [2, 3]


def test_obj_set_replaces_after_iadd():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj += a
    assert sum(1 for w, _ in m._soft if w > 0) == 1
    m.obj = b
    assert sum(1 for w, _ in m._soft if w > 0) == 1


def test_obj_set_literal_negation():
    m = Model()
    a = m.bool("a")
    m.obj = ~a
    assert sum(1 for w, _ in m._soft if w > 0) == 1


def test_obj_set_pbexpr_mixed_coeffs():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj = 3 * a - 2 * b + 7
    # two variable terms + one native constant soft term (__false)
    assert sum(1 for w, _ in m._soft if w > 0) == 3
    assert m._objective_constant == 0


def test_obj_set_intvar_supported():
    m = Model()
    x = m.int("x", 0, 5)
    m.obj = x
    assert sum(1 for w, _ in m._soft if w > 0) == len(x._threshold_lits)


def test_obj_set_lazy_expr_supported():
    m = Model()
    x = m.int("x", 0, 9)
    m.obj = x // 3
    assert sum(1 for w, _ in m._soft if w > 0) > 0


def test_obj_set_rejects_pbconstraint_for_now():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    with pytest.raises(TypeError):
        m.obj = (a + b <= 1)


def test_obj_property_setter_does_not_break_iadd_rebinding_path():
    m = Model()
    a = m.bool("a")
    m.obj += a
    assert sum(1 for w, _ in m._soft if w > 0) == 1


def test_obj_diff_updates_incremental_solver_add_change_remove():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    s = _FakeIP()
    m.solve(backend="maxsat", solver=s)
    m.obj = a + b
    m.obj = 3 * a
    # expected: b removed with weight 0 and a updated to 3
    assert any(w == 0 for _lit, w in s.soft_updates)
    assert any(w == 3 for _lit, w in s.soft_updates)


def test_obj_clear_pushes_zero_updates_incremental():
    m = Model()
    a = m.bool("a")
    s = _FakeIP()
    m.solve(backend="maxsat", solver=s)
    m.obj = a
    s.soft_updates.clear()
    m.obj.clear()
    assert s.soft_updates and all(w == 0 for _l, w in s.soft_updates)


def test_obj_set_weight_parameter():
    m = Model()
    a = m.bool("a")
    m.obj.set(a, weight=5)
    assert _soft_weights(m).count(5) >= 1


def test_obj_set_invalid_weight_rejected():
    m = Model()
    a = m.bool("a")
    with pytest.raises(ValueError):
        m.obj.set(a, weight=0)


def test_obj_clear_idempotent():
    m = Model()
    m.obj.clear()
    m.obj.clear()
    assert sum(1 for w, _ in m._soft if w > 0) == 0


def test_obj_set_then_additive_bucket_accumulates_after_set():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj = a
    m.obj[4] += b
    assert sum(1 for w, _ in m._soft if w > 0) == 2


def test_obj_replace_from_int_to_literal_removes_old_terms():
    m = Model()
    x = m.int("x", 0, 4)
    a = m.bool("a")
    m.obj = x
    before_active = sum(1 for w, _ in m._soft if w > 0)
    assert before_active == len(x._threshold_lits)
    m.obj = a
    assert sum(1 for w, _ in m._soft if w > 0) == 1


def test_obj_set_tracks_constant_delta_on_replace():
    m = Model()
    a = m.bool("a")
    m.obj = a + 7
    c1 = m._objective_constant
    w1 = sum(w for w, c in m._soft if w > 0 and len(c.literals) == 1 and c.literals[0].name == "__false")
    m.obj = a + 2
    c2 = m._objective_constant
    w2 = sum(w for w, c in m._soft if w > 0 and len(c.literals) == 1 and c.literals[0].name == "__false")
    assert c1 == c2 == 0
    assert w1 != w2
    assert w2 == 2
