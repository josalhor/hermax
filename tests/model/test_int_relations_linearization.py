import itertools

from hermax.model import ClauseGroup, Model


OPS = ["==", "!=", "<=", "<", ">=", ">"]


def _apply_rel(m: Model, x, y, op: str):
    if op == "==":
        rel = (x == y)
    elif op == "!=":
        rel = (x != y)
    elif op == "<=":
        rel = x._relop_intvar(y, "<=")
    elif op == "<":
        rel = x._relop_intvar(y, "<")
    elif op == ">=":
        rel = x._relop_intvar(y, ">=")
    elif op == ">":
        rel = x._relop_intvar(y, ">")
    else:  # pragma: no cover
        raise ValueError(op)
    assert isinstance(rel, ClauseGroup)
    m &= rel
    return rel


def _truth(a: int, b: int, op: str) -> bool:
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == "<=":
        return a <= b
    if op == "<":
        return a < b
    if op == ">=":
        return a >= b
    if op == ">":
        return a > b
    raise ValueError(op)


def _pin(m: Model, x, xv: int, y, yv: int):
    m &= (x == xv)
    m &= (y == yv)


def _solve_status(m: Model) -> str:
    return m.solve().status


def test_intvar_relations_match_truth_table_same_domain_exhaustive_small():
    # Exhaustive semantic matrix for a representative same-domain case.
    for op in OPS:
        for xv, yv in itertools.product(range(0, 4), repeat=2):
            m = Model()
            x = m.int("x", lb=0, ub=4)
            y = m.int("y", lb=0, ub=4)
            _apply_rel(m, x, y, op)
            _pin(m, x, xv, y, yv)
            status = _solve_status(m)
            assert (status != "unsat") == _truth(xv, yv, op), (op, xv, yv, status)


def test_intvar_relations_match_truth_table_different_domains_exhaustive_small():
    # Exhaustive semantic matrix across shifted/unequal domains.
    x_domain = range(1, 5)   # {1,2,3,4}
    y_domain = range(3, 7)   # {3,4,5,6}
    for op in OPS:
        for xv, yv in itertools.product(x_domain, y_domain):
            m = Model()
            x = m.int("x", lb=1, ub=5)
            y = m.int("y", lb=3, ub=7)
            _apply_rel(m, x, y, op)
            _pin(m, x, xv, y, yv)
            status = _solve_status(m)
            assert (status != "unsat") == _truth(xv, yv, op), (op, xv, yv, status)


def test_intvar_relations_same_domain_do_not_introduce_aux_variables():
    m = Model()
    x = m.int("x", lb=0, ub=6)
    y = m.int("y", lb=0, ub=6)
    top_before = m._top_id()

    rels = [
        x == y,
        x != y,
        x._relop_intvar(y, "<="),
        x._relop_intvar(y, "<"),
        x._relop_intvar(y, ">="),
        x._relop_intvar(y, ">"),
    ]
    assert all(isinstance(r, ClauseGroup) for r in rels)
    assert m._top_id() == top_before


def test_intvar_relations_shifted_domains_only_materialize_internal_constants_not_aux():
    m = Model()
    x = m.int("x", lb=0, ub=6)
    y = m.int("y", lb=1, ub=7)
    top_before = m._top_id()

    _ = x._relop_intvar(y, "<=")
    _ = x._relop_intvar(y, ">=")
    _ = x._relop_intvar(y, "<")
    _ = x._relop_intvar(y, ">")

    # No auxiliaries should be introduced. Internal constants may or may not be
    # materialized depending on constant-folding strategy.
    assert m._top_id() - top_before <= 2
    if m._top_id() - top_before:
        assert set(m._registry.keys()).issuperset({"__true", "__false"})


def test_intvar_equality_linear_clause_shape_and_count_same_domain():
    m = Model()
    x = m.int("x", lb=0, ub=6)  # span 6 => cuts 1..5 (5 cuts)
    y = m.int("y", lb=0, ub=6)
    rel = x == y
    assert isinstance(rel, ClauseGroup)
    assert len(rel.clauses) == 2 * 5
    assert all(1 <= len(c.literals) <= 2 for c in rel.clauses)


def test_intvar_order_relations_linear_clause_shape_and_count_same_domain():
    m = Model()
    x = m.int("x", lb=2, ub=8)  # span 6 => cuts 3..7 (5 cuts)
    y = m.int("y", lb=2, ub=8)
    le = x._relop_intvar(y, "<=")
    ge = x._relop_intvar(y, ">=")
    lt = x._relop_intvar(y, "<")
    gt = x._relop_intvar(y, ">")

    assert len(le.clauses) == 5
    assert len(ge.clauses) == 5
    assert all(1 <= len(c.literals) <= 2 for c in le.clauses + ge.clauses)

    # Strict versions remain linear and compact (often cheaper than
    # non-strict + inequality after offset-aware direct compilation).
    assert all(1 <= len(c.literals) <= 2 for c in lt.clauses + gt.clauses)
    assert len(lt.clauses) <= len(le.clauses) + 1
    assert len(gt.clauses) <= len(ge.clauses) + 1


def test_intvar_inequality_no_new_vars_linear_and_clause_width_bounded():
    m = Model()
    x = m.int("x", lb=0, ub=8)
    y = m.int("y", lb=3, ub=9)
    top_before = m._top_id()
    neq = x != y
    top_after = m._top_id()

    overlap = min(x.ub, y.ub) - max(x.lb, y.lb)  # values {3,4,5,6,7}
    assert len(neq.clauses) == overlap
    assert top_after == top_before  # no new vars
    assert all(len(c.literals) <= 4 for c in neq.clauses)


def test_intvar_inequality_singleton_overlap_produces_empty_clause_when_impossible():
    m = Model()
    x = m.int("x", lb=5, ub=6)  # singleton {5}
    y = m.int("y", lb=5, ub=6)  # singleton {5}
    neq = x != y
    assert len(neq.clauses) == 1
    assert len(neq.clauses[0].literals) == 0
    m &= neq
    assert m.solve().status == "unsat"


def test_intvar_relations_compose_correctly_in_vectors_after_linearization():
    m = Model()
    v = m.int_vector("v", length=3, lb=0, ub=4)
    w = m.int_vector("w", length=3, lb=0, ub=4)

    m &= v.increasing()
    m &= w.increasing()
    m &= v.lexicographic_less_than(w)

    # Concrete satisfying assignment should still work after scalar relation rewrite.
    m &= (v[0] == 0)
    m &= (v[1] == 1)
    m &= (v[2] == 2)
    m &= (w[0] == 0)
    m &= (w[1] == 1)
    m &= (w[2] == 3)

    r = m.solve()
    assert r.ok is True
    assert r[v] == [0, 1, 2]
    assert r[w] == [0, 1, 3]
