from hermax.core.rc2.rc2_reentrant import RC2Reentrant


def test_set_soft_zero_removes_objective_term():
    s = RC2Reentrant()
    s.add_clause([1])          # force x1 = True
    s.add_soft_unit(-1, 5)     # penalize x1 = True by 5

    assert s.solve() is True
    assert s.get_cost() == 5

    s.set_soft(-1, 0)          # remove objective term
    assert s.solve() is True
    assert s.get_cost() == 0


def test_set_soft_zero_on_missing_literal_is_noop():
    s = RC2Reentrant()
    s.add_clause([1])
    s.set_soft(-1, 0)          # not present, should be a no-op

    assert s.solve() is True
    assert s.get_cost() == 0


def test_add_soft_unit_still_rejects_zero_weight():
    s = RC2Reentrant()
    try:
        s.add_soft_unit(-1, 0)
    except ValueError:
        pass
    else:
        raise AssertionError("add_soft_unit must reject zero weight")


def test_hard_clause_replay_owns_input_and_rejects_invalid_updates_atomically():
    from hermax.core.rc2 import RC2Reentrant
    import pytest

    solver = RC2Reentrant()
    clause = [1, -2]
    try:
        solver.add_clause(clause)
        clause[:] = [-1]
        before = solver._snapshot()
        for invalid in ([3, 0], [3, True], [3, 2**31]):
            with pytest.raises((TypeError, ValueError)):
                solver.add_clause(invalid)
            assert solver._snapshot() == before
        assert solver.solve(assumptions=[-1])
        assert -2 in solver.get_model()
        assert solver._snapshot() == before
        assert solver.solve(assumptions=[1, 2])
        assert solver._snapshot() == before
    finally:
        solver.close()
