from __future__ import annotations

from typing import List, Optional

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus
from hermax.model import Clause, Model


class _NoNewVarIPSolver(IPAMIRSolver):
    def __init__(self, formula=None):
        super().__init__()
        self._status = SolveStatus.UNKNOWN
        self._nv = int(getattr(formula, "nv", 0)) if formula is not None else 0
        self.soft_updates: list[tuple[int, int]] = []
        self.soft_relaxed: list[tuple[list[int], int, int]] = []

    def add_clause(self, clause: list[int]) -> None:
        for l in clause:
            self._nv = max(self._nv, abs(int(l)))

    def set_soft(self, lit: int, weight: int) -> None:
        self.soft_updates.append((int(lit), int(weight)))

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), int(weight))

    def add_soft_relaxed(self, clause: list[int], weight: int, relaxation_lit: int) -> None:
        self.soft_relaxed.append((list(clause), int(weight), int(relaxation_lit)))
        self.set_soft(-int(relaxation_lit), int(weight))

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False, time_limit=None) -> bool:
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
        return "nonewvar-fake"

    def close(self) -> None:
        return None

    def new_var(self) -> int:
        raise NotImplementedError


def test_incremental_maxsat_relaxed_soft_uses_new_var_fallback_when_missing():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj.add_soft(Clause(m, [a, b]), 1)
    s = _NoNewVarIPSolver()
    r = m.solve(incremental=True, backend="maxsat", solver=s)
    assert r.ok
    assert s.soft_relaxed, "expected relaxed soft routing path"
    # Relaxation literal is synthesized even if solver.new_var is unavailable.
    assert s.soft_relaxed[0][2] > 0


def test_incremental_maxsat_routes_zero_weight_update_for_objective_clear():
    m = Model()
    a = m.bool("a")
    m.obj += a
    s = _NoNewVarIPSolver()
    r = m.solve(incremental=True, backend="maxsat", solver=s)
    assert r.ok
    s.soft_updates.clear()
    m.obj.clear()
    assert any(w == 0 for _lit, w in s.soft_updates)
