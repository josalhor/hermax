"""Verify the UWr adapter forwards the intended query unchanged."""
from hermax.core import UWrMaxSATSolver
from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.core.uwrmaxsat_py import urmaxsat_solver


def test_uwr_wrapper_forwards_relaxation_query(monkeypatch):
    calls = []

    class RecordingNative:
        def signature(self):
            return 'recording-uwr'

        def addClause(self, clause, weight):
            calls.append(('clause', list(clause), weight))

        def assume(self, assumptions):
            calls.append(('assume', list(assumptions)))

        def solve(self):
            calls.append(('solve',))
            return int(SolveStatus.UNSAT)

    monkeypatch.setattr(urmaxsat_solver._urmaxsat, 'UWrMaxSAT', RecordingNative)
    solver = UWrMaxSATSolver()
    try:
        solver.add_clause([-1, -2])
        solver.set_soft(1, 5)
        solver.set_soft(2, 3)
        solver.add_soft_relaxed([1, 2], 4, relax_var=3)
        assert not solver.solve(assumptions=[-1, -2])
        assert calls == [
            ('clause', [-1, -2], None),
            ('clause', [1], 5),
            ('clause', [2], 3),
            ('clause', [-3], 4),
            ('clause', [1, 2, 3], None),
            ('assume', [-1, -2]),
            ('solve',),
        ]
    finally:
        solver.close()
