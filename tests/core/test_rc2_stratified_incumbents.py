from pysat.formula import WCNF
from itertools import product
import random
import time
import tempfile
import warnings

from hermax.core.rc2.rc2 import RC2Stratified
from hermax.core.rc2 import rc2_reentrant
from hermax.core.rc2.rc2_reentrant import RC2Reentrant
from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.internal.model_check import check_model
from hermax.model import Model
from hermax.portfolio._test_solvers import SlowAfterIncumbentRC2
from hermax.portfolio import PortfolioSolver
from hermax.portfolio.solver import _WorkerProc
from hermax.internal.subprocess_oneshot import _dumps_frame


def test_stratified_reports_valid_full_cost_incumbents():
    formula = WCNF()
    formula.append([1, 2])
    formula.append([-1], weight=100)
    formula.append([-2], weight=1)
    seen = []
    with RC2Stratified(formula, on_model=lambda model: seen.append(model)) as solver:
        optimal = solver.compute()
    assert seen
    for model in seen:
        checked = check_model(model, [[1, 2]], [([-1], 100), ([-2], 1)])
        assert checked.hards_ok
        assert checked.recomputed_cost >= 1
    assert check_model(optimal, [[1, 2]], [([-1], 100), ([-2], 1)]).recomputed_cost == 1


def test_rc2_wrapper_reports_cost_of_original_objective():
    solver = RC2Reentrant()
    solver.add_clause([1, 2])
    solver.add_soft_unit(-1, 100)
    solver.add_soft_unit(-2, 1)
    seen = []
    solver._set_incumbent_callback(lambda model, cost: seen.append((model, cost)))
    try:
        assert solver.solve()
        assert solver.get_status() == SolveStatus.OPTIMUM
        assert seen
        for model, cost in seen:
            result = check_model(model, [[1, 2]], [([-1], 100), ([-2], 1)])
            assert result.hards_ok and cost == result.recomputed_cost
    finally:
        solver.close()


def test_rc2_wrapper_uses_stratified_solver(monkeypatch):
    constructions = []
    real_solver = rc2_reentrant.RC2Stratified

    def construct(*args, **kwargs):
        constructions.append(True)
        return real_solver(*args, **kwargs)

    monkeypatch.setattr(rc2_reentrant, "RC2Stratified", construct)
    solver = RC2Reentrant()
    try:
        solver.add_soft_unit(1, 1)
        assert solver.solve()
        assert constructions == [True]
    finally:
        solver.close()


def test_model_returns_reported_incumbent_when_worker_times_out():
    model = Model()
    a, b = model.bool("a"), model.bool("b")
    model &= a | b
    model.obj += 100 * a
    model.obj += b
    result = model.solve(solver=SlowAfterIncumbentRC2, incremental=False, time_limit=1)
    assert result.status == "interrupted_sat"
    assert result.ok and not result.proven
    assert result[a] or result[b]
    assert result.cost == (100 if result[a] else 0) + (1 if result[b] else 0)


def test_single_weight_level_can_return_a_feasible_incumbent():
    model = Model()
    a, b = model.bool("a"), model.bool("b")
    model &= a | b
    model.obj += a
    model.obj += b
    result = model.solve(solver=SlowAfterIncumbentRC2, incremental=False,
                         time_limit=1, assumptions=[~a])
    assert result.status == "interrupted_sat"
    assert result[a] is False and result[b] is True
    assert result.cost == 1


def test_direct_rc2_timeout_returns_incumbent_and_supports_reuse():
    solver = SlowAfterIncumbentRC2()
    solver.add_clause([1, 2])
    solver.add_clause([-1, -2], weight=3)
    try:
        assert solver.solve(assumptions=[-1], time_limit=1)
        assert solver.get_status() == SolveStatus.INTERRUPTED_SAT
        assert solver.get_model() == [-1, 2]
        assert solver.get_cost() == 0
        assert solver.solve(assumptions=[1])
        assert solver.get_status() == SolveStatus.OPTIMUM
    finally:
        solver.close()


def test_model_explicit_rc2_supports_timed_incremental_reuse():
    model = Model()
    x = model.bool("x")
    model.obj += ~x
    first = model.solve(solver=RC2Reentrant, backend="maxsat", time_limit=2)
    assert first.status == "optimum" and first[x] is True
    model &= ~x
    second = model.solve(backend="maxsat", time_limit=2)
    assert second.status == "optimum" and second[x] is False and second.cost == 1


def test_timed_model_keeps_soft_clause_variables_distinct_from_auxiliaries():
    model = Model()
    x, y = model.bool("x"), model.bool("y")
    penalty_satisfied = model.bool()
    model &= (x | y).iff(penalty_satisfied)
    model.obj += ~penalty_satisfied
    result = model.solve(incremental=False, time_limit=2, assumptions=[~x, ~y])
    assert result.status == "optimum"
    assert result[x] is False and result[y] is False
    assert result.cost == 1


def test_first_valid_policy_stops_on_live_incumbent():
    solver = PortfolioSolver([SlowAfterIncumbentRC2], selection_policy="first_valid",
                             overall_time_limit_s=5, per_solver_time_limit_s=5)
    solver.add_clause([1, 2])
    solver.add_soft_unit(-1, 100)
    solver.add_soft_unit(-2, 1)
    start = time.monotonic()
    try:
        assert solver.solve()
        assert solver.get_status() == SolveStatus.INTERRUPTED_SAT
        assert time.monotonic() - start < 4
    finally:
        solver.close()


def test_stratified_optimum_matches_brute_force():
    randomizer = random.Random(17)
    for _ in range(50):
        hard = [[randomizer.choice((-1, 1)) * randomizer.randint(1, 4)
                 for _ in range(2)] for _ in range(3)]
        soft = [([randomizer.choice((-1, 1)) * randomizer.randint(1, 4)
                  for _ in range(randomizer.randint(1, 2))], randomizer.randint(1, 20))
                for _ in range(5)]
        solver = RC2Reentrant()
        for clause in hard:
            solver.add_clause(clause)
        for clause, weight in soft:
            solver.add_clause(clause, weight)
        candidates = [check_model([i if bit else -i for i, bit in enumerate(bits, 1)], hard, soft)
                      for bits in product((False, True), repeat=4)]
        costs = [candidate.recomputed_cost for candidate in candidates if candidate.hards_ok]
        try:
            if costs:
                assert solver.solve()
                assert solver.get_status() == SolveStatus.OPTIMUM
                assert solver.get_cost() == min(costs)
            else:
                assert not solver.solve()
                assert solver.get_status() == SolveStatus.UNSAT
        finally:
            solver.close()


def test_portfolio_waits_for_full_report_and_rejects_invalid_incumbent():
    solver = PortfolioSolver([RC2Reentrant])
    solver.add_clause([1])
    with tempfile.NamedTemporaryFile(delete=False) as stream:
        path = stream.name
    worker = _WorkerProc(solver_name="test", worker_class_path="test", proc=None,
                         stdout_file=tempfile.TemporaryFile(), stderr_file=tempfile.TemporaryFile(),
                         start_s=0, deadline_s=1, timeout_s=1, grace_s=0,
                         request_assumptions=[], incumbent_path=path)
    frame = _dumps_frame({"model": [1], "cost": 0})
    try:
        with open(path, "ab") as stream:
            stream.write(frame[:5])
        assert solver._read_incumbents(worker) == []
        with open(path, "ab") as stream:
            stream.write(frame[5:])
            stream.write(_dumps_frame({"model": [-1], "cost": 0}))
        with warnings.catch_warnings(record=True) as caught:
            candidates = solver._read_incumbents(worker)
        assert len(candidates) == 1 and candidates[0]["model"] == [1]
        assert caught
        assert solver._read_incumbents(worker) == []
    finally:
        worker.cleanup()
        solver.close()
