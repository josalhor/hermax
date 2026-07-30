"""PySAT execution helpers shared by live and replayed SAT paths."""

from __future__ import annotations

import threading
from typing import Optional, Sequence

from pysat.solvers import Solver as PySATSolver

from hermax.core.time_limits import validate_time_limit


def solve_pysat_with_time_limit(
    solver: PySATSolver,
    *,
    assumptions: Sequence[int],
    time_limit: Optional[float],
) -> Optional[bool]:
    """Solve a PySAT instance and clear a deadline-induced interrupt."""
    limit = validate_time_limit(time_limit)
    if limit is None:
        return solver.solve(assumptions=list(assumptions))

    finished = threading.Event()

    def interrupt_when_due() -> None:
        if not finished.is_set():
            solver.interrupt()

    timer = threading.Timer(limit, interrupt_when_due)
    timer.start()
    try:
        return solver.solve_limited(
            assumptions=list(assumptions),
            expect_interrupt=True,
        )
    finally:
        finished.set()
        timer.cancel()
        timer.join()
        solver.clear_interrupt()
