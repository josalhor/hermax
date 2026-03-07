from __future__ import annotations

import importlib
from typing import Dict, List, Optional, Tuple

from pysat.formula import WCNF

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula
from hermax.internal.maxsat_cli_parse import parse_maxsat_cli_output
from hermax.internal.subprocess_oneshot import run_oneshot_worker


_WORKER_SOLVER_CLASS = "hermax.core.loandra_py.loandra_solver.LoandraSolver"


class Loandra(IPAMIRSolver):
    """
    Loandra fake-incremental wrapper with one-shot subprocess isolation.

    The wrapper stores the formula state in Python and rebuilds/solves it in a
    fresh child Python process on every ``solve()`` call.
    """

    @classmethod
    def is_available(cls) -> bool:
        try:
            mod_name, _, attr = _WORKER_SOLVER_CLASS.rpartition(".")
            mod = importlib.import_module(mod_name)
            backend_cls = getattr(mod, attr)
            return bool(getattr(backend_cls, "is_available", lambda: True)())
        except Exception:
            return False

    def __init__(
        self,
        formula: Optional[WCNF] = None,
        *args,
        timeout_s: float = 30.0,
        timeout_grace_s: float = 1.0,
        **kwargs,
    ):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula, *args, **kwargs)
        self._timeout_s = float(timeout_s)
        self._timeout_grace_s = float(timeout_grace_s)

        self._closed = False
        self._num_vars = 0
        self._hard_clauses: List[List[int]] = []
        self._soft_unit_by_lit: Dict[int, int] = {}
        self._soft_nonunit: List[Tuple[List[int], int]] = []

        self._status: SolveStatus = SolveStatus.UNKNOWN
        self._model: Optional[List[int]] = None
        self._last_cost: Optional[int] = None
        self._last_signature: str = "Loandra (subprocess wrapper)"
        self._last_error: Optional[str] = None
        self._last_worker_stderr: str = ""
        self._last_worker_stdout: str = ""
        self._last_protocol_error: Optional[str] = None
        self._last_elapsed_s: float = 0.0

        if formula is not None:
            self._load_initial_formula(formula)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Solver is closed")

    def _invalidate(self) -> None:
        self._status = SolveStatus.UNKNOWN
        self._model = None
        self._last_cost = None
        self._last_error = None
        self._last_worker_stderr = ""
        self._last_worker_stdout = ""
        self._last_protocol_error = None
        self._last_elapsed_s = 0.0

    def new_var(self) -> int:
        self._require_open()
        self._num_vars += 1
        self._invalidate()
        return self._num_vars

    def add_clause(self, clause: List[int], weight: Optional[int] = None) -> None:
        self._require_open()
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        cl = [int(x) for x in clause]
        for lit in cl:
            if lit == 0:
                raise ValueError("Clause literals cannot be 0.")
            while abs(lit) > self._num_vars:
                self._num_vars += 1

        if weight is None:
            self._hard_clauses.append(cl)
            self._invalidate()
            return

        if not isinstance(weight, int):
            raise TypeError("Weight must be an integer.")
        if weight <= 0:
            raise ValueError("Weight must be a positive integer.")
        if len(cl) == 0:
            raise ValueError("Empty soft clause is not allowed.")

        if len(cl) == 1:
            self.set_soft(cl[0], int(weight))
        else:
            b = self.new_var()
            self.add_soft_relaxed(cl, int(weight), relax_var=b)

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        lit = int(lit)
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        if not isinstance(weight, int):
            raise TypeError("Weight must be an integer.")
        weight = int(weight)
        if weight < 0:
            raise ValueError("Weight must be a non-negative integer.")
        while abs(lit) > self._num_vars:
            self._num_vars += 1
        if weight == 0:
            self._soft_unit_by_lit.pop(lit, None)
        else:
            self._soft_unit_by_lit[lit] = weight
        self._invalidate()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        if not isinstance(weight, int) or int(weight) <= 0:
            raise ValueError("Weight must be a positive integer.")
        self.set_soft(lit, weight)

    def _snapshot(self, assumptions: Optional[List[int]] = None) -> Dict[str, object]:
        hard = [list(cl) for cl in self._hard_clauses]
        if assumptions:
            hard.extend([[int(a)] for a in assumptions])
        return {
            "num_vars": int(self._num_vars),
            "hard_clauses": hard,
            "soft_units": [(int(l), int(w)) for l, w in self._soft_unit_by_lit.items()],
            "soft_nonunit": [(list(cl), int(w)) for cl, w in self._soft_nonunit],
        }

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._require_open()
        self._invalidate()
        assumps = [int(a) for a in assumptions] if assumptions else []
        for lit in assumps:
            if lit == 0:
                raise ValueError("Assumptions must be non-zero integers.")
            while abs(lit) > self._num_vars:
                self._num_vars += 1

        req = {
            "solver_class_path": _WORKER_SOLVER_CLASS,
            "snapshot": self._snapshot(assumps),
            "assumptions": [],
        }
        run = run_oneshot_worker(req, timeout_s=self._timeout_s, grace_s=self._timeout_grace_s)
        self._last_elapsed_s = run.elapsed_s
        self._last_protocol_error = run.protocol_error
        self._last_worker_stderr = (run.stderr_raw or b"").decode("utf-8", errors="replace")
        self._last_worker_stdout = (run.stdout_raw or b"").decode("utf-8", errors="replace")

        if run.response is None and run.exit_code in {10, 20, 30, 40, 50}:
            self._apply_fallback_solver_output(run.exit_code, self._last_worker_stdout)
            if raise_on_abnormal and self._status in {SolveStatus.INTERRUPTED, SolveStatus.ERROR, SolveStatus.UNKNOWN}:
                raise RuntimeError(f"Solver terminated with abnormal status: {self._status.name}")
            return is_feasible(self._status)

        if run.timed_out and run.response is None:
            self._status = SolveStatus.INTERRUPTED
            self._last_error = "timeout"
            if raise_on_abnormal:
                raise RuntimeError("Loandra worker timed out")
            return False

        if run.response is None:
            self._status = SolveStatus.ERROR
            self._last_error = run.protocol_error or f"worker exited with code {run.exit_code}"
            if raise_on_abnormal:
                raise RuntimeError(self._last_error)
            return False

        resp = run.response
        if not resp.get("ok", False):
            self._status = SolveStatus.ERROR
            self._last_error = resp.get("error") or resp.get("error_type") or "worker error"
            if raise_on_abnormal:
                raise RuntimeError(f"{resp.get('error_type', 'WorkerError')}: {self._last_error}")
            return False

        try:
            self._status = SolveStatus(int(resp["status"]))
        except Exception:
            self._status = SolveStatus.ERROR
            self._last_error = "invalid worker status"
            if raise_on_abnormal:
                raise RuntimeError(self._last_error)
            return False

        self._last_signature = str(resp.get("signature") or self._last_signature)
        if resp.get("cost") is not None:
            try:
                self._last_cost = int(resp["cost"])
            except Exception:
                self._last_cost = None
        if resp.get("model") is not None:
            self._model = [int(x) for x in resp["model"]]
            if len(self._model) < self._num_vars:
                for i in range(len(self._model) + 1, self._num_vars + 1):
                    self._model.append(-i)
            self._model = self._model[: self._num_vars]
        if self._model is not None and is_feasible(self._status):
            self._last_cost = self._compute_wrapper_cost(self._model)

        if raise_on_abnormal and self._status in {SolveStatus.INTERRUPTED, SolveStatus.ERROR, SolveStatus.UNKNOWN}:
            raise RuntimeError(f"Solver terminated with abnormal status: {self._status.name}")
        return is_feasible(self._status)

    def _apply_fallback_solver_output(self, exit_code: Optional[int], text: str) -> None:
        st, obj, model = parse_maxsat_cli_output(text, num_vars=self._num_vars)
        if st is None:
            if exit_code == 30:
                st = SolveStatus.OPTIMUM
            elif exit_code == 20:
                st = SolveStatus.UNSAT
            elif exit_code == 10:
                st = SolveStatus.INTERRUPTED_SAT
            else:
                st = SolveStatus.ERROR
        self._status = st
        self._last_signature = "Loandra (subprocess worker/native binding)"
        if model is not None:
            if len(model) < self._num_vars:
                for i in range(len(model) + 1, self._num_vars + 1):
                    model.append(-i)
            self._model = model[: self._num_vars]
        else:
            self._model = None
        self._last_cost = obj if obj is not None else None
        if self._last_cost is None and self._model is not None and is_feasible(self._status):
            self._last_cost = self._compute_wrapper_cost(self._model)
        if self._status == SolveStatus.ERROR and self._last_error is None:
            self._last_error = f"worker exited with code {exit_code}"

    def _compute_wrapper_cost(self, model: List[int]) -> int:
        asg = {abs(int(m)): int(m) > 0 for m in model}
        total = 0
        for lit, w in self._soft_unit_by_lit.items():
            v = abs(int(lit))
            val = asg.get(v, False)
            lit_true = val if lit > 0 else (not val)
            if not lit_true:
                total += int(w)
        for cl, w in self._soft_nonunit:
            sat = False
            for l in cl:
                lv = abs(int(l))
                val = asg.get(lv, False)
                if (int(l) > 0 and val) or (int(l) < 0 and not val):
                    sat = True
                    break
            if not sat:
                total += int(w)
        return total

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        if not is_feasible(self._status):
            raise RuntimeError("Cost is only available for feasible status.")
        if self._last_cost is None:
            raise RuntimeError("Objective value unavailable")
        return int(self._last_cost)

    def val(self, lit: int) -> int:
        if not is_feasible(self._status) or self._model is None:
            raise RuntimeError("No model available")
        lit = int(lit)
        if lit == 0:
            raise ValueError("Literal 0 is invalid.")
        v = abs(lit)
        if v > self._num_vars:
            raise ValueError("Invalid literal for val().")
        m = self._model[v - 1]
        return 1 if m == (v if lit > 0 else -v) else -1

    def get_model(self) -> Optional[List[int]]:
        if not is_feasible(self._status):
            raise RuntimeError("No model available")
        return list(self._model) if self._model is not None else None

    def signature(self) -> str:
        return f"{self._last_signature} [oneshot subprocess]"

    def close(self) -> None:
        self._closed = True
        self._hard_clauses.clear()
        self._soft_unit_by_lit.clear()
        self._soft_nonunit.clear()
        self._invalidate()

    def set_terminate(self, callback):
        raise NotImplementedError("set_terminate is not supported by this wrapper")

    def _load_initial_formula(self, formula: WCNF) -> None:
        for cl in getattr(formula, "hard", []):
            self.add_clause(list(map(int, cl)))

        soft_attr = getattr(formula, "soft", [])
        wghts = getattr(formula, "wght", None)
        if wghts is not None and len(wghts) == len(soft_attr) and (not soft_attr or not isinstance(soft_attr[0], tuple)):
            for cl, w in zip(soft_attr, wghts):
                self.add_clause(list(map(int, cl)), int(w))
            return
        for item in soft_attr:
            if isinstance(item, tuple) and len(item) >= 2:
                cl, w = item[0], item[1]
            else:
                cl, w = item, 1
            self.add_clause(list(map(int, cl)), int(w))
