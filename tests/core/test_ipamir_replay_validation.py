import pytest
from types import SimpleNamespace

from hermax.core.ipamir_replay_base import ReplayFormulaSolverBase, ReplaySolveResult
from hermax.core.ipamir_solver_interface import SolveStatus


class _ReplayProbe(ReplayFormulaSolverBase):
    def signature(self):
        return "replay-probe"

    def _run_replay_solve(self, assumptions):
        return ReplaySolveResult(SolveStatus.UNSAT, None, None)


class _MalformedReplayResultProbe(_ReplayProbe):
    def __init__(self, result):
        self._result = result
        super().__init__()

    def _run_replay_solve(self, assumptions):
        return self._result


class _FeasibleReplayProbe(_ReplayProbe):
    def _run_replay_solve(self, assumptions):
        return ReplaySolveResult(SolveStatus.OPTIMUM, [1], 0)


def test_replay_solver_rejects_feasible_result_without_model():
    solver = _MalformedReplayResultProbe(
        ReplaySolveResult(SolveStatus.OPTIMUM, None, 0)
    )

    try:
        assert not solver.solve()
    finally:
        solver.close()


@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_replay_solver_rejects_non_integer_clause_literals(raw_literal):
    solver = _ReplayProbe()

    with pytest.raises((TypeError, ValueError)):
        solver.add_clause([raw_literal])


@pytest.mark.parametrize("bad_literal", [1.5, True, "1"])
def test_replay_solver_rejects_non_integer_formula_literals(bad_literal):
    formula = SimpleNamespace(
        hard=[[bad_literal]],
        soft=[],
        wght=[],
        nv=1,
    )

    with pytest.raises((TypeError, ValueError)):
        _ReplayProbe(formula=formula)


@pytest.mark.parametrize("bad_call", ["assumptions", "time_limit"])
def test_replay_solver_preserves_previous_result_when_solve_input_is_invalid(bad_call):
    solver = _FeasibleReplayProbe()
    solver.new_var()
    assert solver.solve()
    before = (solver.get_status(), solver.get_model(), solver.get_cost())

    with pytest.raises((TypeError, ValueError)):
        if bad_call == "assumptions":
            solver.solve(assumptions=[0])
        else:
            solver.solve(time_limit=0)

    assert (solver.get_status(), solver.get_model(), solver.get_cost()) == before


def test_replay_solver_assumptions_do_not_extend_persistent_formula():
    solver = _ReplayProbe()
    assert solver._num_vars == 0

    solver.solve(assumptions=[5])

    assert solver._num_vars == 0
    assert solver._journal.snapshot()["hard_clauses"] == []
