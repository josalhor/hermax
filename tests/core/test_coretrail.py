import os
import signal
import threading
import time

import pytest

from hermax.core.ipamir_solver_interface import SolveStatus


def _solver_class():
    from hermax.core.coretrail_py import CoreTrailSolver

    if not CoreTrailSolver.is_available():
        pytest.skip("CoreTrail native module is not available in this build")
    return CoreTrailSolver


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
