from __future__ import annotations

import pytest

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus
from hermax.model import Clause, ClauseGroup, Model


class _ReplaySolverNoNewVar(IPAMIRSolver):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.hard: list[list[int]] = []
        self.soft: dict[int, int] = {}
        self.closed = False
        self._status = SolveStatus.OPTIMUM
        self._model: list[int] = []
        self._cost = 0

    def add_clause(self, clause: list[int]) -> None:
        self.hard.append([int(x) for x in clause])

    def set_soft(self, lit: int, weight: int) -> None:
        self.soft[int(lit)] = int(weight)

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(int(lit), int(weight))

    def solve(self, assumptions=None, raise_on_abnormal: bool = False) -> bool:
        return self._status in (SolveStatus.OPTIMUM, SolveStatus.INTERRUPTED_SAT)

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        return int(self._cost)

    def val(self, lit: int) -> int:
        return 0

    def get_model(self):
        return list(self._model)

    def signature(self) -> str:
        return "replay-no-newvar"

    def close(self) -> None:
        self.closed = True


class _ReplaySolverWithNewVar(_ReplaySolverNoNewVar):
    def __init__(self):
        super().__init__()
        self._next = 0

    def new_var(self) -> int:
        self._next += 1
        return self._next

    def signature(self) -> str:
        return "replay-with-newvar"


def _mk_nonunit_soft_model() -> Model:
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.add_soft(a | b, weight=7)
    return m


def test_clausegroup_extend_and_clause_and_paths():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    g = ClauseGroup(m, [Clause(m, [a])])
    with pytest.raises(TypeError, match="inplace=True"):
        g.extend(Clause(m, [b]))

    g.extend(Clause(m, [b]), inplace=True)
    g.extend(c, inplace=True)
    g2 = ClauseGroup(m, [Clause(m, [~a])])
    g.extend(g2, inplace=True)
    assert len(g.clauses) == 4

    # Cover Clause.__and__ branches for Clause and ClauseGroup operands.
    ch = Clause(m, [a]) & Clause(m, [b])
    assert isinstance(ch, ClauseGroup) and len(ch.clauses) == 2
    ch2 = Clause(m, [a]) & ClauseGroup(m, [Clause(m, [c])])
    assert isinstance(ch2, ClauseGroup) and len(ch2.clauses) == 2


def test_model_vector_errors_empty_mixed_cross_model():
    m1 = Model()
    m2 = Model()
    a = m1.bool("a")
    x = m1.int("x", 0, 3)
    b2 = m2.bool("b2")

    with pytest.raises(ValueError, match="at least one item"):
        m1.vector([])
    with pytest.raises(TypeError, match="homogeneous"):
        m1.vector([a, x])
    with pytest.raises(ValueError, match="different models"):
        m1.vector([a, b2])


@pytest.mark.parametrize("bad", [True, 0, -1])
def test_floor_div_rejects_bad_divisor_values(bad):
    m = Model()
    x = m.int("x", 0, 6)
    with pytest.raises(ValueError):
        m.floor_div(x, bad)


def test_floor_div_rejects_non_integer_divisor():
    m = Model()
    x = m.int("x", 0, 6)
    with pytest.raises(TypeError):
        m.floor_div(x, 2.5)


@pytest.mark.parametrize("bad", [True, 0, -3])
def test_scale_rejects_bad_factor_values(bad):
    m = Model()
    x = m.int("x", 0, 6)
    with pytest.raises(ValueError):
        m.scale(x, bad)


def test_scale_rejects_non_integer_factor():
    m = Model()
    x = m.int("x", 0, 6)
    with pytest.raises(TypeError):
        m.scale(x, 1.25)


def test_aggregate_helpers_empty_and_singleton_behaviors():
    m = Model()
    x = m.int("x", 0, 4)
    assert m.max([x]) is x
    assert m.min([x]) is x
    assert m.upper_bound([x]) is x
    assert m.lower_bound([x]) is x

    with pytest.raises(ValueError, match="empty IntVector"):
        m.max([])
    with pytest.raises(ValueError, match="empty IntVector"):
        m.min([])
    with pytest.raises(ValueError, match="empty IntVector"):
        m.upper_bound([])
    with pytest.raises(ValueError, match="empty IntVector"):
        m.lower_bound([])


def test_add_soft_rejects_negative_lb_intvar():
    m = Model()
    x = m.int("x", -2, 3)
    with pytest.raises(ValueError, match="IntVar.lb >= 0"):
        m.add_soft(x, weight=1)


def test_add_soft_rejects_cross_model_pbexpr():
    m1 = Model()
    m2 = Model()
    a = m1.bool("a")
    expr = a + 1
    with pytest.raises(ValueError, match="different models"):
        m2.add_soft(expr, weight=1)


def test_add_soft_accepts_lazy_expr_by_realization():
    m = Model()
    x = m.int("x", 0, 6)
    # _LazyIntExpr branch in add_soft.
    ref = m.add_soft(x // 2, weight=2)
    assert ref.soft_ids


def test_solve_with_existing_solver_replay_nonunit_soft_without_new_var():
    m = _mk_nonunit_soft_model()
    s = _ReplaySolverNoNewVar()
    r = m.solve(solver=s, incremental=False)
    assert r.status == "optimum"
    # Non-unit soft replay should introduce one relax hard clause and one soft unit.
    assert any(len(cl) >= 3 for cl in s.hard)
    assert len(s.soft) == 1
    # Existing solver instance should not be closed by Model.
    assert s.closed is False


def test_solve_with_existing_solver_replay_nonunit_soft_with_new_var():
    m = _mk_nonunit_soft_model()
    s = _ReplaySolverWithNewVar()
    r = m.solve(solver=s, incremental=False)
    assert r.status == "optimum"
    assert len(s.soft) == 1
    assert s._next >= 1


@pytest.mark.parametrize(
    ("st", "expected"),
    [
        (SolveStatus.OPTIMUM, "optimum"),
        (SolveStatus.UNSAT, "unsat"),
        (SolveStatus.INTERRUPTED_SAT, "interrupted_sat"),
        (SolveStatus.INTERRUPTED, "interrupted"),
        (SolveStatus.ERROR, "error"),
        (SolveStatus.UNKNOWN, "unknown"),
    ],
)
def test_solve_status_mapping_for_ipamir_backends(st, expected):
    m = Model()
    m &= m.bool("a")
    s = _ReplaySolverNoNewVar()
    s._status = st
    r = m.solve(solver=s, incremental=False)
    assert r.status == expected


def test_assumptions_reject_bool_zero_and_bad_term_coeff():
    m = Model()
    a = m.bool("a")
    s = _ReplaySolverNoNewVar()

    with pytest.raises(TypeError, match="do not accept bool"):
        m.solve(solver=s, incremental=False, assumptions=[True])
    with pytest.raises(ValueError, match="cannot be 0"):
        m.solve(solver=s, incremental=False, assumptions=[0])
    with pytest.raises(TypeError, match="unit term"):
        m.solve(solver=s, incremental=False, assumptions=[2 * a])


def test_update_soft_weight_rejects_unknown_targets_and_types():
    m = Model()
    a = m.bool("a")
    m.add_soft(a, weight=2)

    with pytest.raises(KeyError, match="Unknown soft target"):
        m.update_soft_weight(999999, 3)
    with pytest.raises(TypeError, match="target must be"):
        m.update_soft_weight(object(), 3)


def test_vector_element_all_comparators_with_intvar_rhs():
    m = Model()
    vals = m.int_vector("v", length=3, lb=0, ub=10)
    idx = m.int("idx", 0, 3)
    rhs = m.int("rhs", 0, 10)
    m &= (vals[0] == 2)
    m &= (vals[1] == 5)
    m &= (vals[2] == 8)
    m &= (idx == 1)
    m &= (rhs == 5)
    m &= (vals[idx] <= rhs)
    m &= (vals[idx] < rhs)
    m &= (vals[idx] >= rhs)
    m &= (vals[idx] > rhs)
    m &= (vals[idx] == rhs)
    m &= (vals[idx] != rhs)
    r = m.solve()
    assert r.status == "unsat"


def test_vector_element_rejects_bad_rhs_type():
    m = Model()
    vals = m.int_vector("v", length=2, lb=0, ub=5)
    idx = m.int("idx", 0, 2)
    with pytest.raises(TypeError, match="does not support RHS"):
        _ = (vals[idx] <= "x")


def test_intvector_extreme_and_bound_empty_errors():
    m = Model()
    v = m.int_vector("v", length=0, lb=0, ub=1)
    with pytest.raises(ValueError, match="empty IntVector"):
        _ = v.max()
    with pytest.raises(ValueError, match="empty IntVector"):
        _ = v.min()
    with pytest.raises(ValueError, match="empty IntVector"):
        _ = v.upper_bound()
    with pytest.raises(ValueError, match="empty IntVector"):
        _ = v.lower_bound()


def test_set_objective_precision_rejects_bad_decimals_and_zero_rounding():
    m = Model()
    a = m.bool("a")
    with pytest.raises(ValueError, match="non-negative integer"):
        m.set_objective_precision(decimals=-1)
    with pytest.raises(ValueError, match="non-negative integer"):
        m.set_objective_precision(decimals=True)

    m.set_objective_precision(decimals=2)
    m.add_soft(a, weight=0.01)
    with pytest.raises(ValueError, match="rounds an existing positive soft weight to zero"):
        m.set_objective_precision(decimals=1)


def test_add_soft_pbexpr_positive_and_negative_coeff_paths_affect_offset():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    # Force deterministic model so fake backend cost contribution is only offset.
    m &= a
    m &= ~b
    # positive coeff path (~lit soft) and negative coeff path (lit soft + offset decrement)
    m.add_soft((2 * a) + (-3 * b) + 5, weight=1)

    s = _ReplaySolverNoNewVar()
    s._status = SolveStatus.OPTIMUM
    s._cost = 0
    r = m.solve(solver=s, incremental=False)
    assert r.status == "optimum"
    # offset = +5 -3 = +2
    assert r.cost == 2


def test_solve_one_shot_rejects_non_callable_solver():
    m = Model()
    m &= m.bool("a")
    with pytest.raises(TypeError, match="instance, class, or callable"):
        m.solve(solver=123, incremental=False)


def test_solve_one_shot_factory_wrong_return_type_raises():
    m = Model()
    m &= m.bool("a")

    def _bad_factory(*args, **kwargs):
        class _X:
            def close(self):
                return None

        return _X()

    with pytest.raises(TypeError, match="must return an IPAMIRSolver"):
        m.solve(solver=_bad_factory, incremental=False)


def test_solve_one_shot_created_solver_close_exception_is_swallowed():
    class _ClosingRaises(_ReplaySolverNoNewVar):
        def close(self) -> None:
            raise RuntimeError("close failure")

    m = Model()
    m &= m.bool("a")

    r = m.solve(solver=_ClosingRaises, incremental=False)
    assert r.status == "optimum"
