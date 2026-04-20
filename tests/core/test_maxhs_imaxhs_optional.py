from __future__ import annotations

import pytest

from hermax.core import IMaxHSSolver, MaxHSSolver


@pytest.mark.parametrize("solver_cls", [IMaxHSSolver, MaxHSSolver])
def test_optional_solver_availability_contract(solver_cls):
    avail = solver_cls.is_available()
    assert isinstance(avail, bool)

    if avail:
        solver = solver_cls()
        solver.close()
        return

    with pytest.raises(RuntimeError) as ei:
        solver_cls()
    msg = str(ei.value).lower()
    assert "not available" in msg
    assert "cplex" in msg


@pytest.mark.parametrize("solver_cls", [IMaxHSSolver, MaxHSSolver])
def test_weight_int64_bounds_enforced(solver_cls):
    if not solver_cls.is_available():
        pytest.skip(f"{solver_cls.__name__} not available in this build")

    solver = solver_cls()
    solver.add_clause([1])
    solver.add_soft_unit(-1, (1 << 63) - 1)
    assert solver.solve() is True
    assert solver.get_cost() == (1 << 63) - 1
    with pytest.raises((OverflowError, ValueError)):
        solver.set_soft(-1, 1 << 63)
    solver.close()


def test_maxhs_val_sign_semantics():
    if not MaxHSSolver.is_available():
        pytest.skip("MaxHSSolver not available in this build")

    solver = MaxHSSolver()
    solver.add_clause([1])
    assert solver.solve() is True
    assert solver.val(1) == 1
    assert solver.val(-1) == -1
    solver.close()
