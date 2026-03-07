from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SolverSpec:
    solver_id: str
    module: str
    cls: str
    default_enabled: bool = True


SOLVER_SPECS: list[SolverSpec] = [
    SolverSpec("UWrMaxSAT", "hermax.core.uwrmaxsat_py", "UWrMaxSATSolver"),
    SolverSpec("UWrMaxSATComp", "hermax.core.uwrmaxsat_comp_py", "UWrMaxSATCompSolver"),
    SolverSpec("EvalMaxSAT", "hermax.core.evalmaxsat_latest_py", "EvalMaxSATLatestSolver"),
    SolverSpec("EvalMaxSATLatest", "hermax.core.evalmaxsat_latest_py", "EvalMaxSATLatestSolver"),
    SolverSpec("EvalMaxSATIncr", "hermax.core.evalmaxsat_incr_py", "EvalMaxSATIncrSolver"),
    SolverSpec("RC2Reentrant", "hermax.core.rc2.rc2_reentrant", "RC2Reentrant"),
    SolverSpec("OpenWBO-OLL", "hermax.core.openwbo_py", "OLLSolver"),
    SolverSpec("OpenWBO-PartMSU3", "hermax.core.openwbo_py", "PartMSU3Solver"),
    SolverSpec("OpenWBO-Auto", "hermax.core.openwbo_py", "AutoOpenWBOSolver"),
    SolverSpec("OpenWBOInc", "hermax.core.openwbo_inc_py", "OpenWBOIncSolver", default_enabled=False),
]


def solver_ids() -> list[str]:
    return [s.solver_id for s in SOLVER_SPECS if s.default_enabled]


def get_spec(solver_id: str) -> SolverSpec:
    for spec in SOLVER_SPECS:
        if spec.solver_id == solver_id:
            return spec
    raise KeyError(f"Unknown solver id: {solver_id}")
