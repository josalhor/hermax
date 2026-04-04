import pytest

from pysat.formula import CNF, WCNF

from hermax.model import Model


def test_to_cnf_hard_only_and_rejects_soft():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a | b)

    cnf = m.to_cnf()
    assert isinstance(cnf, CNF)
    assert len(cnf.clauses) >= 1

    m.obj[1] += ~a
    with pytest.raises(ValueError, match="soft clauses"):
        m.to_cnf()


def test_to_wcnf_contains_hard_and_soft():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    m &= (a | b)
    m.obj[3] += ~a

    w = m.to_wcnf()
    assert isinstance(w, WCNF)
    assert len(w.hard) >= 1
    assert len(w.soft) >= 1
    assert 3 in w.wght


def test_decode_model_for_bool_enum_int_vector():
    m = Model()
    a = m.bool("a")
    color = m.enum("color", choices=["red", "green"])
    speed = m.int("speed", lb=0, ub=4)
    vec = m.bool_vector("v", length=2)

    # Seed some exact/int comparator literals so decode has something stable.
    _ = (speed == 2)
    _ = (speed <= 1)

    raw = [
        a.id,
        color._choice_lits["green"].id,
        -(color._choice_lits["red"].id),
        speed._eq_lits[2].id,
        vec[0].id,
        -vec[1].id,
    ]
    assignment = m.decode_model(raw)

    assert assignment[a] is True
    assert assignment[color] == "green"
    assert assignment[speed] == 2
    assert assignment[vec] == [True, False]


def test_model_solve_defaults_sat_and_maxsat():
    # Hard-only -> SAT backend
    m1 = Model()
    a = m1.bool("a")
    m1 &= a
    r1 = m1.solve()
    assert r1.status == "sat"
    assert r1[a] is True
    assert r1.cost is None

    # Soft present -> RC2 MaxSAT backend
    m2 = Model()
    x = m2.bool("x")
    m2.obj[5] += x      # pay if x is false
    m2.obj[1] += ~x     # pay if x is true
    r2 = m2.solve()
    assert r2.status == "optimum"
    assert r2.cost == 1
    assert r2[x] is True

