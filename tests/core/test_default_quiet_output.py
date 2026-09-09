"""Small smoke checks for the default solver output contract."""

import ctypes
from importlib import import_module

import pytest


# Keep imports lazy: optional native backends may be absent in a wheel.
MATRIX_OUTPUT_SOLVERS = {
    "CoreTrail": ("hermax.core", "CoreTrailSolver", False),
    "Aperture": ("hermax.core", "ApertureSolver", False),
    "UWrMaxSAT": ("hermax.core", "UWrMaxSATSolver", False),
    "UWrMaxSATComp": ("hermax.core.uwrmaxsat_comp_py", "UWrMaxSATCompSolver", False),
    "CASHWMaxSAT": ("hermax.core.cashwmaxsat_py", "CASHWMaxSATSolver", False),
    "EvalMaxSAT": ("hermax.core.evalmaxsat_latest_py", "EvalMaxSATLatestSolver", False),
    "EvalMaxSATLatest": ("hermax.core.evalmaxsat_latest_py", "EvalMaxSATLatestSolver", False),
    "EvalMaxSATIncr": ("hermax.core.evalmaxsat_incr_py", "EvalMaxSATIncrSolver", False),
    "EvalMaxSATIncrReentrant": ("hermax.core.evalmaxsat_incr_py", "EvalMaxSATIncrReentrant", False),
    "IMaxHS": ("hermax.core", "IMaxHSSolver", False),
    "MaxHS": ("hermax.core", "MaxHSSolver", False),
    "RC2Reentrant": ("hermax.core", "RC2Reentrant", False),
    "CGSS": ("hermax.non_incremental", "CGSS", False),
    "OpenWBO-OLL": ("hermax.core.openwbo_py", "OLLSolver", False),
    "OpenWBO-PartMSU3": ("hermax.core.openwbo_py", "PartMSU3Solver", False),
    "OpenWBO-Auto": ("hermax.core.openwbo_py", "AutoOpenWBOSolver", False),
    "OpenWBOInc": ("hermax.non_incremental.incomplete", "OpenWBOInc", True),
    "TTOpenWBOInc": ("hermax.non_incremental.incomplete", "TTOpenWBOInc", True),
    "SPB-MaxSAT-c-FPS": ("hermax.non_incremental.incomplete", "SPBMaxSATCFPS", True),
    "NuWLS-c-IBR": ("hermax.non_incremental.incomplete", "NuWLSCIBR", True),
    "Loandra": ("hermax.non_incremental.incomplete", "Loandra", True),
    "WMaxCDCL": ("hermax.core", "WMaxCDCLSolver", False),
}


def _matrix_solver(name):
    module_name, class_name, is_subprocess = MATRIX_OUTPUT_SOLVERS[name]
    try:
        solver_class = getattr(import_module(module_name), class_name)
    except (ImportError, AttributeError) as exc:
        pytest.skip(f"{name} is not available: {exc}")
    if hasattr(solver_class, "is_available") and not solver_class.is_available():
        pytest.skip(f"{name} is not available in this build")
    return solver_class, is_subprocess


def _assert_quiet(capfd, run):
    run()
    # Native solvers may buffer printf/cout output until the C stream is flushed.
    ctypes.CDLL(None).fflush(None)
    captured = capfd.readouterr()
    assert captured.out == "", f"unexpected solver stdout:\n{captured.out}"
    assert captured.err == "", f"unexpected solver stderr:\n{captured.err}"


def test_rc2_default_is_quiet(capfd):
    from pysat.formula import WCNF
    from hermax.core.rc2.rc2 import RC2

    def run():
        formula = WCNF()
        formula.append([1])
        formula.append([-1], weight=3)
        with RC2(formula) as solver:
            assert solver.compute() is not None

    _assert_quiet(capfd, run)


def test_rc2_explicit_verbose_output_is_captured(capfd):
    from pysat.formula import WCNF
    from hermax.core.rc2.rc2 import RC2

    formula = WCNF()
    formula.append([1])
    formula.append([-1], weight=3)
    with RC2(formula, verbose=2) as solver:
        assert solver.compute() is not None

    ctypes.CDLL(None).fflush(None)
    captured = capfd.readouterr()
    assert "c formula:" in captured.out
    assert captured.err == ""


def test_uwrmaxsat_default_is_quiet(capfd):
    from hermax.core.uwrmaxsat_py.urmaxsat_solver import UWrMaxSATSolver

    def run():
        solver = UWrMaxSATSolver()
        try:
            solver.add_clause([1])
            assert solver.solve()
        finally:
            solver.close()

    _assert_quiet(capfd, run)


def test_evalmaxsat_default_is_quiet(capfd):
    pytest.importorskip("hermax.core.evalmaxsat_latest")
    from hermax.core.evalmaxsat_latest_py.evalmaxsat_solver import EvalMaxSATLatestSolver

    def run():
        solver = EvalMaxSATLatestSolver()
        try:
            solver.add_clause([1])
            assert solver.solve()
        finally:
            solver.close()

    _assert_quiet(capfd, run)


def test_cashwmaxsat_default_is_quiet(capfd):
    pytest.importorskip("hermax.core.cashwmaxsat")
    from hermax.core.cashwmaxsat_py.cashwmaxsat_solver import CASHWMaxSATSolver

    def run():
        solver = CASHWMaxSATSolver()
        try:
            solver.add_clause([1])
            assert solver.solve()
        finally:
            solver.close()

    _assert_quiet(capfd, run)


def test_wmaxcdcl_default_is_quiet(capfd):
    pytest.importorskip("hermax.core.wmaxcdcl")
    from hermax.core.wmaxcdcl_py.wmaxcdcl_solver import WMaxCDCLSolver

    def run():
        solver = WMaxCDCLSolver()
        try:
            solver.add_clause([1])
            assert solver.solve()
        finally:
            solver.close()

    _assert_quiet(capfd, run)


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    [
        ("hermax.core.nuwls_c_ibr_py.nuwls_c_ibr_subprocess", "NuWLSCIBR"),
        ("hermax.core.tt_openwbo_inc_py.tt_openwbo_inc_subprocess", "TTOpenWBOInc"),
        ("hermax.core.spb_maxsat_c_fps_py.spb_maxsat_c_fps_subprocess", "SPBMaxSATCFPS"),
    ],
)
def test_subprocess_solver_default_worker_has_no_diagnostics(module_name, class_name):
    module = import_module(module_name)
    solver_class = getattr(module, class_name)
    if hasattr(solver_class, "is_available") and not solver_class.is_available():
        pytest.skip(f"{class_name} is not available in this build")

    solver = solver_class()
    try:
        solver.add_clause([1])
        assert solver.solve()
        assert not any(
            line.startswith("c ")
            for line in solver._last_worker_stdout.splitlines()
        )
    finally:
        solver.close()


@pytest.mark.parametrize(
    "solver_name",
    [pytest.param(name, id=name) for name in MATRIX_OUTPUT_SOLVERS],
)
def test_matrix_solver_default_output_is_quiet(capfd, solver_name):
    solver_class, is_subprocess = _matrix_solver(solver_name)
    solver = solver_class()
    worker_stdout = ""
    try:
        solver.add_clause([1])
        assert solver.solve()
        worker_stdout = getattr(solver, "_last_worker_stdout", "")
    finally:
        solver.close()

    ctypes.CDLL(None).fflush(None)
    captured = capfd.readouterr()
    assert captured.out == "", f"{solver_name} emitted stdout:\n{captured.out}"
    assert captured.err == "", f"{solver_name} emitted stderr:\n{captured.err}"

    if is_subprocess:
        diagnostics = [
            line
            for line in worker_stdout.splitlines()
            if line.startswith("c ")
        ]
        assert not diagnostics, f"{solver_name} emitted diagnostics:\n{diagnostics}"


def test_model_default_is_quiet(capfd):
    from hermax.model import Model

    def run():
        model = Model()
        x = model.bool("x")
        model &= x
        assert model.solve().ok

    _assert_quiet(capfd, run)
