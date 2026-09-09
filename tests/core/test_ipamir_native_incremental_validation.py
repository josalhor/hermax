import pytest

from hermax.core.ipamir_native_incremental_base import NativeIncrementalSolverBase
from hermax.core.formula_journal import FormulaJournal
from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.core.uwrmaxsat_comp_py.urmaxsat_solver import UWrMaxSATCompSolver


class _NativeBackend:
    def __init__(self, *, fail_add=False, fail_soft=False, fail_new=False):
        self.fail_add = fail_add
        self.fail_soft = fail_soft
        self.fail_new = fail_new
        self.variables = []
        self.hard = []
        self.soft = []

    def new_var(self, var_id):
        if self.fail_new:
            raise RuntimeError("synthetic native variable failure")
        self.variables.append(var_id)

    def add_clause(self, clause):
        if self.fail_add:
            raise RuntimeError("synthetic native clause failure")
        self.hard.append(list(clause))

    def set_soft(self, lit, weight):
        if self.fail_soft:
            raise RuntimeError("synthetic native soft failure")
        self.soft.append((lit, weight))


class _NativeProbe(NativeIncrementalSolverBase):
    def __init__(self, backend):
        self.backend = backend
        super().__init__()

    def _backend_new_var(self, var_id):
        self.backend.new_var(var_id)

    def add_clause(self, clause):
        self._require_open()
        normalized = self._normalize_clause(clause)
        self.backend.add_clause(normalized)
        self._record_hard_clause(normalized)
        self._invalidate_solution()

    def set_soft(self, lit, weight):
        self._require_open()
        normalized = self._normalize_lit(lit)
        normalized_weight = self._normalize_positive_weight(weight)
        self._ensure_var(abs(normalized))
        self.backend.set_soft(normalized, normalized_weight)
        self._record_soft_unit(normalized, normalized_weight)
        self._invalidate_solution()

    def add_soft_unit(self, lit, weight):
        self.set_soft(lit, weight)

    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        raise NotImplementedError

    def get_status(self):
        return SolveStatus.UNKNOWN

    def get_cost(self):
        raise RuntimeError

    def val(self, lit):
        raise RuntimeError

    def get_model(self):
        raise RuntimeError

    def signature(self):
        return "native-probe"


@pytest.mark.xfail(
    strict=True,
    reason="NativeIncrementalSolverBase._normalize_lit coerces non-integer literals with int()",
)
@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_native_solver_rejects_non_integer_clause_literals(raw_literal):
    solver = _NativeProbe(_NativeBackend())

    with pytest.raises((TypeError, ValueError)):
        solver.add_clause([raw_literal])


@pytest.mark.xfail(
    strict=True,
    reason="Native clause insertion allocates journal variables before native insertion succeeds",
)
def test_native_clause_failure_does_not_leave_phantom_variables():
    backend = _NativeBackend(fail_add=True)
    solver = _NativeProbe(backend)

    with pytest.raises(RuntimeError, match="synthetic native clause failure"):
        solver.add_clause([3])

    assert solver.num_vars == 0
    assert solver._journal.hard_clauses == []


@pytest.mark.xfail(
    strict=True,
    reason="Native soft insertion allocates journal variables before native insertion succeeds",
)
def test_native_soft_failure_does_not_leave_phantom_variables():
    backend = _NativeBackend(fail_soft=True)
    solver = _NativeProbe(backend)

    with pytest.raises(RuntimeError, match="synthetic native soft failure"):
        solver.set_soft(4, 2)

    assert solver.num_vars == 0
    assert solver._journal.soft_units == {}


@pytest.mark.xfail(
    strict=True,
    reason="NativeIncrementalSolverBase.new_var updates the journal before native allocation succeeds",
)
def test_native_variable_allocation_failure_does_not_leave_phantom_variables():
    solver = _NativeProbe(_NativeBackend(fail_new=True))

    with pytest.raises(RuntimeError, match="synthetic native variable failure"):
        solver.new_var()

    assert solver.num_vars == 0


@pytest.mark.xfail(
    strict=True,
    reason="NativeIncrementalSolverBase persists variables introduced only by temporary assumptions",
)
def test_native_solver_assumptions_do_not_extend_persistent_formula():
    solver = _NativeProbe(_NativeBackend())
    assert solver.num_vars == 0

    solver._normalize_assumptions([5])

    assert solver.num_vars == 0
    assert solver._journal.hard_clauses == []


@pytest.mark.xfail(
    strict=True,
    reason="UWrMaxSATComp zero-weight removal mutates formula state before rebuild succeeds",
)
def test_uwr_comp_zero_weight_rebuild_failure_is_atomic():
    solver = object.__new__(UWrMaxSATCompSolver)
    solver._closed = False
    solver._status = SolveStatus.UNKNOWN
    solver._model = None
    solver._last_cost = None
    solver._journal = FormulaJournal()
    solver.solver = object()
    solver._anon_soft_by_lit = {-1: 7}
    solver._id_soft_b_weight = {}
    solver._soft_ids = {}
    solver._hard_only_guard_installed = False
    solver._hard_clauses = []

    solver._journal.set_soft(-1, 7)

    def fail_rebuild():
        raise RuntimeError("synthetic rebuild failure")

    solver._rebuild_backend = fail_rebuild

    with pytest.raises(RuntimeError, match="synthetic rebuild failure"):
        solver.set_soft(-1, 0)

    assert solver._anon_soft_by_lit == {-1: 7}
    assert solver._journal.soft_units == {-1: 7}
