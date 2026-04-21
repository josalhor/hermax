from __future__ import annotations

import abc
from typing import List, Optional

from pysat.formula import WCNF
from hermax.core.rc2.rc2 import RC2

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible
from hermax.internal.subprocess_oneshot import run_oneshot_worker


class OneShotSubprocessReplaySolverBase(ReplayFormulaSolverBase, abc.ABC):
    """Replay wrapper that solves via one-shot worker subprocesses."""

    # If False, assumptions are emulated as temporary hard units in snapshot.
    pass_assumptions_to_worker: bool = True

    @property
    @abc.abstractmethod
    def worker_solver_class_path(self) -> str:
        """Import path to worker-side solver class."""

    @property
    @abc.abstractmethod
    def default_signature(self) -> str:
        """Default wrapper signature label."""

    @property
    @abc.abstractmethod
    def timeout_error_prefix(self) -> str:
        """Name used in timeout error message."""

    @staticmethod
    def _coerce_int(value: object) -> Optional[int]:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return int(value)
        if isinstance(value, str):
            s = value.strip()
            if s.startswith(("+", "-")):
                sign, digits = s[0], s[1:]
                if digits.isdigit():
                    return int(sign + digits)
            elif s.isdigit():
                return int(s)
        return None

    def __init__(
        self,
        formula: Optional[WCNF] = None,
        *args,
        timeout_s: float = 30.0,
        timeout_grace_s: float = 1.0,
        **kwargs,
    ):
        super().__init__(formula=formula, *args, **kwargs)
        self._timeout_s = float(timeout_s)
        self._timeout_grace_s = float(timeout_grace_s)

        self._last_signature: str = self.default_signature
        self._last_error: Optional[str] = None
        self._last_worker_stderr: str = ""
        self._last_worker_stdout: str = ""
        self._last_protocol_error: Optional[str] = None
        self._last_elapsed_s: float = 0.0

    def _invalidate_solution(self) -> None:
        super()._invalidate_solution()
        self._last_error = None
        self._last_worker_stderr = ""
        self._last_worker_stdout = ""
        self._last_protocol_error = None
        self._last_elapsed_s = 0.0

    def _run_replay_solve(self, assumptions: List[int]) -> ReplaySolveResult:
        req_assumps = assumptions if self.pass_assumptions_to_worker else []
        snapshot_assumps = assumptions if not self.pass_assumptions_to_worker else None

        req = {
            "solver_class_path": self.worker_solver_class_path,
            "snapshot": self._snapshot(snapshot_assumps),
            "assumptions": [int(a) for a in req_assumps],
        }

        run = run_oneshot_worker(req, timeout_s=self._timeout_s, grace_s=self._timeout_grace_s)
        self._last_elapsed_s = run.elapsed_s
        self._last_protocol_error = run.protocol_error
        self._last_worker_stderr = (run.stderr_raw or b"").decode("utf-8", errors="replace")
        self._last_worker_stdout = (run.stdout_raw or b"").decode("utf-8", errors="replace")

        if run.timed_out and run.response is None:
            self._last_error = "timeout"
            return ReplaySolveResult(status=SolveStatus.INTERRUPTED, model=None, cost=None)

        if run.response is None:
            compat = self._compat_result_from_exit_code(run.exit_code, assumptions)
            if compat is not None:
                return compat
            self._last_error = run.protocol_error or f"worker exited with code {run.exit_code}"
            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)

        resp = run.response
        if not resp.get("ok", False):
            self._last_error = resp.get("error") or resp.get("error_type") or "worker error"
            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)

        status_i = self._coerce_int(resp.get("status"))
        allowed = {
            int(SolveStatus.INTERRUPTED),
            int(SolveStatus.INTERRUPTED_SAT),
            int(SolveStatus.UNSAT),
            int(SolveStatus.OPTIMUM),
            int(SolveStatus.ERROR),
            int(SolveStatus.UNKNOWN),
        }
        if status_i not in allowed:
            self._last_error = "invalid worker status"
            return ReplaySolveResult(status=SolveStatus.ERROR, model=None, cost=None)

        st = SolveStatus(status_i)
        self._last_signature = str(resp.get("signature") or self._last_signature)

        model = None
        if resp.get("model") is not None:
            model = [int(x) for x in resp["model"]]

        cost = None
        if resp.get("cost") is not None:
            cost = self._coerce_int(resp.get("cost"))

        return ReplaySolveResult(status=st, model=model, cost=cost)

    def _compat_result_from_exit_code(
        self,
        exit_code: Optional[int],
        assumptions: List[int],
    ) -> Optional[ReplaySolveResult]:
        if exit_code is None:
            return None

        code_to_status = {
            10: SolveStatus.INTERRUPTED_SAT,
            20: SolveStatus.UNSAT,
            30: SolveStatus.OPTIMUM,
            40: SolveStatus.ERROR,
            50: SolveStatus.UNKNOWN,
        }
        st = code_to_status.get(int(exit_code))
        if st is None:
            return None

        if not is_feasible(st):
            return ReplaySolveResult(status=st, model=None, cost=None)

        model, cost = self._reference_solve_from_snapshot(assumptions)
        if model is None:
            return ReplaySolveResult(status=SolveStatus.UNSAT, model=None, cost=None)
        return ReplaySolveResult(status=st, model=model, cost=cost)

    def _reference_solve_from_snapshot(self, assumptions: List[int]) -> tuple[Optional[List[int]], Optional[int]]:
        wcnf = WCNF()
        max_var = int(self._num_vars)

        for cl in self._hard_clauses:
            wcnf.append([int(x) for x in cl])
            for lit in cl:
                max_var = max(max_var, abs(int(lit)))

        for a in assumptions:
            wcnf.append([int(a)])
            max_var = max(max_var, abs(int(a)))

        for lit, w in self._soft_unit_by_lit.items():
            wcnf.append([int(lit)], weight=int(w))
            max_var = max(max_var, abs(int(lit)))

        for cl, w in self._soft_nonunit:
            wcnf.append([int(x) for x in cl], weight=int(w))
            for lit in cl:
                max_var = max(max_var, abs(int(lit)))

        wcnf.nv = max(int(getattr(wcnf, "nv", 0)), max_var)
        with RC2(wcnf) as rc2:
            model = rc2.compute()
            if model is None:
                return None, None
            out = [int(x) for x in model]
            return out, int(rc2.cost)

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._require_open()
        self._invalidate_solution()

        assumps = self._normalize_assumptions(assumptions)
        result = self._run_replay_solve(assumps)

        self._set_result(
            status=result.status,
            model=result.model,
            cost=result.cost,
            num_vars=self._num_vars,
        )

        if self._model is not None and is_feasible(self._status):
            self._last_cost = self._compute_wrapper_cost(self._model)

        self._maybe_raise_on_abnormal(raise_on_abnormal)
        return is_feasible(self._status)

    def signature(self) -> str:
        return f"{self._last_signature} [oneshot subprocess]"
