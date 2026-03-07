import pytest

from hermax.model import Clause, Model


def test_cross_model_pollution_messages_are_clear():
    m1 = Model()
    m2 = Model()
    a1 = m1.bool("a1")
    a2 = m2.bool("a2")

    with pytest.raises(ValueError, match="different models"):
        _ = a1 | a2

    with pytest.raises(ValueError, match="different models"):
        _ = a1 + a2

    with pytest.raises(ValueError, match="different models"):
        _ = a1.implies(a2)


def test_detection_circuit_ban_messages_for_only_if_and_implies_conditions():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    pb = (a + b <= 1)  # ClauseGroup

    with pytest.raises(TypeError, match="must be a Literal"):
        _ = pb.only_if(pb)

    with pytest.raises(TypeError, match="must be a Literal"):
        _ = a.only_if(pb)

    with pytest.raises(TypeError, match="must be a Literal"):
        _ = Clause(m, [a, b]).only_if(pb)

def test_invalid_domain_error_messages_are_specific():
    m = Model()

    with pytest.raises(TypeError, match="lb and ub must be ints"):
        m.int("x", lb=0.0, ub=3)

    with pytest.raises(ValueError, match="lb < ub"):
        m.int("y", lb=3, ub=3)

    z = m.int("z", lb=1, ub=4)
    with pytest.raises(ValueError, match=r"outside domain \[1, 4\)"):
        _ = (z == 4)


def test_duplicate_identifier_error_messages_are_specific():
    m = Model()
    m.bool("a")
    with pytest.raises(ValueError, match="already registered in this model"):
        m.bool("a")

    m2 = Model()
    m2.bool_vector("v", 2)
    with pytest.raises(ValueError, match="already registered in this model"):
        m2.bool("v")

    m3 = Model()
    with pytest.raises(ValueError, match="reserved for internal model constants"):
        m3.bool("__true")


def test_unsupported_boolean_operation_messages_are_helpful():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")

    g = a & b
    assert len(g.clauses) == 2
    m &= g
    m &= ~c
    r = m.solve()
    assert r.ok is True
    assert r[a] is True
    assert r[b] is True

    cl = a | b
    with pytest.raises(TypeError, match="Cannot directly negate a Clause"):
        _ = ~cl

    with pytest.raises(TypeError, match="OR only supports Literal operands"):
        _ = cl | cl


def test_vector_operation_error_messages_are_explicit():
    m = Model()
    v1 = m.int_vector("v1", length=2, lb=0, ub=3)
    v2 = m.int_vector("v2", length=2, lb=0, ub=3)
    v3 = m.int_vector("v3", length=3, lb=0, ub=3)
    b = m.bool_vector("b", length=2)

    with pytest.raises(TypeError, match="Vector equality is ambiguous"):
        _ = (v1 == v2)

    with pytest.raises(TypeError, match="Vector ordering is ambiguous; use lexicographic_less_than"):
        _ = (v1 <= v2)

    with pytest.raises(ValueError, match="Vector lengths differ"):
        _ = v1.lexicographic_less_than(v3)

    with pytest.raises(TypeError, match="lexicographic_less_than expects IntVector"):
        _ = v1.lexicographic_less_than(b)  # type: ignore[arg-type]


def test_model_vector_and_matrix_indexing_messages_are_clear():
    m = Model()
    a = m.bool("a")
    x = m.int("x", lb=0, ub=3)

    with pytest.raises(ValueError, match="at least one item"):
        m.vector([])

    with pytest.raises(TypeError, match="homogeneous items"):
        m.vector([a, x])

    mat = m.int_matrix("m", rows=2, cols=2, lb=0, ub=3)
    # Single-index row access is supported for chained indexing (mat[i][j]).
    assert len(mat[0]) == 2
    with pytest.raises(TypeError, match="Use matrix\\[row, col\\] or matrix\\[row\\]\\[col\\] indexing"):
        _ = mat["bad"]

    with pytest.raises(TypeError, match="ints or slices"):
        _ = mat[0, "x"]  # type: ignore[index]


def test_export_and_solve_backend_error_messages_are_clear():
    m = Model()
    a = m.bool("a")
    m.obj[1] += a

    with pytest.raises(ValueError, match="contains soft clauses; use to_wcnf"):
        m.to_cnf()

    with pytest.raises(ValueError, match="Unsupported maxsat backend"):
        m.solve(maxsat_backend="not-rc2")
