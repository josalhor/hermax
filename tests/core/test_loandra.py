from hermax.core.ipamir_solver_interface import SolveStatus, is_feasible
from hermax.non_incremental.incomplete import Loandra


def _require_loandra():
    if not Loandra.is_available():
        import pytest

        pytest.skip("Loandra native binding is not available in this build.")


def test_loandra_basic_weighted_smoke():
    _require_loandra()
    s = Loandra(timeout_s=4.0, timeout_grace_s=0.5)
    s.add_clause([1])          # hard
    s.add_soft_unit(-1, 3)     # pay if x1 = true
    ok = s.solve()
    assert ok is True
    assert is_feasible(s.get_status())
    assert s.get_status() in (SolveStatus.INTERRUPTED_SAT, SolveStatus.OPTIMUM)
    assert s.get_cost() == 3
    assert s.val(1) == 1
    model = s.get_model()
    assert model is not None and 1 in model
    s.close()


def test_loandra_assumptions_emulated_by_hard_units():
    _require_loandra()
    s = Loandra(timeout_s=4.0, timeout_grace_s=0.5)
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
