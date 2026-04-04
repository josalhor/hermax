from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible
from hermax.non_incremental.incomplete import OpenWBOInc, NuWLSCIBR
import pytest


def _require_nuwls():
    if not NuWLSCIBR.is_available():
        import pytest

        pytest.skip("NuWLS-c-IBR binary is not available in this environment.")


def test_incomplete_namespace_openwboinc_alias_imports():
    # Public API relocation alias should remain importable.
    if not OpenWBOInc.is_available():
        pytest.skip("OpenWBOInc native module not built in minimal SPB-only configuration.")
    solver = OpenWBOInc()
    solver.close()


def test_nuwls_basic_weighted_smoke():
    _require_nuwls()
    s = NuWLSCIBR()
    s.add_clause([1])               # hard: x1 must be true
    s.add_soft_unit(-1, 3)          # penalize x1 = True
    ok = s.solve()
    assert ok is True
    assert is_feasible(s.get_status())
    assert s.get_status() in (SolveStatus.INTERRUPTED_SAT, SolveStatus.OPTIMUM)
    assert s.get_cost() == 3
    assert s.val(1) == 1
    model = s.get_model()
    assert model is not None
    assert 1 in model
    s.close()


def test_nuwls_assumptions_emulated_by_hard_units():
    _require_nuwls()
    s = NuWLSCIBR()
    s.add_clause([1, 2])            # hard
    s.add_soft_unit(-1, 5)          # cost if x1=True
    s.add_soft_unit(-2, 7)          # cost if x2=True

    ok = s.solve([1, -2])           # force x1=True, x2=False
    assert ok is True
    assert is_feasible(s.get_status())
    assert s.val(1) == 1
    assert s.val(2) == -1
    assert s.get_cost() == 5
    s.close()
