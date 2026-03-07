from __future__ import annotations

from typing import Optional

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus
from hermax.model import Model


class _FakeIPCost(IPAMIRSolver):
    def __init__(self, formula=None, cost: int = 0):
        super().__init__(formula)
        self._cost = int(cost)
        self._status = SolveStatus.OPTIMUM
        self._model = [1]
        self.soft_units: list[tuple[int, int]] = []
        self.soft_relaxed: list[tuple[list[int], int, int]] = []

    def add_clause(self, clause):
        return None

    def set_soft(self, lit: int, weight: int) -> None:
        self.soft_units.append((int(lit), int(weight)))

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.soft_units.append((int(lit), int(weight)))

    def add_soft_relaxed(self, clause: list[int], weight: int, relaxation_lit: int) -> None:
        self.soft_relaxed.append((list(clause), int(weight), int(relaxation_lit)))
        self.soft_units.append((-int(relaxation_lit), int(weight)))

    def solve(self, assumptions: Optional[list[int]] = None, raise_on_abnormal: bool = False) -> bool:
        return True

    def get_status(self):
        return self._status

    def get_cost(self) -> int:
        return int(self._cost)

    def val(self, lit: int) -> int:
        return 1

    def get_model(self):
        return list(self._model)

    def signature(self) -> str:
        return "fake-cost"

    def close(self) -> None:
        return None


def test_soft_gcd_optimization_enabled_by_default_scales_one_shot_weights():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.add_soft(a, 10)
    m.add_soft(~b, 20)
    s = _FakeIPCost(cost=0)
    m.solve(solver=s, incremental=False)
    sent = sorted(w for _l, w in s.soft_units)
    assert sent == [1, 2]


def test_soft_gcd_optimization_compensates_reported_cost():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.add_soft(a, 10)
    m.add_soft(~b, 20)
    s = _FakeIPCost(cost=7)
    r = m.solve(solver=s, incremental=False)
    assert r.cost == 70


def test_soft_gcd_optimization_can_be_disabled():
    m = Model()
    m.set_soft_gcd_optimization(False)
    a = m.bool("a")
    b = m.bool("b")
    m.add_soft(a, 10)
    m.add_soft(~b, 20)
    s = _FakeIPCost(cost=7)
    r = m.solve(solver=s, incremental=False)
    sent = sorted(w for _l, w in s.soft_units)
    assert sent == [10, 20]
    assert r.cost == 7


def test_soft_gcd_optimization_no_effect_when_gcd_is_one():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.add_soft(a, 5)
    m.add_soft(~b, 6)
    s = _FakeIPCost(cost=9)
    r = m.solve(solver=s, incremental=False)
    sent = sorted(w for _l, w in s.soft_units)
    assert sent == [5, 6]
    assert r.cost == 9


def test_soft_dedup_can_be_disabled_via_model_method():
    m = Model()
    m.set_soft_dedup(False)
    a = m.bool("a")
    r1 = m.add_soft(a, 5)
    r2 = m.add_soft(a, 10)
    assert len(m._soft) == 2
    assert sorted(w for w, _ in m._soft) == [5, 10]
    assert r1.soft_ids[0] != r2.soft_ids[0]

