import pytest

from hermax.internal.solver_worker_main import _ops_replay_to_solver, _snapshot_replay_to_solver


class _WorkerProbeSolver:
    def __init__(self):
        self.calls = []

    def new_var(self):
        self.calls.append(("new_var",))

    def add_clause(self, clause, weight=None):
        self.calls.append(("add_clause", list(clause), weight))

    def set_soft(self, lit, weight):
        self.calls.append(("set_soft", lit, weight))

    def add_soft_unit(self, lit, weight):
        self.calls.append(("add_soft_unit", lit, weight))

    def add_soft_relaxed(self, clause, weight, relax_var):
        self.calls.append(("add_soft_relaxed", list(clause), weight, relax_var))


@pytest.mark.xfail(
    strict=True,
    reason="Worker operation replay coerces malformed literals with int()",
)
@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_worker_operation_replay_rejects_non_integer_literals(raw_literal):
    solver = _WorkerProbeSolver()

    with pytest.raises((TypeError, ValueError)):
        _ops_replay_to_solver(solver, [("add_clause", [raw_literal])])


@pytest.mark.xfail(
    strict=True,
    reason="Worker snapshot replay coerces malformed literals with int()",
)
@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_worker_snapshot_replay_rejects_non_integer_literals(raw_literal):
    solver = _WorkerProbeSolver()

    with pytest.raises((TypeError, ValueError)):
        _snapshot_replay_to_solver(
            solver,
            {"hard_clauses": [[raw_literal]], "soft_units": [], "soft_nonunit": []},
        )

