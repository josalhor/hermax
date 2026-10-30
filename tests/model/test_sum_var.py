import pytest
from hermax.model import Model

def test_sum_var_basic():
    m = Model()
    x = [m.int(f"x_{i}", lb=0, ub=4) for i in range(5)]  # 5 vars, max sum = 15
    s = m.sum_var(x)
    m &= (s == 12)
    
    r = m.solve()
    assert r.ok
    assert r[s] == 12
    assert sum(r[v] for v in x) == 12

def test_sum_var_empty_raises():
    m = Model()
    with pytest.raises(ValueError, match="empty sequence"):
        m.sum_var([])

def test_sum_var_single():
    m = Model()
    x = m.int("x", lb=0, ub=5)
    s = m.sum_var([x])
    assert s is x

def test_sum_var_tree_reduction_semantics():
    # 16 vars in [0, 2), tree sum = some value in [0, 16]
    m = Model()
    x = [m.int(f"b_{i}", lb=0, ub=2) for i in range(16)]
    s = m.sum_var(x)
    
    # All ones -> sum = 16. But ub=2 means each is 0 or 1.
    for v in x:
        m &= (v == 1)
    
    r = m.solve()
    assert r.ok
    assert r[s] == 16
    assert sum(r[v] for v in x) == 16


def test_sum_var_width_aware_merge_is_order_robust_for_mixed_domains():
    def stats(widths):
        m = Model()
        xs = [m.int(f"x_{i}", lb=0, ub=w) for i, w in enumerate(widths)]
        m.sum_var(xs, name="total")
        return m._top_id(), len(m._hard)

    widths = [1, 2, 4, 8, 16, 32]
    assert stats(widths) == stats(list(reversed(widths)))


@pytest.mark.parametrize("kind", ["bool", "integer", "shifted", "negated"])
def test_sum_var_two_value_inputs_use_one_count_encoding(kind):
    def stats(via_sum_var):
        m = Model()
        if kind in ("bool", "negated"):
            inputs = list(m.bool_vector("x", 32))
            if kind == "negated":
                inputs = [~item if i % 2 else item for i, item in enumerate(inputs)]
            lower = 0
        else:
            lower = -3 if kind == "shifted" else 0
            inputs = list(m.int_vector("x", 32, lower, lower + 1))
        if via_sum_var:
            result = m.sum_var(inputs, name="total")
            assert result.name == "total_step30"
        else:
            result = m.int("total", 32 * lower, 32 * (lower + 1))
            m &= result == sum(inputs)
        cnf = m.to_cnf()
        return cnf.nv, len(cnf.clauses)

    assert stats(True) == stats(False)
