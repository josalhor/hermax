"""Regression checks for the Python C API migration, using rebuilt extensions."""
import importlib
import importlib.util

import pytest


SOLVERS = [
    ("_aperture_native", "Aperture"),
    ("openwbo", "OLL"), ("openwbo", "PartMSU3"), ("openwbo", "Auto"),
    ("openwbo_inc", "OpenWBOInc"), ("tt_openwbo_inc", "TTOpenWBOInc"),
    ("urmaxsat_py", "UWrMaxSAT"), ("urmaxsat_comp_py", "UWrMaxSAT"),
    ("cashwmaxsat", "CASHWMaxSAT"),
    ("evalmaxsat_latest", "EvalMaxSAT"), ("evalmaxsat_incr", "EvalMaxSATIncr"),
    ("wmaxcdcl", "WMaxCDCL"), ("spb_maxsat_c_fps", "SPBMaxSATCFPS"),
    ("nuwls_c_ibr", "NuWLSCIBR"), ("loandra", "Loandra"),
    ("maxhs_py", "MaxHS"), ("imaxhs_py", "IMaxHS"),
]


def native_type(module, name):
    fullname = "hermax.core." + module
    if importlib.util.find_spec(fullname) is None:
        pytest.skip(f"{fullname} is not included in this build")
    return getattr(importlib.import_module(fullname), name)


@pytest.mark.parametrize("module,name", SOLVERS)
@pytest.mark.parametrize("arguments", ["positional", "keyword"])
def test_native_constructors_reject_unknown_arguments(module, name, arguments):
    cls = native_type(module, name)
    with pytest.raises(TypeError):
        if arguments == "positional":
            cls(123)
        else:
            cls(unsupported_option=True)


@pytest.mark.parametrize("module,name", SOLVERS)
def test_native_clauses_reject_literal_that_cannot_be_negated(module, name):
    solver = native_type(module, name)()
    add = getattr(solver, "addClause", None) or solver.add_clause
    with pytest.raises((ValueError, OverflowError)):
        add([-2**31])


def test_evalmaxsat_incremental_rejects_negative_unsigned_weight():
    solver = native_type("evalmaxsat_incr", "EvalMaxSATIncr")()
    with pytest.raises((ValueError, OverflowError)):
        solver.addSoftLit(lit=1, weight=-1)


def test_evalmaxsat_incremental_preserves_keyword_arguments():
    solver = native_type("evalmaxsat_incr", "EvalMaxSATIncr")()
    solver.addClause(clause=[1])
    solver.assume(assumptions=[1])
    assert solver.solve() == 30
    assert solver.getValue(lit=1) is True


def test_integer_sum_state_counter_preserves_64_bit_weights():
    from hermax.internal import _integer_sum_native as native

    weights = [1, 3, 7]
    scale = 2**40
    expected = native.count_states(weights, 4, native.LEQ, 0)
    assert native.count_states([w * scale for w in weights], 4 * scale, native.LEQ, 0) == expected


@pytest.mark.parametrize("module,name", [
    ("spb_maxsat_c_fps", "SPBMaxSATCFPS"), ("nuwls_c_ibr", "NuWLSCIBR"),
])
@pytest.mark.parametrize("case", ["zero_cost", "positive_cost", "unsat"])
def test_mcs_terminal_results_do_not_continue_into_lsu(module, name, case):
    import subprocess
    import sys

    native_type(module, name)  # Skip only when this solver is not built.
    code = f'''
from hermax.core.{module} import {name}
s = {name}()
s.newVar()
s.addClause([1])
if {case!r} == "unsat":
    s.addClause([-1])
    assert s.solve() is False
    assert s.getStatus() == 20
else:
    if {case!r} == "positive_cost":
        s.addClause([-1], 3)
    assert s.solve() is True
    assert s.getStatus() == 30
    assert 1 in s.getModel()
    assert s.getCost() == (3 if {case!r} == "positive_cost" else 0)
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module,name", [
    ("spb_maxsat_c_fps", "SPBMaxSATCFPS"), ("nuwls_c_ibr", "NuWLSCIBR"),
])
def test_mcs_wrappers_hide_internal_relaxation_variables(module, name):
    native_type(module, name)
    from hermax.non_incremental import incomplete

    solver = getattr(incomplete, name)(default_time_limit=5)
    try:
        solver.add_clause([1])
        solver.add_soft_unit(-1, 3)
        assert solver.solve()
        assert solver.get_model() == [1]
        assert solver.get_cost() == 3
    finally:
        solver.close()
