from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible
from hermax.non_incremental.incomplete import TTOpenWBOInc
import pytest


def _require_tt_openwbo_inc():
    if not TTOpenWBOInc.is_available():
        pytest.skip("TT-Open-WBO-Inc native module is not available in this environment.")


def test_incomplete_namespace_tt_openwboinc_alias_imports():
    _require_tt_openwbo_inc()
    solver = TTOpenWBOInc()
    solver.close()


def test_tt_openwbo_inc_basic_weighted_smoke():
    _require_tt_openwbo_inc()
    s = TTOpenWBOInc()
    s.add_clause([1])
    s.add_soft_unit(-1, 3)
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


def test_tt_openwbo_inc_assumptions_emulated_by_hard_units():
    _require_tt_openwbo_inc()
    s = TTOpenWBOInc()
    s.add_clause([1, 2])
    s.add_soft_unit(-1, 5)
    s.add_soft_unit(-2, 7)

    ok = s.solve([1, -2])
    assert ok is True
    assert is_feasible(s.get_status())
    assert s.val(1) == 1
    assert s.val(2) == -1
    assert s.get_cost() == 5
    s.close()
