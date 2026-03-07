from __future__ import annotations

import inspect
import importlib
import os
import tempfile
import time
import warnings
from enum import Enum
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Type

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.core.utils import normalize_wcnf_formula
from hermax.internal.maxsat_cli_parse import parse_maxsat_cli_output
from hermax.internal.model_check import check_model
from hermax.internal.subprocess_oneshot import (
    _dumps_frame,
    _interrupt_process,
    _kill_process,
    _loads_frame_from_bytes,
    _worker_cmd,
    _popen_kwargs,
)


PortfolioPolicy = str


class CallbackAction(Enum):
    CONTINUE = "CONTINUE"
    STOP = "STOP"
    DROP_CURRENT = "DROP_CURRENT"


@dataclass(frozen=True)
class AdjustTimeout:
    new_timeout_s: float
    mode: str = "relative"  # "relative" | "absolute"


@dataclass(frozen=True)
class PortfolioEvent:
    event_type: str  # "HEARTBEAT" | "INCUMBENT"
    elapsed_s: float
    worker_id: Optional[int] = None
    cost: Optional[int] = None
    model: Optional[List[int]] = None
    is_optimal: bool = False


_INCOMPLETE_CLASS_PATH_MAP: Dict[str, str] = {
    "hermax.non_incremental.incomplete.SPBMaxSATCFPS": "hermax.core.spb_maxsat_c_fps_py.spb_maxsat_c_fps_solver.SPBMaxSATCFPSSolver",
    "hermax.non_incremental.incomplete.NuWLSCIBR": "hermax.core.nuwls_c_ibr_py.nuwls_c_ibr_solver.NuWLSCIBRSolver",
    "hermax.non_incremental.incomplete.Loandra": "hermax.core.loandra_py.loandra_solver.LoandraSolver",
    "hermax.non_incremental.incomplete.OpenWBOInc": "hermax.core.openwbo_inc_py.openwbo_inc_solver.OpenWBOIncSolver",
    "hermax.core.spb_maxsat_c_fps_py.spb_maxsat_c_fps_subprocess.SPBMaxSATCFPS": "hermax.core.spb_maxsat_c_fps_py.spb_maxsat_c_fps_solver.SPBMaxSATCFPSSolver",
    "hermax.core.nuwls_c_ibr_py.nuwls_c_ibr_subprocess.NuWLSCIBR": "hermax.core.nuwls_c_ibr_py.nuwls_c_ibr_solver.NuWLSCIBRSolver",
    "hermax.core.loandra_py.loandra_subprocess.Loandra": "hermax.core.loandra_py.loandra_solver.LoandraSolver",
    "hermax.core.openwbo_inc_py.openwbo_inc_subprocess.OpenWBOInc": "hermax.core.openwbo_inc_py.openwbo_inc_solver.OpenWBOIncSolver",
}

_INCOMPLETE_WORKER_CLASSES: set[str] = set(_INCOMPLETE_CLASS_PATH_MAP.values())


def _class_path(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _worker_solver_path_for_class(cls: type) -> str:
    p = _class_path(cls)
    return _INCOMPLETE_CLASS_PATH_MAP.get(p, p)


def _effective_solver_key(cls: type) -> str:
    return _worker_solver_path_for_class(cls)


def _solver_is_available(cls: type) -> bool:
    try:
        if hasattr(cls, "is_available"):
            return bool(cls.is_available())
        return True
    except Exception:
        return False


def _solver_is_known_incomplete(worker_class_path: str) -> bool:
    return worker_class_path in _INCOMPLETE_WORKER_CLASSES


def _solver_proves_optimum(worker_class_path: str) -> bool:
    return not _solver_is_known_incomplete(worker_class_path)


def _solver_proves_unsat(worker_class_path: str) -> bool:
    return not _solver_is_known_incomplete(worker_class_path)


def _is_ipamir_solver_class(obj: Any) -> bool:
    try:
        return inspect.isclass(obj) and issubclass(obj, IPAMIRSolver) and obj is not IPAMIRSolver
    except Exception:
        return False


def _public_namespace_solver_classes(module_name: str) -> list[type]:
    mod = importlib.import_module(module_name)
    names = list(getattr(mod, "__all__", []))
    if not names:
        names = [n for n in dir(mod) if not n.startswith("_")]
    out: list[type] = []
    for name in names:
        obj = getattr(mod, name, None)
        if not _is_ipamir_solver_class(obj):
            continue
        try:
            if inspect.isabstract(obj):
                continue
        except Exception:
            pass
        out.append(obj)
    return out


def _discover_solver_classes_from_namespaces(
    namespace_modules: Sequence[str],
    *,
    include: Sequence[type] | None = None,
    exclude: Sequence[type] | None = None,
) -> list[type]:
    include_set = set(include or [])
    exclude_keys = {_effective_solver_key(c) for c in (exclude or []) if inspect.isclass(c)}
    seen: set[str] = set()
    classes: list[type] = []

    for module_name in namespace_modules:
        for cls in _public_namespace_solver_classes(module_name):
            key = _effective_solver_key(cls)
            if key in exclude_keys or key in seen:
                continue
            seen.add(key)
            classes.append(cls)

    for cls in include_set:
        if not _is_ipamir_solver_class(cls):
            continue
        key = _effective_solver_key(cls)
        if key in exclude_keys or key in seen:
            continue
        seen.add(key)
        classes.append(cls)

    classes.sort(key=lambda c: _effective_solver_key(c))
    return classes


@dataclass
class _WorkerProc:
    solver_name: str
    worker_class_path: str
    proc: Any
    stdout_file: Any
    stderr_file: Any
    start_s: float
    deadline_s: float
    timeout_s: float
    grace_s: float
    request_assumptions: List[int]
    done: bool = False
    timed_out: bool = False
    interrupted: bool = False
    killed: bool = False
    exit_code: Optional[int] = None
    stdout_raw: bytes = b""
    stderr_raw: bytes = b""
    response: Optional[Dict[str, Any]] = None
    protocol_error: Optional[str] = None
    elapsed_s: float = 0.0

    def cleanup(self) -> None:
        try:
            self.stdout_file.close()
        except Exception:
            pass
        try:
            self.stderr_file.close()
        except Exception:
            pass


class PortfolioSolver(IPAMIRSolver):
    """
    Portfolio MaxSAT solver that races multiple Hermax solver classes in parallel.

    The portfolio is fake-incremental: it caches the formula in Python and
    replays an IPAMIR-level operation log into a fresh worker process per solver
    on each ``solve()`` call.
    """

    SUPPORTED_POLICIES = {
        "best_valid_until_timeout",
        "first_valid",
        "first_optimal_or_best_until_timeout",
    }
    CALLBACK_HEARTBEAT_S = 1.0

    def __init__(
        self,
        solver_classes: Sequence[Type[IPAMIRSolver]],
        formula=None,
        *,
        per_solver_timeout_s: float = 20.0,
        overall_timeout_s: float = 0.0,
        timeout_grace_s: float = 1.0,
        max_workers: int = 0,
        selection_policy: PortfolioPolicy = "first_optimal_or_best_until_timeout",
        validate_model: bool = True,
        recompute_cost_from_model: bool = True,
        invalid_result_policy: str = "warn_drop",
        verbose_invalid: bool = True,
    ):
        formula = normalize_wcnf_formula(formula)
        super().__init__(formula)
        if not solver_classes:
            raise ValueError("solver_classes must be a non-empty sequence of solver classes.")
        if selection_policy not in self.SUPPORTED_POLICIES:
            raise ValueError(f"Unsupported selection_policy={selection_policy!r}")
        if invalid_result_policy not in {"warn_drop", "drop", "ignore", "raise"}:
            raise ValueError(f"Unsupported invalid_result_policy={invalid_result_policy!r}")

        self._solver_classes: list[type] = [cls for cls in solver_classes]
        self._per_solver_timeout_s = float(per_solver_timeout_s)
        self._overall_timeout_s = float(overall_timeout_s)
        self._timeout_grace_s = float(timeout_grace_s)
        self._max_workers = int(max_workers)
        if self._max_workers < 0:
            raise ValueError("max_workers must be >= 0")
        self._selection_policy = selection_policy
        self._validate_model = bool(validate_model)
        self._recompute_cost = bool(recompute_cost_from_model)
        self._invalid_result_policy = invalid_result_policy
        self._verbose_invalid = bool(verbose_invalid)

        self._closed = False
        self._num_vars = 0
        self._ops: list[tuple] = []
        self._hard_clauses: list[list[int]] = []
        self._softs: list[tuple[list[int], int]] = []

        self._status = SolveStatus.UNKNOWN
        self._model: Optional[List[int]] = None
        self._last_cost: Optional[int] = None
        self._last_error: Optional[str] = None
        self._last_solver_name: Optional[str] = None
        self._last_run_details: list[dict[str, Any]] = []
        self._callback: Optional[Callable[..., Any]] = None
        self._callback_accepts_event: bool = True

        if formula is not None:
            self._load_initial_formula(formula)

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def complete(cls, *args, **kwargs):
        return CompletePortfolioSolver(*args, **kwargs)

    @classmethod
    def incomplete(cls, *args, **kwargs):
        return IncompletePortfolioSolver(*args, **kwargs)

    @classmethod
    def performance(cls, *args, **kwargs):
        return PerformancePortfolioSolver(*args, **kwargs)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Solver is closed")

    def set_callback(self, callback: Optional[Callable[..., Any]]) -> None:
        """Register portfolio callback.

        Backward-compatible signatures:
        * ``callback()`` (legacy)
        * ``callback(event: PortfolioEvent)`` (preferred)
        """
        self._require_open()
        if callback is None:
            self._callback = None
            self._callback_accepts_event = True
            return
        if not callable(callback):
            raise TypeError("callback must be callable or None")
        accepts_event = True
        try:
            sig = inspect.signature(callback)
            required_positional = [
                p
                for p in sig.parameters.values()
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                and p.default is inspect._empty
            ]
            if len(required_positional) == 0:
                accepts_event = False
            elif len(required_positional) >= 1:
                accepts_event = True
        except Exception:
            accepts_event = True
        self._callback = callback
        self._callback_accepts_event = bool(accepts_event)

    def _invalidate(self) -> None:
        self._status = SolveStatus.UNKNOWN
        self._model = None
        self._last_cost = None
        self._last_error = None
        self._last_solver_name = None
        self._last_run_details = []

    def new_var(self) -> int:
        self._require_open()
        self._num_vars += 1
        self._ops.append(("new_var",))
        self._invalidate()
        return self._num_vars

    def add_clause(self, clause: list[int]) -> None:
        self._require_open()
        if not isinstance(clause, list):
            raise ValueError("Clause must be a list.")
        cl = [int(x) for x in clause]
        for lit in cl:
            if lit == 0:
                raise ValueError("Clause literals cannot be 0.")
            while abs(lit) > self._num_vars:
                self.new_var()
        self._ops.append(("add_clause", cl))
        self._hard_clauses.append(cl)
        self._invalidate()

    def set_soft(self, lit: int, weight: int) -> None:
        self._require_open()
        if not isinstance(lit, int):
            raise TypeError("Soft literal must be an integer.")
        if not isinstance(weight, int):
            raise TypeError("Weight must be a positive integer.")
        lit = int(lit)
        weight = int(weight)
        if lit == 0:
            raise ValueError("Soft literal must be non-zero.")
        if weight <= 0:
            raise ValueError("Weight must be positive.")
        while abs(lit) > self._num_vars:
            self.new_var()
        self._ops.append(("set_soft", lit, weight))
        self._softs.append(([lit], weight))
        self._invalidate()

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self._require_open()
        self.set_soft(int(lit), int(weight))

    def add_soft_relaxed(self, clause: list[int], weight: int, relax_var: int | None):
        self._require_open()
        # Mirror IPAMIRSolver semantics while tracking exact replay op.
        if not isinstance(clause, list) or len(clause) == 0:
            raise ValueError("clause must be a non-empty list")
        if not isinstance(weight, int):
            raise TypeError("weight must be a positive int")
        if int(weight) <= 0:
            raise ValueError("weight must be a positive int")
        cl = [int(x) for x in clause]
        for lit in cl:
            if lit == 0:
                raise ValueError("Clause literals cannot be 0.")
            while abs(lit) > self._num_vars:
                self.new_var()

        if relax_var is None:
            if len(cl) != 1:
                raise ValueError("relax_var=None only allowed for unit clauses")
            self.add_soft_unit(cl[0], int(weight))
            return None

        b = abs(int(relax_var))
        while b > self._num_vars:
            self.new_var()
        self._ops.append(("add_soft_relaxed", cl, int(weight), b))
        # Semantic effect for validation
        self._hard_clauses.append([*cl, b])
        self._softs.append(([-b], int(weight)))
        self._invalidate()
        return b

    def _launch_workers(self, assumptions: list[int]) -> list[_WorkerProc]:
        workers: list[_WorkerProc] = []
        now = time.monotonic()
        for cls in self._solver_classes:
            w = self._spawn_worker(cls, assumptions, now)
            if w is not None:
                workers.append(w)
        return workers

    def _spawn_worker(self, cls: type, assumptions: list[int], now: Optional[float] = None) -> Optional[_WorkerProc]:
        if now is None:
            now = time.monotonic()
        if not _solver_is_available(cls):
            self._last_run_details.append(
                {"solver": _class_path(cls), "status": "SKIP", "reason": "unavailable"}
            )
            return None
        worker_class_path = _worker_solver_path_for_class(cls)
        req = {
            "solver_class_path": worker_class_path,
            "ops": list(self._ops),
            "assumptions": [int(a) for a in assumptions],
        }
        req_bytes = _dumps_frame(req)
        stdout_f = tempfile.TemporaryFile()
        stderr_f = tempfile.TemporaryFile()
        kwargs = _popen_kwargs()
        kwargs["stdout"] = stdout_f
        kwargs["stderr"] = stderr_f
        proc = __import__("subprocess").Popen(_worker_cmd(), **kwargs)
        assert proc.stdin is not None
        proc.stdin.write(req_bytes)
        proc.stdin.flush()
        proc.stdin.close()
        return _WorkerProc(
            solver_name=cls.__name__,
            worker_class_path=worker_class_path,
            proc=proc,
            stdout_file=stdout_f,
            stderr_file=stderr_f,
            start_s=now,
            deadline_s=now + self._per_solver_timeout_s,
            timeout_s=self._per_solver_timeout_s,
            grace_s=self._timeout_grace_s,
            request_assumptions=list(assumptions),
        )

    def _finalize_worker(self, w: _WorkerProc) -> None:
        if w.done:
            return
        code = w.proc.poll()
        if code is None:
            return
        w.exit_code = int(code)
        w.elapsed_s = time.monotonic() - w.start_s
        try:
            w.stdout_file.seek(0)
            w.stdout_raw = w.stdout_file.read() or b""
        except Exception:
            w.stdout_raw = b""
        try:
            w.stderr_file.seek(0)
            w.stderr_raw = w.stderr_file.read() or b""
        except Exception:
            w.stderr_raw = b""
        if w.stderr_raw:
            try:
                resp = _loads_frame_from_bytes(w.stderr_raw)
                if isinstance(resp, dict):
                    w.response = resp
            except Exception as e:
                w.protocol_error = f"{type(e).__name__}: {e}"
        w.done = True

    def _timeout_worker(self, w: _WorkerProc) -> None:
        if w.done:
            return
        if w.proc.poll() is not None:
            self._finalize_worker(w)
            return
        w.timed_out = True
        w.interrupted = _interrupt_process(w.proc)
        deadline = time.monotonic() + max(0.0, w.grace_s)
        while time.monotonic() < deadline:
            if w.proc.poll() is not None:
                break
            time.sleep(0.01)
        if w.proc.poll() is None:
            w.killed = _kill_process(w.proc)
        try:
            w.proc.wait(timeout=max(0.0, w.grace_s))
        except Exception:
            pass
        self._finalize_worker(w)

    def _validate_candidate(
        self,
        w: _WorkerProc,
        status: SolveStatus,
        model: Optional[list[int]],
        cost: Optional[int],
    ) -> tuple[bool, Optional[int], Optional[str]]:
        if not is_feasible(status):
            return True, cost, None
        if model is None:
            return False, None, "feasible status without model"
        assumptions_hard = [[int(a)] for a in w.request_assumptions]
        chk = check_model(model, self._hard_clauses + assumptions_hard, self._softs, reported_cost=cost)
        if self._validate_model and not chk.hards_ok:
            return False, None, "model violates hard clauses"
        final_cost = cost
        if self._recompute_cost:
            final_cost = chk.recomputed_cost
        elif cost is None:
            final_cost = chk.recomputed_cost
        if (not self._recompute_cost) and (cost is not None) and self._validate_model and chk.reported_cost_matches is False:
            return False, None, f"reported cost {cost} != recomputed {chk.recomputed_cost}"
        return True, final_cost, None

    def _handle_invalid(self, solver_name: str, reason: str) -> None:
        if self._invalid_result_policy == "ignore":
            return
        msg = f"PortfolioSolver dropped invalid result from {solver_name}: {reason}"
        if self._invalid_result_policy == "raise":
            raise RuntimeError(msg)
        if self._invalid_result_policy in {"warn_drop", "drop"} and self._verbose_invalid:
            warnings.warn(msg, RuntimeWarning, stacklevel=2)

    def _apply_worker_result(self, w: _WorkerProc) -> Optional[dict[str, Any]]:
        detail: dict[str, Any] = {
            "solver": w.solver_name,
            "worker_class_path": w.worker_class_path,
            "elapsed_s": w.elapsed_s,
            "exit_code": w.exit_code,
            "timed_out": w.timed_out,
            "interrupted": w.interrupted,
            "killed": w.killed,
        }

        if w.timed_out and w.response is None:
            detail["status"] = "TIMEOUT"
            self._last_run_details.append(detail)
            return None

        resp = w.response
        if resp is None and w.exit_code in {10, 20, 30, 40, 50}:
            st, obj, model = parse_maxsat_cli_output((w.stdout_raw or b"").decode("utf-8", errors="replace"), num_vars=self._num_vars)
            if st is None:
                st = {10: SolveStatus.INTERRUPTED_SAT, 20: SolveStatus.UNSAT, 30: SolveStatus.OPTIMUM}.get(w.exit_code, SolveStatus.ERROR)
            status = st
            cost = None if obj is None else int(obj)
            model_list = None if model is None else [int(x) for x in model]
            ok, final_cost, invalid_reason = self._validate_candidate(w, status, model_list, cost)
            if not ok:
                self._handle_invalid(w.solver_name, invalid_reason or "invalid result")
                detail["status"] = "INVALID"
                detail["invalid_reason"] = invalid_reason
                self._last_run_details.append(detail)
                return None
            detail.update({"status": status.name, "cost": final_cost})
            self._last_run_details.append(detail)
            return {"solver": w.solver_name, "status": status, "cost": final_cost, "model": model_list}

        if resp is None:
            detail["status"] = "ERR"
            if w.protocol_error:
                detail["protocol_error"] = w.protocol_error
            self._last_run_details.append(detail)
            return None

        if not resp.get("ok", False):
            detail["status"] = "ERR"
            detail["error"] = resp.get("error")
            detail["error_type"] = resp.get("error_type")
            self._last_run_details.append(detail)
            return None

        try:
            status = SolveStatus(int(resp["status"]))
        except Exception:
            detail["status"] = "ERR"
            detail["error"] = "invalid status"
            self._last_run_details.append(detail)
            return None

        model = resp.get("model")
        model_list = None if model is None else [int(x) for x in model]
        cost = None
        if resp.get("cost") is not None:
            try:
                cost = int(resp["cost"])
            except Exception:
                cost = None
        ok, final_cost, invalid_reason = self._validate_candidate(w, status, model_list, cost)
        if not ok:
            self._handle_invalid(w.solver_name, invalid_reason or "invalid result")
            detail["status"] = "INVALID"
            detail["invalid_reason"] = invalid_reason
            self._last_run_details.append(detail)
            return None

        detail.update({"status": status.name, "cost": final_cost})
        self._last_run_details.append(detail)
        return {"solver": w.solver_name, "status": status, "cost": final_cost, "model": model_list}

    def _is_strict_improvement(
        self,
        prev_best: Optional[dict[str, Any]],
        new_best: Optional[dict[str, Any]],
    ) -> bool:
        if new_best is None:
            return False
        if prev_best is None:
            return True
        if new_best is prev_best:
            return False
        prev_cost = prev_best.get("cost")
        new_cost = new_best.get("cost")
        if new_cost is None:
            return False
        if prev_cost is None:
            return True
        return int(new_cost) < int(prev_cost)

    def _invoke_callback(self, event: PortfolioEvent):
        cb = self._callback
        if cb is None:
            return None
        try:
            if self._callback_accepts_event:
                return cb(event)
            return cb()
        except Exception:
            # Callback failures are interpreted as STOP by design.
            return CallbackAction.STOP

    def _apply_callback_action(
        self,
        action,
        *,
        event: PortfolioEvent,
        now: float,
        t0: float,
        overall_deadline: Optional[float],
        active: set[int],
        workers: list[_WorkerProc],
    ) -> Optional[float]:
        if action is None or action == CallbackAction.CONTINUE:
            return overall_deadline

        if action == CallbackAction.STOP:
            for i in list(active):
                self._timeout_worker(workers[i])
                self._apply_worker_result(workers[i])
                active.discard(i)
            return overall_deadline

        if action == CallbackAction.DROP_CURRENT:
            wid = event.worker_id
            if wid is not None and int(wid) in active:
                self._timeout_worker(workers[int(wid)])
                self._apply_worker_result(workers[int(wid)])
                active.discard(int(wid))
            return overall_deadline

        if isinstance(action, AdjustTimeout):
            new_timeout = max(0.0, float(action.new_timeout_s))
            mode = str(action.mode).lower()
            if mode == "absolute":
                new_deadline = t0 + new_timeout
            elif mode == "relative":
                new_deadline = now + new_timeout
            else:
                return overall_deadline
            overall_deadline = float(new_deadline)
            for i in list(active):
                workers[i].deadline_s = min(float(workers[i].deadline_s), float(overall_deadline))
            return overall_deadline

        return overall_deadline

    def solve(self, assumptions: Optional[List[int]] = None, raise_on_abnormal: bool = False) -> bool:
        self._require_open()
        self._invalidate()
        assumps = [int(a) for a in assumptions] if assumptions else []
        for lit in assumps:
            if lit == 0:
                raise ValueError("Assumptions must be non-zero integers.")
            while abs(lit) > self._num_vars:
                self.new_var()

        max_parallel = self._max_workers if self._max_workers > 0 else len(self._solver_classes)
        pending_classes = list(self._solver_classes)
        workers: list[_WorkerProc] = []
        while pending_classes and len(workers) < max_parallel:
            w = self._spawn_worker(pending_classes.pop(0), assumps)
            if w is not None:
                workers.append(w)
        if not workers:
            self._status = SolveStatus.ERROR
            self._last_error = "No available solver workers"
            if raise_on_abnormal:
                raise RuntimeError(self._last_error)
            return False

        t0 = time.monotonic()
        overall_deadline = None if self._overall_timeout_s <= 0 else (t0 + self._overall_timeout_s)
        best: Optional[dict[str, Any]] = None
        saw_trusted_unsat = False
        active = set(range(len(workers)))
        next_callback_s = t0 + float(self.CALLBACK_HEARTBEAT_S)
        pending_incumbent_event: Optional[PortfolioEvent] = None

        try:
            while active:
                now = time.monotonic()
                if overall_deadline is not None and now >= overall_deadline:
                    for i in list(active):
                        self._timeout_worker(workers[i])
                        active.discard(i)
                    break

                progressed = False
                for i in list(active):
                    w = workers[i]
                    if now >= w.deadline_s:
                        self._timeout_worker(w)
                        cand = self._apply_worker_result(w)
                        if cand:
                            prev_best = best
                            best = self._choose_best(best, cand)
                            if self._is_strict_improvement(prev_best, best):
                                pending_incumbent_event = PortfolioEvent(
                                    event_type="INCUMBENT",
                                    elapsed_s=max(0.0, float(now - t0)),
                                    worker_id=int(i),
                                    cost=None if best.get("cost") is None else int(best["cost"]),
                                    model=None if best.get("model") is None else list(best["model"]),
                                    is_optimal=(best.get("status") == SolveStatus.OPTIMUM),
                                )
                        active.discard(i)
                        progressed = True
                        continue
                    self._finalize_worker(w)
                    if w.done:
                        cand = self._apply_worker_result(w)
                        if cand:
                            prev_best = best
                            best = self._choose_best(best, cand)
                            if self._is_strict_improvement(prev_best, best):
                                pending_incumbent_event = PortfolioEvent(
                                    event_type="INCUMBENT",
                                    elapsed_s=max(0.0, float(now - t0)),
                                    worker_id=int(i),
                                    cost=None if best.get("cost") is None else int(best["cost"]),
                                    model=None if best.get("model") is None else list(best["model"]),
                                    is_optimal=(best.get("status") == SolveStatus.OPTIMUM),
                                )
                            st = cand["status"]
                            if st == SolveStatus.UNSAT and _solver_proves_unsat(w.worker_class_path):
                                saw_trusted_unsat = True
                            if self._should_early_stop(cand, w.worker_class_path):
                                for j in list(active):
                                    if j != i:
                                        self._timeout_worker(workers[j])
                                        self._apply_worker_result(workers[j])
                                        active.discard(j)
                                active.discard(i)
                                progressed = True
                                break
                        else:
                            # trust UNSAT only if parsed/structured candidate was unavailable -> no.
                            pass
                        active.discard(i)
                        if pending_classes:
                            nw = self._spawn_worker(pending_classes.pop(0), assumps)
                            if nw is not None:
                                workers.append(nw)
                                active.add(len(workers) - 1)
                        progressed = True

                now2 = time.monotonic()
                if self._callback is not None and now2 >= next_callback_s:
                    evt = pending_incumbent_event
                    if evt is None:
                        evt = PortfolioEvent(
                            event_type="HEARTBEAT",
                            elapsed_s=max(0.0, float(now2 - t0)),
                            worker_id=None,
                            cost=None,
                            model=None,
                            is_optimal=False,
                        )
                    pending_incumbent_event = None
                    action = self._invoke_callback(evt)
                    overall_deadline = self._apply_callback_action(
                        action,
                        event=evt,
                        now=now2,
                        t0=t0,
                        overall_deadline=overall_deadline,
                        active=active,
                        workers=workers,
                    )
                    next_callback_s = now2 + float(self.CALLBACK_HEARTBEAT_S)
                if not progressed:
                    time.sleep(0.01)
        finally:
            for w in workers:
                try:
                    if w.proc.poll() is None:
                        self._timeout_worker(w)
                    if not w.done:
                        self._finalize_worker(w)
                except Exception:
                    pass
                w.cleanup()

        if self._callback is not None and pending_incumbent_event is not None:
            _ = self._invoke_callback(pending_incumbent_event)

        if best is not None and is_feasible(best["status"]):
            self._model = list(best["model"]) if best.get("model") is not None else None
            self._last_cost = None if best.get("cost") is None else int(best["cost"])
            self._last_solver_name = str(best["solver"])
            if best["status"] == SolveStatus.OPTIMUM:
                self._status = SolveStatus.OPTIMUM
            else:
                self._status = SolveStatus.INTERRUPTED_SAT
            return True

        if saw_trusted_unsat:
            self._status = SolveStatus.UNSAT
            return False

        # No valid result found.
        any_timeout = any(d.get("status") == "TIMEOUT" for d in self._last_run_details)
        self._status = SolveStatus.INTERRUPTED if any_timeout else SolveStatus.ERROR
        self._last_error = "No valid portfolio result"
        if raise_on_abnormal:
            raise RuntimeError(self._last_error)
        return False

    def _choose_best(self, cur: Optional[dict[str, Any]], cand: dict[str, Any]) -> dict[str, Any]:
        if cur is None:
            return cand
        cst = cand.get("status")
        rst = cur.get("status")
        # Prefer OPTIMUM over non-optimum if same/unknown cost.
        if cst == SolveStatus.OPTIMUM and rst != SolveStatus.OPTIMUM:
            if cand.get("cost") is not None and cur.get("cost") is not None:
                if int(cand["cost"]) > int(cur["cost"]):
                    return cur
            return cand
        if cand.get("cost") is None:
            return cur
        if cur.get("cost") is None:
            return cand
        return cand if int(cand["cost"]) < int(cur["cost"]) else cur

    def _should_early_stop(self, cand: dict[str, Any], worker_class_path: str) -> bool:
        pol = self._selection_policy
        st: SolveStatus = cand["status"]
        if pol == "first_valid":
            return is_feasible(st)
        if pol == "best_valid_until_timeout":
            return False
        if pol == "first_optimal_or_best_until_timeout":
            return st == SolveStatus.OPTIMUM and _solver_proves_optimum(worker_class_path)
        return False

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
            raise RuntimeError("Model is not available.")
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
            raise RuntimeError("Model is only available for feasible status.")
        return list(self._model) if self._model is not None else None

    def signature(self) -> str:
        names = ", ".join(cls.__name__ for cls in self._solver_classes)
        return f"PortfolioSolver[{self._selection_policy}]({names})"

    def close(self) -> None:
        self._closed = True
        self._ops.clear()
        self._hard_clauses.clear()
        self._softs.clear()
        self._invalidate()

    def _load_initial_formula(self, formula) -> None:
        for cl in getattr(formula, "hard", []):
            self.add_clause(list(map(int, cl)))
        soft_attr = getattr(formula, "soft", [])
        wghts = getattr(formula, "wght", None)
        if wghts is not None and len(wghts) == len(soft_attr) and (not soft_attr or not isinstance(soft_attr[0], tuple)):
            for cl, w in zip(soft_attr, wghts):
                cl2 = list(map(int, cl))
                if len(cl2) == 1:
                    self.add_soft_unit(cl2[0], int(w))
                else:
                    b = self.new_var()
                    self.add_soft_relaxed(cl2, int(w), relax_var=b)
            return
        for item in soft_attr:
            if isinstance(item, tuple) and len(item) >= 2:
                cl, w = item[0], item[1]
            else:
                cl, w = item, 1
            cl2 = list(map(int, cl))
            if len(cl2) == 1:
                self.add_soft_unit(cl2[0], int(w))
            else:
                b = self.new_var()
                self.add_soft_relaxed(cl2, int(w), relax_var=b)

    @property
    def last_run_details(self) -> list[dict[str, Any]]:
        return [dict(x) for x in self._last_run_details]


class _AutoPortfolioSolver(PortfolioSolver):
    _NAMESPACE_MODULES: tuple[str, ...] = ()

    def __init__(
        self,
        formula=None,
        *,
        include: Sequence[type] | None = None,
        exclude: Sequence[type] | None = None,
        **kwargs,
    ):
        classes = _discover_solver_classes_from_namespaces(
            self._NAMESPACE_MODULES,
            include=include,
            exclude=exclude,
        )
        if not classes:
            raise ValueError(f"No solver classes discovered for preset {type(self).__name__}")
        super().__init__(classes, formula=formula, **kwargs)

    @classmethod
    def discovered_solver_classes(
        cls,
        *,
        include: Sequence[type] | None = None,
        exclude: Sequence[type] | None = None,
    ) -> list[type]:
        return _discover_solver_classes_from_namespaces(
            cls._NAMESPACE_MODULES, include=include, exclude=exclude
        )


class CompletePortfolioSolver(_AutoPortfolioSolver):
    """Auto-discovered portfolio over incremental + non-incremental (complete/reentrant) namespaces."""

    _NAMESPACE_MODULES = ("hermax.incremental", "hermax.non_incremental")


class IncompletePortfolioSolver(_AutoPortfolioSolver):
    """Auto-discovered portfolio over incomplete subprocess-backed namespace."""

    _NAMESPACE_MODULES = ("hermax.non_incremental.incomplete",)


class PerformancePortfolioSolver(_AutoPortfolioSolver):
    """Auto-discovered mixed portfolio over complete + incomplete namespaces."""

    _NAMESPACE_MODULES = (
        "hermax.incremental",
        "hermax.non_incremental",
        "hermax.non_incremental.incomplete",
    )
