from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import textwrap
import time

import pytest


@pytest.mark.skipif(os.name == "nt", reason="the native Ctrl-C guard is POSIX-only")
def test_uwrmaxsat_ctrl_c_releases_native_state_and_returns_to_python():
    pytest.importorskip("hermax.core.urmaxsat_py")
    program = textwrap.dedent(
        """
        import random
        import sys

        from hermax.core.uwrmaxsat_py.urmaxsat_solver import UWrMaxSATSolver

        random_source = random.Random(7)
        solver = UWrMaxSATSolver()

        def clause():
            return [
                variable if random_source.randrange(2) else -variable
                for variable in random_source.sample(range(1, 301), 3)
            ]

        for _ in range(1300):
            solver.add_clause(clause())
        # Keep this instance alive long enough to target an active native
        # search.  These direct binding clauses only shape the workload; the
        # public post-interrupt behavior is asserted below.
        for _ in range(2500):
            solver.solver.addClause(clause(), 1)

        print("READY", flush=True)
        try:
            solver.solve()
        except KeyboardInterrupt:
            print("INTERRUPTED", solver.get_status().name, flush=True)
            try:
                solver.add_clause([1])
            except RuntimeError as exc:
                print("DISCARDED", "cannot be used after Ctrl-C" in str(exc), flush=True)
            else:
                print("DISCARDED", False, flush=True)
            raise SystemExit(0)

        print("NOT_INTERRUPTED", flush=True)
        raise SystemExit(3)
        """
    )
    root = Path(__file__).resolve().parents[2]
    child = subprocess.Popen(
        [sys.executable, "-c", program],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        ready = child.stdout.readline().strip()
        if ready != "READY":
            stdout, stderr = child.communicate(timeout=10)
            pytest.fail(f"UWrMaxSAT child did not become ready: {ready!r}\n{stdout}\n{stderr}")

        # The workload is intentionally much slower than this short delay.
        time.sleep(0.1)
        os.kill(child.pid, signal.SIGINT)
        stdout, stderr = child.communicate(timeout=30)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()

    assert child.returncode == 0, stderr
    assert "INTERRUPTED INTERRUPTED" in stdout
    assert "DISCARDED True" in stdout
