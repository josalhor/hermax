import pytest

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus


class _DummySolver(IPAMIRSolver):
    def __init__(self, *, fail_set_soft=False):
        super().__init__()
        self.hard = []
        self.soft = []
        self.fail_set_soft = fail_set_soft

    def add_clause(self, clause):
        self.hard.append(list(clause))

    def set_soft(self, lit, weight):
        if self.fail_set_soft:
            raise RuntimeError("synthetic soft-update failure")
        self.soft.append((lit, weight))

    def add_soft_unit(self, lit, weight):
        self.set_soft(lit, weight)

    def solve(self, assumptions=None, raise_on_abnormal=False, time_limit=None):
        self._status = SolveStatus.OPTIMUM
        return True

    def get_status(self):
        return self._status

    def get_cost(self):
        return 0

    def val(self, lit):
        return 1

    def get_model(self):
        return []

    def signature(self):
        return "dummy"

    def close(self):
        pass


@pytest.mark.xfail(
    strict=True,
    reason="IPAMIRSolver.add_soft_relaxed coerces invalid relaxation variables with int()",
)
@pytest.mark.parametrize("relax_var", [0, True, 1.5, "2"])
def test_default_add_soft_relaxed_rejects_invalid_relaxation_variables(relax_var):
    solver = _DummySolver()

    with pytest.raises((TypeError, ValueError), match="relax"):
        solver.add_soft_relaxed([1, 2], 3, relax_var=relax_var)


@pytest.mark.xfail(
    strict=True,
    reason="IPAMIRSolver.add_soft_relaxed adds the hard clause before soft registration succeeds",
)
def test_default_add_soft_relaxed_is_atomic_when_soft_registration_fails():
    solver = _DummySolver(fail_set_soft=True)

    with pytest.raises(RuntimeError, match="synthetic soft-update failure"):
        solver.add_soft_relaxed([1, 2], 3, relax_var=4)

    assert solver.hard == []
    assert solver.soft == []


@pytest.mark.xfail(
    strict=True,
    reason="IPAMIRSolver.add_soft_relaxed coerces non-integer clause literals with int()",
)
@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_default_add_soft_relaxed_rejects_non_integer_clause_literals(raw_literal):
    solver = _DummySolver()

    with pytest.raises((TypeError, ValueError), match="literal|integer"):
        solver.add_soft_relaxed([raw_literal, 2], 3, relax_var=4)
