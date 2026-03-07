import pytest

from hermax.model import Model
from hermax.core.rc2 import RC2Reentrant
from hermax.portfolio import PortfolioSolver


def test_model_solve_hard_only_uses_sat_backend_and_returns_sat():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= a
    m &= (~a | b)

    r = m.solve()
    assert r.status == "sat"
    assert r.backend == "pysat.g4"
    assert r.cost is None
    assert r[a] is True
    assert r[b] is True


def test_model_solve_hard_only_unsat_status():
    m = Model()
    a = m.bool("a")
    m &= a
    m &= ~a

    r = m.solve()
    assert r.status == "unsat"
    assert r.backend == "pysat.g4"
    assert r.cost is None
    assert r.raw_model is None


def test_model_solve_soft_present_uses_rc2_and_returns_optimum():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Prefer a=true, b=false.
    m.obj[5] += a
    m.obj[2] += ~b

    r = m.solve()
    assert r.status == "optimum"
    assert r.backend.startswith("hermax.")
    assert r.cost == 0
    assert r[a] is True
    assert r[b] is False


def test_model_solve_soft_unsat_due_to_hard_contradiction():
    m = Model()
    a = m.bool("a")
    m &= a
    m &= ~a
    m.obj[3] += a

    r = m.solve()
    assert r.status == "unsat"
    assert r.backend.startswith("hermax.")
    assert r.cost is None
    assert r.raw_model is None


def test_model_solve_respects_custom_sat_solver_name():
    m = Model()
    a = m.bool("a")
    m &= a

    r = m.solve(sat_solver_name="m22")
    assert r.status == "sat"
    assert r.backend == "pysat.m22"
    assert r[a] is True


def test_model_solve_rejects_unknown_maxsat_backend_value():
    m = Model()
    a = m.bool("a")
    m.obj[1] += a

    with pytest.raises(ValueError, match="Unsupported maxsat backend"):
        m.solve(maxsat_backend="not-rc2")


def test_model_solve_result_ok_property_and_decoded_access():
    m = Model()
    a = m.bool("a")
    m &= a
    r = m.solve()

    assert r.ok is True
    assert r[a] is True
    assert r.assignment[a] is True


def test_model_solve_result_ok_false_for_unsat():
    m = Model()
    a = m.bool("a")
    m &= a
    m &= ~a

    r = m.solve()
    assert r.ok is False


def test_model_solve_with_boolean_constant_softs_uses_rc2_and_costs_match():
    m = Model()
    x = m.bool("x")
    m &= x
    m.obj[4] += True
    m.obj[9] += False

    r = m.solve()
    assert r.status == "optimum"
    assert r.backend.startswith("hermax.")
    assert r.cost == 9
    assert r[x] is True


def test_model_solve_hard_only_with_typed_declarations_respects_domain_constraints():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=False)
    speed = m.int("speed", lb=0, ub=4)

    r = m.solve()
    assert r.status == "sat"

    # Enum is non-nullable: exactly one choice should decode.
    assert r[color] in {"red", "green", "blue"}
    # Int is constrained to domain [0, 4).
    assert 0 <= r[speed] < 4


def test_model_solve_pure_soft_model_is_valid_maxsat_case():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")

    # Under soft-unit-clause semantics:
    #   obj[w] += lit   => pay w when lit is false
    # So the optimum is a=true, b=true with total cost 2.
    m.obj[5] += a
    m.obj[1] += ~a
    m.obj[2] += b
    m.obj[1] += ~b

    r = m.solve()
    assert r.status == "optimum"
    assert r.backend.startswith("hermax.")
    assert r.cost == 2
    assert r[a] is True
    assert r[b] is True


def test_model_solve_accepts_hermax_solver_class_rc2fork():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj[5] += a
    m.obj[2] += ~b

    r = m.solve(solver=RC2Reentrant)
    assert r.status == "optimum"
    assert r.cost == 0
    assert r[a] is True
    assert r[b] is False
    assert r.backend.startswith("hermax.")


def test_model_solve_accepts_hermax_solver_instance_rc2fork():
    m = Model()
    a = m.bool("a")
    m &= a
    inst = RC2Reentrant()

    r = m.solve(solver=inst)
    # A hard-only formula solved by a MaxSAT backend returns OPTIMUM.
    assert r.status == "optimum"
    assert r[a] is True
    assert r.backend.startswith("hermax.")

    inst.close()


def test_model_solve_accepts_portfolio_solver_class_with_kwargs():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m.obj[3] += a
    m.obj[1] += ~b

    r = m.solve(
        solver=PortfolioSolver,
        solver_kwargs={
            "solver_classes": [RC2Reentrant],
            "per_solver_timeout_s": 2.0,
            "overall_timeout_s": 5.0,
            "max_workers": 1,
            "selection_policy": "first_optimal_or_best_until_timeout",
        },
    )
    assert r.status in {"optimum", "interrupted_sat"}
    assert r.ok is True
    assert r.cost == 0
    assert r[a] is True
    assert r[b] is False
    assert r.backend.startswith("hermax.")


def test_model_solve_rejects_solver_kwargs_with_solver_instance():
    m = Model()
    inst = RC2Reentrant()
    try:
        with pytest.raises(ValueError, match="solver_kwargs"):
            m.solve(solver=inst, solver_kwargs={"x": 1})
    finally:
        inst.close()
