from pysat.examples.rc2 import RC2 as PySATRC2
from pysat.solvers import Solver as PySATSolver

from hermax.internal.model_check import check_model, model_satisfies_hard_clauses
from hermax.model import Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def _solve_cnf_direct(m: Model, *, sat_solver_name: str = "g4"):
    cnf = m.to_cnf()
    with PySATSolver(name=sat_solver_name) as s:
        s.append_formula(cnf.clauses)
        sat = s.solve()
        return sat, (s.get_model() or []), cnf


def _solve_wcnf_direct(m: Model):
    wcnf = m.to_wcnf()
    with PySATRC2(wcnf) as rc2:
        model = rc2.compute()
        cost = None if model is None else int(rc2.cost)
        return model, cost, wcnf


def _add_sudoku9_constraints(m: Model, grid):
    # Rows and columns are all-different.
    for i in range(9):
        m &= grid.row(i).all_different()
        m &= grid.col(i).all_different()

    # 3x3 subgrids via NumPy-like slicing + flatten().
    for br in (0, 3, 6):
        for bc in (0, 3, 6):
            m &= grid[br:br + 3, bc:bc + 3].flatten().all_different()


def test_sudoku9_end_to_end_with_arbitrary_subgrid_views_single_clue():
    m = Model()
    grid = m.int_matrix("s", rows=9, cols=9, lb=1, ub=10)  # values {1..9}
    _add_sudoku9_constraints(m, grid)

    # Example-style single clue: enough to exercise typed matrices + arbitrary subgrid views.
    clue = (4, 4, 5)
    m &= (grid[clue[0], clue[1]] == clue[2])

    r = _solve_ok(m)
    sol = r[grid]

    # Check clue and Sudoku semantics from the decoded assignment.
    assert sol[clue[0]][clue[1]] == clue[2]

    for i in range(9):
        assert sorted(sol[i]) == list(range(1, 10))
        assert sorted(sol[r_][i] for r_ in range(9)) == list(range(1, 10))

    for br in (0, 3, 6):
        for bc in (0, 3, 6):
            box = [sol[br + dr][bc + dc] for dr in range(3) for dc in range(3)]
            assert sorted(box) == list(range(1, 10))


def test_sudoku9_detects_inconsistent_givens_unsat():
    m = Model()
    grid = m.int_matrix("s", rows=9, cols=9, lb=1, ub=10)
    _add_sudoku9_constraints(m, grid)

    # Contradict a row with duplicate givens.
    m &= (grid[0, 0] == 1)
    m &= (grid[0, 1] == 1)

    r = m.solve()
    assert r.status == "unsat"


def test_roundtrip_hard_only_cardinality_cnf_and_model_solve_agree():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # Cardinality-only constraints (unit coefficients) -> CardEnc path.
    m &= (a + b + c == 1)
    m &= a

    r_model = _solve_ok(m)
    assert r_model.status == "sat"
    assert r_model[a] is True
    assert sum([r_model[a], r_model[b], r_model[c]]) == 1

    sat, raw_direct, cnf = _solve_cnf_direct(m)
    assert sat is True
    r_direct = m.decode_model(raw_direct)
    assert r_direct[a] is True
    assert sum([r_direct[a], r_direct[b], r_direct[c]]) == 1
    assert model_satisfies_hard_clauses(cnf.clauses, raw_direct)
    assert model_satisfies_hard_clauses(cnf.clauses, r_model.raw_model or [])


def test_roundtrip_weighted_pb_maxsat_matches_direct_rc2_cost_and_model_checks():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    # Weighted PB hard constraints -> PBEnc path.
    m &= (2 * a + 3 * b + c >= 3)
    m &= (a + b + c <= 2)

    # Mixed softs: literals + cardinality ClauseGroup + weighted PB ClauseGroup.
    m.obj[4] += ~a
    m.obj[2] += ~b
    m.obj[3] += (a + b + c <= 1)
    m.obj[5] += (2 * a + b + c >= 2)

    r_model = _solve_ok(m)
    assert r_model.status == "optimum"

    raw_direct, cost_direct, wcnf = _solve_wcnf_direct(m)
    assert raw_direct is not None
    assert cost_direct is not None

    r_direct = m.decode_model(raw_direct)

    # Hard satisfiability for both models on exported WCNF hard clauses.
    chk_model = check_model(r_model.raw_model or [], wcnf.hard, list(zip(wcnf.soft, wcnf.wght)), r_model.cost)
    chk_direct = check_model(raw_direct, wcnf.hard, list(zip(wcnf.soft, wcnf.wght)), cost_direct)
    assert chk_model.hards_ok is True
    assert chk_direct.hards_ok is True
    assert chk_model.reported_cost_matches is True
    assert chk_direct.reported_cost_matches is True

    # Parity of optimum cost across convenience and explicit RC2.
    assert r_model.cost == cost_direct

    # Decoded assignments satisfy the intended hard semantics.
    assert (2 * int(r_model[a]) + 3 * int(r_model[b]) + int(r_model[c])) >= 3
    assert (int(r_direct[a]) + int(r_direct[b]) + int(r_direct[c])) <= 2


def test_roundtrip_mixed_typed_model_wcnf_export_manual_rc2_and_decode_agree():
    m = Model()
    color = m.enum("color", choices=["red", "green", "blue"], nullable=False)
    mode = m.enum("mode", choices=["eco", "turbo"], nullable=True)
    speed = m.int("speed", lb=1, ub=6)  # {1..5}
    boost = m.bool("boost")

    # Hard typed constraints compiled to literals / clause groups.
    m &= (speed >= 2)
    m &= (speed <= 4)
    m &= (color != "blue")
    m &= (boost.implies(speed >= 3))
    m &= ((color == "red").implies(~boost))

    # Soft preferences over typed views and booleans.
    m.obj[2] += (color == "green")
    m.obj[1] += (mode == "eco")
    m.obj[3] += ~boost
    m.obj[2] += (speed >= 4)

    r_model = _solve_ok(m)
    assert r_model.status == "optimum"

    raw_direct, cost_direct, wcnf = _solve_wcnf_direct(m)
    assert raw_direct is not None
    assert cost_direct is not None

    chk_model = check_model(r_model.raw_model or [], wcnf.hard, list(zip(wcnf.soft, wcnf.wght)), r_model.cost)
    chk_direct = check_model(raw_direct, wcnf.hard, list(zip(wcnf.soft, wcnf.wght)), cost_direct)
    assert chk_model.hards_ok is True
    assert chk_direct.hards_ok is True
    assert chk_model.reported_cost_matches is True
    assert chk_direct.reported_cost_matches is True
    assert r_model.cost == cost_direct

    decoded_model = r_model.assignment
    decoded_direct = m.decode_model(raw_direct)

    # Typed decode sanity on both paths.
    assert decoded_model[color] in {"red", "green"}
    assert decoded_direct[color] in {"red", "green"}
    assert decoded_model[speed] in {2, 3, 4}
    assert decoded_direct[speed] in {2, 3, 4}
    assert not (decoded_model[color] == "red" and decoded_model[boost] is True)
    assert not (decoded_direct[color] == "red" and decoded_direct[boost] is True)
