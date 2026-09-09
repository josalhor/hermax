import pytest

from hermax.core.loandra_py.loandra_solver import LoandraSolver
from hermax.core.openwbo_inc_py.openwbo_inc_solver import OpenWBOIncSolver
from hermax.core.tt_openwbo_inc_py.tt_openwbo_inc_solver import TTOpenWBOIncSolver
from hermax.core.aperture_py.aperture_solver import ApertureSolver
from hermax.core.evalmaxsat_incr_py.evalmaxsat_solver import EvalMaxSATIncrSolver
from hermax.core.imaxhs_wrapper_py.imaxhs import IMaxHSSolver
from hermax.core.uwrmaxsat_comp_py.urmaxsat_solver import UWrMaxSATCompSolver
from hermax.core.uwrmaxsat_py.urmaxsat_solver import UWrMaxSATSolver


class _NativeProbe:
    def __init__(self):
        self.next_var = 0
        self.clauses = []

    def newVar(self):
        self.next_var += 1
        return self.next_var

    def addClause(self, clause, weight=None):
        self.clauses.append((list(clause), weight))

    def getValue(self, var):
        return True


def _wrapper(cls):
    solver = object.__new__(cls)
    solver.solver = _NativeProbe()
    solver.num_vars = 0
    return solver


@pytest.mark.xfail(
    strict=True,
    reason="One-shot native wrappers coerce non-integer hard literals with int()",
)
@pytest.mark.parametrize("wrapper", [LoandraSolver, OpenWBOIncSolver, TTOpenWBOIncSolver])
@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_one_shot_native_wrappers_reject_non_integer_hard_literals(wrapper, raw_literal):
    solver = _wrapper(wrapper)

    with pytest.raises((TypeError, ValueError), match="literal|integer"):
        solver.add_clause([raw_literal])


@pytest.mark.xfail(
    strict=True,
    reason="One-shot native wrappers allocate variables before rejecting a later invalid literal",
)
@pytest.mark.parametrize("wrapper", [LoandraSolver, OpenWBOIncSolver, TTOpenWBOIncSolver])
def test_one_shot_native_wrapper_clause_validation_is_atomic(wrapper):
    solver = _wrapper(wrapper)

    with pytest.raises((TypeError, ValueError), match="literal|integer|zero"):
        solver.add_clause([3, 0])

    assert solver.num_vars == 0
    assert solver.solver.clauses == []


@pytest.mark.xfail(
    strict=True,
    reason="One-shot native wrappers coerce non-integer literals in add_soft_unit()",
)
@pytest.mark.parametrize("wrapper", [LoandraSolver, OpenWBOIncSolver, TTOpenWBOIncSolver])
def test_one_shot_native_wrappers_reject_non_integer_soft_literals(wrapper):
    solver = _wrapper(wrapper)

    with pytest.raises((TypeError, ValueError), match="literal|integer"):
        solver.add_soft_unit(1.5, 2)


@pytest.mark.xfail(
    strict=True,
    reason="One-shot native wrappers coerce non-integer weights in add_soft_unit()",
)
@pytest.mark.parametrize("wrapper", [LoandraSolver, OpenWBOIncSolver, TTOpenWBOIncSolver])
@pytest.mark.parametrize("raw_weight", [True, 1.5, "2"])
def test_one_shot_native_wrappers_reject_non_integer_soft_weights(wrapper, raw_weight):
    solver = _wrapper(wrapper)

    with pytest.raises((TypeError, ValueError), match="weight|integer"):
        solver.add_soft_unit(1, raw_weight)


@pytest.mark.xfail(
    strict=True,
    reason="One-shot native wrappers coerce non-integer val() literals with int()",
)
@pytest.mark.parametrize("wrapper", [LoandraSolver, TTOpenWBOIncSolver])
@pytest.mark.parametrize("raw_literal", [1.5, True])
def test_one_shot_native_wrappers_reject_non_integer_val_literals(wrapper, raw_literal):
    solver = _wrapper(wrapper)
    solver.num_vars = 1
    solver._model = [1]

    with pytest.raises((TypeError, ValueError), match="literal|integer"):
        solver.val(raw_literal)


@pytest.mark.xfail(
    strict=True,
    reason="OpenWBO-Inc coerces boolean val() literals to variable 1",
)
def test_openwbo_inc_rejects_boolean_val_literals():
    solver = _wrapper(OpenWBOIncSolver)
    solver.num_vars = 1
    solver._model = [1]

    with pytest.raises((TypeError, ValueError), match="literal|integer"):
        solver.val(True)


@pytest.mark.xfail(
    strict=True,
    reason="Several native wrappers cast add_soft_unit() literals before validation",
)
@pytest.mark.parametrize(
    "wrapper",
    [
        ApertureSolver,
        EvalMaxSATIncrSolver,
        IMaxHSSolver,
        UWrMaxSATSolver,
        UWrMaxSATCompSolver,
    ],
)
@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_native_incremental_wrappers_reject_non_integer_soft_literals(
    wrapper, raw_literal
):
    solver = object.__new__(wrapper)
    solver.set_soft = lambda _lit, _weight: None

    with pytest.raises((TypeError, ValueError), match="literal|integer"):
        solver.add_soft_unit(raw_literal, 2)
