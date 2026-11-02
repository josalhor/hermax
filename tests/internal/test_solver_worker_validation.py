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


@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_worker_operation_replay_rejects_non_integer_literals(raw_literal):
    solver = _WorkerProbeSolver()

    with pytest.raises((TypeError, ValueError)):
        _ops_replay_to_solver(solver, [("add_clause", [raw_literal])])
    assert solver.calls == []


@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_worker_snapshot_replay_rejects_non_integer_literals(raw_literal):
    solver = _WorkerProbeSolver()

    with pytest.raises((TypeError, ValueError)):
        _snapshot_replay_to_solver(
            solver,
            {"hard_clauses": [[raw_literal]], "soft_units": [], "soft_nonunit": []},
        )
    assert solver.calls == []



def test_worker_snapshot_uses_bulk_handoff_for_native_hards():
    from hermax.internal._clause_storage import ClauseStorage

    class BulkSolver(_WorkerProbeSolver):
        def add_clauses(self, clauses):
            assert isinstance(clauses, ClauseStorage)
            self.calls.append(('bulk_hards', clauses.to_lists()))

    solver = BulkSolver()
    _snapshot_replay_to_solver(solver, {
        'num_vars': 2, 'hard_clauses': [[1, -2]],
        'soft_units': [(1, 3)], 'soft_nonunit': [],
    })
    assert solver.calls == [('new_var',), ('new_var',),
                            ('bulk_hards', [[1, -2]]), ('set_soft', 1, 3)]


def test_worker_snapshot_supports_backends_that_allocate_variables_on_demand():
    class LazySolver(_WorkerProbeSolver):
        def new_var(self):
            raise NotImplementedError('Variables are allocated when clauses are added.')

    solver = LazySolver()
    _snapshot_replay_to_solver(solver, {'num_vars': 2, 'hard_clauses': [[1, -2]]})
    assert solver.calls == [('add_clause', [1, -2], None)]
