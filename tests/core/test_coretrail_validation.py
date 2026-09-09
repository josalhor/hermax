from types import SimpleNamespace

import pytest

from hermax.core.coretrail_py.coretrail_solver import CoreTrailSolver


class _BackendProbe:
    def add_clause(self, clause):
        return None

    def set_soft(self, lit, weight):
        return None


def _load(formula):
    solver = object.__new__(CoreTrailSolver)
    solver._init_ipamir_state()
    solver._num_vars = 0
    solver.solver = _BackendProbe()
    solver._load_initial_formula(formula)


@pytest.mark.xfail(
    strict=True,
    reason="CoreTrail formula loading converts malformed WCNF literals before validation",
)
@pytest.mark.parametrize("bad_literal", [1.5, True, "1"])
def test_coretrail_rejects_non_integer_formula_literals(bad_literal):
    formula = SimpleNamespace(hard=[[bad_literal]], soft=[], wght=[], nv=1)

    with pytest.raises((TypeError, ValueError)):
        _load(formula)


@pytest.mark.xfail(
    strict=True,
    reason="CoreTrail formula loading converts malformed WCNF weights before validation",
)
@pytest.mark.parametrize("bad_weight", [1.5, True, "2"])
def test_coretrail_rejects_non_integer_formula_weights(bad_weight):
    formula = SimpleNamespace(hard=[], soft=[[1]], wght=[bad_weight], nv=1)

    with pytest.raises((TypeError, ValueError)):
        _load(formula)
