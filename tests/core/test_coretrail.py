import os
import signal
import sys
import threading
import time

import pytest

from hermax.core.ipamir_solver_interface import SolveStatus


def _solver_class():
    from hermax.core.coretrail_py import CoreTrailSolver

    if not CoreTrailSolver.is_available():
        pytest.skip("CoreTrail native module is not available in this build")
    return CoreTrailSolver


def test_coretrail_exhausts_all_inputs_of_a_nonminimal_core():
    # Each soft literal is impossible, but the four clauses encoding that
    # fact do not reveal it by unit propagation. The final hard clause gives
    # the solver a nonminimal three-literal core to exhaust.
    solver = _solver_class()()
    try:
        solver.add_clause([-1, -2, -3])
        for literal in range(1, 4):
            a, b = 2 * literal + 2, 2 * literal + 3
            for x, y in ((a, b), (a, -b), (-a, b), (-a, -b)):
                solver.add_clause([-literal, x, y])
        for literal in range(1, 4):
            solver.add_soft_unit(literal, 1)

        assert solver.solve()
        assert solver.get_cost() == 3
        assert all(-literal in solver.get_model() for literal in range(1, 4))
    finally:
        solver.close()


def test_coretrail_disabled_core_replay_solves_satisfiable_formula():
    _solver_class()
    from hermax.core import coretrail_native
    from hermax.formula import WCNF

    formula = WCNF()
    formula.append([1], weight=1)
    solver = coretrail_native.CoreTrail(formula, core_replay=0)
    try:
        assert solver.solve()
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert solver.get_cost() == 0
        assert 1 in solver.get_model()
    finally:
        solver.close()


def test_coretrail_incremental_weighted_maxsat():
    solver = _solver_class()()
    try:
        solver.add_clause([1, 2])
        solver.add_clause([-1, -2])
        solver.set_soft(-1, 10)
        solver.set_soft(-2, 5)

        assert solver.solve()
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert solver.get_cost() == 5
        assert solver.get_model() == [-1, 2]

        assert solver.solve(assumptions=[1])
        assert solver.get_cost() == 10

        assert solver.solve()
        assert solver.get_cost() == 5

        solver.set_soft(-2, 0)
        assert solver.solve()
        assert solver.get_cost() == 0
    finally:
        solver.close()


@pytest.mark.parametrize("method", ["add_clause", "set_soft", "add_soft_unit"])
def test_coretrail_large_weight_and_cost_round_trip(method):
    solver = _solver_class()()
    weight = (1 << 63) - 1
    try:
        solver.add_clause([1])
        if method == "add_clause":
            # The IPAMIR adapter adds soft clauses via set_soft; exercise the
            # native clause-weight conversion directly as well.
            solver.solver.add_clause([-1], weight=weight)
        else:
            getattr(solver, method)(-1, weight)
        assert solver.solve()
        assert solver.get_cost() == weight
        assert solver.get_model() == [1]
    finally:
        solver.close()


def test_coretrail_deadline_resumes_natively_without_rebuild():
    solver = _solver_class()()
    try:
        solver.add_clause([1])

        solver.solve(time_limit=1e-12)
        assert solver.get_status() in {SolveStatus.INTERRUPTED, SolveStatus.INTERRUPTED_SAT}

        assert solver.solve()
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert solver.get_model() == [1]
    finally:
        solver.close()


def test_coretrail_mutation_after_interruption_uses_live_native_state():
    solver = _solver_class()()
    try:
        solver.add_clause([1, 2])
        solver.set_soft(-1, 10)
        solver.set_soft(-2, 5)

        solver.solve(time_limit=1e-12)
        assert solver.get_status() in {SolveStatus.INTERRUPTED, SolveStatus.INTERRUPTED_SAT}

        solver.add_clause([-1])
        assert solver.solve()
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert solver.get_cost() == 5
        assert solver.get_model() == [-1, 2]
    finally:
        solver.close()


@pytest.mark.skipif(sys.platform == "win32", reason="os.kill(SIGINT) terminates the process on Windows instead of delivering POSIX SIGINT")
def test_coretrail_sigint_interrupts_and_restores_the_python_handler():
    solver = _solver_class()()
    delivered: list[int] = []

    def previous_handler(signum: int, frame: object) -> None:
        del frame
        delivered.append(signum)

    original_handler = signal.signal(signal.SIGINT, previous_handler)
    try:
        for var in range(1, 1001):
            solver.add_clause([var])
            solver.set_soft(-var, 1)

        interrupter = threading.Thread(
            target=lambda: (time.sleep(0.001), os.kill(os.getpid(), signal.SIGINT)),
        )
        interrupter.start()
        returned = solver.solve()
        interrupter.join()

        assert solver.get_status() in {SolveStatus.INTERRUPTED, SolveStatus.INTERRUPTED_SAT}
        assert returned is (solver.get_status() == SolveStatus.INTERRUPTED_SAT)
        assert signal.getsignal(signal.SIGINT) is previous_handler
        assert delivered == []

        assert solver.solve()
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert solver.get_cost() == 1000
    finally:
        signal.signal(signal.SIGINT, original_handler)
        solver.close()


def test_coretrail_public_exports():
    from hermax.core import CoreTrailSolver
    from hermax.incremental import CoreTrail

    assert CoreTrail.__mro__[1] is CoreTrailSolver


def test_coretrail_loads_native_hards_without_python_clause_iteration(monkeypatch):
    from hermax.formula import WCNF
    from hermax.internal._clause_storage import ClauseStorage
    formula = WCNF()
    formula.append([1, 2])
    formula.append([-1, -2])
    formula.append([-1], weight=3)
    formula.append([-2], weight=7)
    original = ClauseStorage.__iter__

    def guarded(collection):
        if collection is formula.hard:
            raise AssertionError('Native hard clauses were exported through Python.')
        return original(collection)

    monkeypatch.setattr(ClauseStorage, '__iter__', guarded)
    solver = _solver_class()(formula)
    try:
        assert solver.solve()
        assert solver.get_cost() == 3
        assert solver.solve(assumptions=[2])
        assert solver.get_cost() == 7
    finally:
        solver.close()


def test_coretrail_native_bulk_hards_reject_wide_input_before_mutation():
    from hermax.internal._clause_storage import ClauseStorage
    solver = _solver_class()()
    try:
        hards = ClauseStorage([[], [2**40]])
        with pytest.raises(OverflowError):
            solver.solver._add_hard_packed(hards._storage)
        assert solver.solve()  # the preceding empty clause must not have been added
    finally:
        solver.close()


def test_coretrail_batch_hard_loading_updates_public_state_and_uses_native_storage(monkeypatch):
    from hermax.internal._clause_storage import ClauseStorage
    clauses = ClauseStorage([[1, 2], [-1, -2]])
    solver = _solver_class()()
    try:
        assert solver.solve()
        monkeypatch.setattr(clauses.__class__, '__iter__', lambda _: (_ for _ in ()).throw(
            AssertionError('Batch loading must not materialize native hard clauses.')))
        solver.add_clauses(clauses)
        assert solver.num_vars == 2
        solver.set_soft(-1, 3)
        solver.set_soft(-2, 7)
        assert solver.solve()
        assert solver.get_cost() == 3
    finally:
        solver.close()


def test_native_coretrail_accepts_plain_literal_tuples():
    solver = _solver_class()()
    try:
        solver.solver.add_clause((1, 2))
        solver.solver.add_clause((-1,))
        assert solver.solver.solve()
        assert 2 in solver.solver.get_model()
    finally:
        solver.close()


@pytest.mark.parametrize('literal', [True, 1.5, 0, 2**40, 2**40 + 1, -(2**31)])
def test_native_coretrail_rejects_invalid_literals_without_truncating(literal):
    solver = _solver_class()()
    try:
        with pytest.raises((TypeError, ValueError, OverflowError)):
            solver.solver.add_clause([literal])
        assert solver.solve()
    finally:
        solver.close()


def test_native_coretrail_rejects_variable_count_outside_int32():
    from types import SimpleNamespace
    from hermax.core import coretrail_native
    with pytest.raises(OverflowError):
        coretrail_native.CoreTrail(SimpleNamespace(nv=2**32, hard=[], soft=[], wght=[]))


@pytest.mark.parametrize('method', ['set_soft', 'add_soft_unit'])
@pytest.mark.parametrize('literal', [True, 0, 2**40 + 1, -(2**31)])
def test_native_coretrail_scalar_soft_literals_do_not_narrow_or_coerce(method, literal):
    solver = _solver_class()()
    try:
        with pytest.raises((TypeError, ValueError, OverflowError)):
            getattr(solver.solver, method)(literal, 1)
        assert solver.solve()
        assert solver.get_cost() == 0
    finally:
        solver.close()


@pytest.mark.parametrize('unit_first', [False, True])
def test_native_soft_clause_selector_does_not_collide_with_user_literal(unit_first):
    from hermax.core import coretrail_native
    from hermax.formula import WCNF
    s = coretrail_native.CoreTrail(WCNF())
    try:
        if unit_first:
            s.set_soft(4, 2)
            s.add_clause([1, 2], weight=5)
            unit = 4
        else:
            s.add_clause([1, 2], weight=5)
            s.set_soft(3, 2)
            unit = 3
        s.add_clause([-1])
        s.add_clause([-2])
        s.add_clause([-unit])
        assert s.solve()
        assert s.get_cost() == 7
        s.set_soft(unit, 3)
        assert s.solve()
        assert s.get_cost() == 8
    finally:
        s.close()
