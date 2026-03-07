from __future__ import annotations

import argparse
import importlib
import json
import time
import traceback
from pathlib import Path

from .model import WeightedCNF
from .solver_registry import get_spec


class UnsupportedCaseError(RuntimeError):
    pass


def _load_solver(solver_id: str):
    spec = get_spec(solver_id)
    mod = importlib.import_module(spec.module)
    cls = getattr(mod, spec.cls)
    return cls()


def _prepare_solver(solver, wcnf: WeightedCNF) -> int:
    max_var = wcnf.nvars
    try:
        new_var = getattr(solver, "new_var")
        for _ in range(max_var):
            new_var()
    except Exception:
        pass

    const_cost = 0
    for cl in wcnf.hard:
        if cl:
            solver.add_clause(list(cl))
            continue
        # Encode empty hard clause by forcing contradiction on a fresh var.
        max_var += 1
        try:
            new_var = getattr(solver, "new_var")
            new_var()
        except Exception:
            pass
        solver.add_clause([max_var])
        solver.add_clause([-max_var])

    extra = max_var
    for cl, w in wcnf.soft:
        if not cl:
            const_cost += int(w)
            continue
        if len(cl) == 1:
            # Encode each unit soft independently as a relaxed clause.
            # This avoids soft-literal overwrite/update semantics across solvers
            # and prevents overflow from aggregating duplicate-unit weights.
            extra += 1
            solver.add_soft_relaxed([int(cl[0])], int(w), relax_var=extra)
        else:
            extra += 1
            solver.add_soft_relaxed(list(cl), int(w), relax_var=extra)
    return const_cost


def run_worker(solver_id: str, case_path: Path, assumptions: list[int] | None = None) -> dict:
    started = time.monotonic()
    wcnf = WeightedCNF.from_dict(json.loads(case_path.read_text(encoding="utf-8")))
    if solver_id == "OpenWBOInc":
        raise UnsupportedCaseError("OpenWBOInc disabled in fuzzing: wrapper incomplete for reliable comparison.")
    if solver_id == "OpenWBO-PartMSU3" and any(int(w) != 1 for _cl, w in wcnf.soft):
        raise UnsupportedCaseError("OpenWBO-PartMSU3 only supports unweighted soft clauses in this fuzzing mode.")
    solver = _load_solver(solver_id)
    out: dict = {
        "solver_id": solver_id,
        "status_name": "UNKNOWN",
        "feasible": False,
        "o_solver": None,
        "model": None,
        "error": None,
        "traceback": None,
    }
    try:
        const_cost = _prepare_solver(solver, wcnf)
        ok = solver.solve(assumptions=assumptions or None)
        out["feasible"] = bool(ok)
        try:
            out["status_name"] = str(getattr(solver.get_status(), "name", solver.get_status()))
        except Exception:
            out["status_name"] = "UNKNOWN"

        if out["feasible"]:
            try:
                out["o_solver"] = int(solver.get_cost()) + int(const_cost)
            except Exception:
                out["o_solver"] = None
            try:
                model = solver.get_model()
                out["model"] = [int(x) for x in model] if model is not None else None
            except Exception:
                out["model"] = None
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()
    finally:
        try:
            solver.close()
        except Exception:
            pass

    out["duration_s"] = time.monotonic() - started
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one solver on one WCNF case")
    parser.add_argument("--solver", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--assumptions", default="")
    args = parser.parse_args()

    assumptions = None
    if args.assumptions.strip():
        assumptions = [int(x) for x in args.assumptions.split(",") if x.strip()]

    try:
        result = run_worker(args.solver, Path(args.case), assumptions=assumptions)
    except Exception as exc:
        result = {
            "solver_id": args.solver,
            "status_name": "WORKER_ERROR",
            "feasible": False,
            "o_solver": None,
            "model": None,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "duration_s": 0.0,
        }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
