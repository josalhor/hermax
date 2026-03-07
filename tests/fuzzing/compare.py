from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .model import WeightedCNF

CRASH_CODES = {134, 135, 136, 137, 139}


@dataclass
class SolverOutcome:
    solver_id: str
    exit_code: int | None
    timed_out: bool
    duration_s: float
    payload: dict
    stdout: str = ""
    stderr: str = ""
    fault: str | None = None
    notes: str = ""


class WCNFCompare:
    def __init__(self, out_dir: Path, per_solver_timeout_s: float, run_id: str, progress_cb=None):
        self.out_dir = out_dir
        self.per_solver_timeout_s = per_solver_timeout_s
        self.run_id = run_id
        self.progress_cb = progress_cb
        self.logs_dir = self.out_dir / "fault_logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _run_solver(self, solver_id: str, case_json: Path, assumptions: list[int] | None = None) -> SolverOutcome:
        env = os.environ.copy()
        lib_paths: list[str] = []
        for p in sys.path:
            base = Path(p)
            if not base.exists():
                continue
            for d in ("hermax.libs", "pymaxsat.libs"):
                cand = base / d
                if cand.is_dir():
                    lib_paths.append(str(cand.resolve()))

        # Fallback for project-local virtualenv layouts.
        venv_site = sorted(Path.cwd().glob("venv/lib/python*/site-packages"))
        for base in venv_site:
            for d in ("hermax.libs", "pymaxsat.libs"):
                cand = base / d
                if cand.is_dir():
                    lib_paths.append(str(cand.resolve()))

        if lib_paths:
            dedup: list[str] = []
            seen = set()
            for p in lib_paths:
                if p not in seen:
                    dedup.append(p)
                    seen.add(p)
            old = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = ":".join(dedup + ([old] if old else []))

        cmd = [
            sys.executable,
            "-m",
            "tests.fuzzing.worker",
            "--solver",
            solver_id,
            "--case",
            str(case_json),
        ]
        if assumptions:
            cmd.extend(["--assumptions", ",".join(str(int(x)) for x in assumptions)])
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.per_solver_timeout_s,
                env=env,
            )
            elapsed = time.monotonic() - start
            payload = {}
            if proc.stdout.strip():
                for line in reversed(proc.stdout.splitlines()):
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        payload = json.loads(line)
                        break
                    except Exception:
                        continue
            return SolverOutcome(
                solver_id=solver_id,
                exit_code=proc.returncode,
                timed_out=False,
                duration_s=elapsed,
                payload=payload,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return SolverOutcome(
                solver_id=solver_id,
                exit_code=None,
                timed_out=True,
                duration_s=elapsed,
                payload={},
                fault="TIMEOUT",
                notes=f"timeout>{self.per_solver_timeout_s}s",
            )

    def _classify_crash(self, oc: SolverOutcome) -> str | None:
        if oc.timed_out:
            return "TIMEOUT"
        code = oc.exit_code
        if code is None:
            return None
        if code < 0:
            try:
                sig_name = signal.Signals(-code).name
            except Exception:
                sig_name = f"SIG{-code}"
            oc.notes = sig_name
            return "CRASH"
        if code in CRASH_CODES:
            return "CRASH"
        return None

    @staticmethod
    def _is_unavailable_error(msg: str | None) -> bool:
        if not msg:
            return False
        m = msg.lower()
        needles = [
            "importerror:",
            "cannot open shared object file",
            "can't instantiate abstract class",
            "has no attribute",
            "modulenotfounderror:",
            "unsupportedcaseerror:",
            "only supports soft weight 1",
        ]
        return any(n in m for n in needles)

    def compare_case(
        self,
        wcnf: WeightedCNF,
        case_json: Path,
        solvers: list[str],
        assumptions: list[int] | None = None,
        *,
        run_id_override: str | None = None,
        emit_fault_logs: bool = True,
    ) -> tuple[list[SolverOutcome], dict]:
        outcomes = []
        total = len(solvers)
        for idx, s in enumerate(solvers, start=1):
            if self.progress_cb is not None:
                self.progress_cb({"phase": "solve", "solver": s, "solver_idx": idx, "solver_total": total, "event": "start"})
            oc = self._run_solver(s, case_json, assumptions=assumptions)
            outcomes.append(oc)
            if self.progress_cb is not None:
                self.progress_cb({"phase": "solve", "solver": s, "solver_idx": idx, "solver_total": total, "event": "end"})

        # Compute o_model and o_min from valid hard-satisfying models.
        o_model: dict[str, int | None] = {}
        hard_ok: dict[str, bool] = {}
        for oc in outcomes:
            model = oc.payload.get("model") if oc.payload else None
            hard = wcnf.hard_satisfied(model)
            hard_ok[oc.solver_id] = hard
            o_model[oc.solver_id] = wcnf.soft_cost(model) if model is not None and hard else None

        valid = [v for v in o_model.values() if v is not None]
        o_min = min(valid) if valid else None

        run_id = run_id_override or self.run_id
        summary = {
            "run_id": run_id,
            "assumptions": [int(x) for x in (assumptions or [])],
            "o_min": o_min,
            "results": [],
        }

        for oc in outcomes:
            sid = oc.solver_id
            crash = self._classify_crash(oc)
            if crash:
                oc.fault = crash
            else:
                p = oc.payload or {}
                status = str(p.get("status_name", "UNKNOWN"))
                solver_error = p.get("error")
                model = p.get("model")
                osolver = p.get("o_solver")

                if solver_error:
                    if self._is_unavailable_error(str(solver_error)):
                        oc.fault = "SKIP_UNAVAILABLE"
                    else:
                        oc.fault = "SOLVER_EXCEPTION"
                elif (oc.exit_code is not None and oc.exit_code != 0) and not p:
                    oc.fault = "PROCESS_EXIT_NONZERO"
                elif model is not None and not hard_ok[sid]:
                    oc.fault = "SANITY_HARD_MISMATCH"
                elif status == "UNSAT" and o_min is not None:
                    oc.fault = "SANITY_UNSAT_MISMATCH"
                elif osolver is not None and o_model[sid] is not None and int(osolver) != int(o_model[sid]):
                    oc.fault = "CONSISTENCY_O_SOLVER_NEQ_O_MODEL"
                elif o_min is not None and o_model[sid] is not None and int(o_model[sid]) > int(o_min):
                    oc.fault = "BOUND_O_MODEL_GT_O_MIN"
                elif o_min is not None and osolver is not None and int(osolver) != int(o_min):
                    oc.fault = "BOUND_O_SOLVER_NEQ_O_MIN"

            rec = {
                "solver": sid,
                "exit_code": oc.exit_code,
                "timed_out": oc.timed_out,
                "duration_s": round(oc.duration_s, 6),
                "fault": oc.fault,
                "notes": oc.notes,
                "status_name": oc.payload.get("status_name") if oc.payload else None,
                "o_solver": oc.payload.get("o_solver") if oc.payload else None,
                "o_model": o_model[sid],
                "hard_ok": hard_ok[sid],
                "error": oc.payload.get("error") if oc.payload else None,
            }
            summary["results"].append(rec)

            if oc.fault and emit_fault_logs:
                fname = f"{run_id}__{sid}__{oc.fault}.log"
                path = self.logs_dir / fname
                lines = [
                    f"run_id={run_id}",
                    f"solver={sid}",
                    f"fault={oc.fault}",
                    f"exit_code={oc.exit_code}",
                    f"timed_out={oc.timed_out}",
                    f"notes={oc.notes}",
                    f"payload={json.dumps(oc.payload, sort_keys=True)}",
                    f"stderr={oc.stderr.strip()}",
                ]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return outcomes, summary
