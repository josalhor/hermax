from __future__ import annotations

import importlib
import sysconfig

import pytest


def _is_wasm_build() -> bool:
    soabi = (sysconfig.get_config_var("SOABI") or "").lower()
    plat = (sysconfig.get_platform() or "").lower()
    return ("emscripten" in soabi) or ("wasm" in soabi) or ("emscripten" in plat) or ("wasm" in plat)


if not _is_wasm_build():
    pytest.skip("Pyodide/WASM-specific test module", allow_module_level=True)


def _exercise_solver(solver):
    # Hard clauses force x1=True and x2=False.
    solver.add_clause([1])
    solver.add_clause([-2])
    # Soft clauses are then forced unsatisfied by the hard clauses.
    solver.add_soft_unit(-1, 5)
    solver.add_soft_unit(2, 2)

    assert solver.solve() is True
    assert solver.get_cost() == 7
    assert solver.val(1) == 1
    assert solver.val(2) == -1


def test_rc2_and_cgss_work_in_wasm_build():
    from hermax.core import RC2Reentrant, CGSSSolver, CGSSPMRESSolver
    from hermax.non_incremental import RC2, CGSS, CGSSPMRES

    for cls in (RC2Reentrant, CGSSSolver, CGSSPMRESSolver, RC2, CGSS, CGSSPMRES):
        solver = cls()
        _exercise_solver(solver)
        solver.close()


def test_unavailable_native_solvers_raise_clear_import_error():
    core = importlib.import_module("hermax.core")
    unavailable = [
        "UWrMaxSATSolver",
        "UWrMaxSATCompSolver",
        "CASHWMaxSATSolver",
        "EvalMaxSATLatestSolver",
        "EvalMaxSATIncrSolver",
        "WMaxCDCLSolver",
        "SPBMaxSATCFPSSolver",
        "NuWLSCIBRSolver",
        "LoandraSolver",
    ]

    for name in unavailable:
        with pytest.raises(ImportError) as ei:
            getattr(core, name)
        msg = str(ei.value).lower()
        assert name.lower() in msg
        assert "not available" in msg
