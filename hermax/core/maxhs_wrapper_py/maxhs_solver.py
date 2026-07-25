from __future__ import annotations

import importlib
import importlib.util
import os
from typing import Dict, List, Optional, Set

from pysat.formula import WCNF

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible

_MAX_I64 = (1 << 63) - 1


def _import_backend():
    if os.environ.get("FORCE_MAXHS_NOT_COMPILED", "").strip() == "1":
        raise ImportError("FORCE_MAXHS_NOT_COMPILED=1")
    return importlib.import_module("hermax.core.maxhs_py")


class MaxHSSolver(ReplayFormulaSolverBase):
    """Re-encoding wrapper around MaxHS with replay-per-solve semantics."""

    nonunit_soft_policy = "store"

    @classmethod
    def is_available(cls) -> bool:
        if os.environ.get("FORCE_MAXHS_NOT_COMPILED", "").strip() == "1":
            return False
        spec = importlib.util.find_spec("hermax.core.maxhs_py")
        return spec is not None

    def __init__(self, formula: Optional[WCNF] = None, *args, **kwargs):
        if not self.is_available():
            raise RuntimeError(
                "MaxHS native module is not available in this build "
                "(likely built without CPLEX)."
            )
        backend = _import_backend()
        self._backend_ctor = backend.MaxHS
        self._terminate_cb = None
        self.solver = None  # compatibility hook for tests monkeypatching backend instance
        self._last_model_set: Set[int] = set()
        super().__init__(formula=formula, *args, **kwargs)

    @staticmethod
    def _normalize_nonnegative_weight(weight: int) -> int:
        if not isinstance(weight, int):
            raise ValueError("Weight must be an integer.")
        if int(weight) < 0:
            raise ValueError("Weight must be a non-negative integer.")
        if int(weight) > _MAX_I64:
            raise OverflowError(f"Weight exceeds int64 max: {weight}")
        return int(weight)

    def _invalidate_solution(self) -> None:
        super()._invalidate_solution()
        self._last_model_set.clear()

    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        if self._terminate_cb is not None and int(self._terminate_cb()) != 0:
            raise RuntimeError("Solver terminated by callback")

        solver = self.solver if self.solver is not None else self._backend_ctor()

        current_max = self._num_vars
        for a in assumptions:
            current_max = max(current_max, abs(int(a)))
        self._ensure_var(current_max)

        if hasattr(solver, "setNInputVars"):
            solver.setNInputVars(current_max)

        for cl in self._hard_clauses:
            solver.addClause([int(x) for x in cl], None)

        for a in assumptions:
            solver.addClause([int(a)], None)

        resolved_softs: Dict[int, int] = {}
        for lit, w in self._soft_unit_by_lit.items():
            opp = -int(lit)
            if opp in resolved_softs:
                w_opp = resolved_softs[opp]
                if int(w) > int(w_opp):
                    resolved_softs[int(lit)] = int(w) - int(w_opp)
                    del resolved_softs[opp]
                elif int(w) < int(w_opp):
                    resolved_softs[opp] = int(w_opp) - int(w)
                else:
                    del resolved_softs[opp]
            else:
                resolved_softs[int(lit)] = int(w)

        for lit, w in resolved_softs.items():
            solver.addClause([int(lit)], int(w))

        for cl, w in self._soft_nonunit:
            solver.addClause([int(x) for x in cl], int(w))

        res = solver.solve()
        raw_status: Optional[int] = None
        if hasattr(solver, "solve_status"):
            raw_status = int(solver.solve_status())
        elif isinstance(res, int) and res in {
            int(SolveStatus.INTERRUPTED),
            int(SolveStatus.INTERRUPTED_SAT),
            int(SolveStatus.UNSAT),
            int(SolveStatus.OPTIMUM),
            int(SolveStatus.ERROR),
        }:
            raw_status = int(res)

        is_optimum = raw_status == int(SolveStatus.OPTIMUM) or (raw_status is None and bool(res))
        if is_optimum:
            model = [int(x) for x in solver.getModel()] if hasattr(solver, "getModel") else []
            if len(model) < current_max:
                for i in range(len(model) + 1, current_max + 1):
                    model.append(-i)
            if assumptions:
                for a in assumptions:
                    v = abs(int(a))
                    if 1 <= v <= current_max:
                        model[v - 1] = v if int(a) > 0 else -v
            return ReplaySolveResult(status=SolveStatus.OPTIMUM, model=model, cost=None)

        if raw_status == int(SolveStatus.INTERRUPTED_SAT):
            model = [int(x) for x in solver.getModel()] if hasattr(solver, "getModel") else []
            return ReplaySolveResult(status=SolveStatus.INTERRUPTED_SAT, model=model, cost=None)

        if raw_status == int(SolveStatus.UNSAT):
            return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)

        if raw_status == int(SolveStatus.INTERRUPTED):
            return ReplaySolveResult(status=SolveStatus.INTERRUPTED, model=None, cost=None)

        if raw_status == int(SolveStatus.ERROR):
            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)

        return ReplaySolveResult(status=SolveStatus.UNKNOWN, model=None, cost=None)

    def solve(
        self,
        assumptions: Optional[List[int]] = None,
        raise_on_abnormal: bool = False,
        time_limit: Optional[float] = None,
    ) -> bool:
        ok = super().solve(
            assumptions=assumptions,
            raise_on_abnormal=raise_on_abnormal,
            time_limit=time_limit,
        )
        if self._model is not None:
            self._last_model_set = set(int(x) for x in self._model)
        return ok

    def _compute_wrapper_cost(self, model: List[int]) -> int:
        s = set(int(x) for x in model)
        total = 0
        for lit, w in self._soft_unit_by_lit.items():
            if int(lit) not in s:
                total += int(w)
        for cl, w in self._soft_nonunit:
            if not any(int(l) in s for l in cl):
                total += int(w)
        return int(total)

    def val(self, lit: int) -> int:
        self._require_open()
        if not is_feasible(self._status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        lit = int(lit)
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        if abs(lit) > self._num_vars:
            raise ValueError("Invalid literal for val().")
        v = abs(lit)
        if v in self._last_model_set and -v not in self._last_model_set:
            return 1 if lit > 0 else -1
        if -v in self._last_model_set and v not in self._last_model_set:
            return -1 if lit > 0 else 1
        return 0

    def get_model(self) -> Optional[List[int]]:
        self._require_open()
        if not is_feasible(self._status):
            raise RuntimeError("No model available; last status is not SAT/OPTIMUM")
        return list(self._model) if self._model is not None else None

    def signature(self) -> str:
        return "maxhs-reentrant-ipamir"

    def set_terminate(self, callback) -> None:
        raise NotImplementedError("MaxHS wrapper does not support set_terminate.")
