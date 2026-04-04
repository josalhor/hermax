from hermax.model import Model, Literal, IntVar, IntSetVar, EnumVar

def test_cumulative_task_backend_gating_literal():
    """Point (4): confirm eq_i is always a Literal in cumulative task backend."""
    m = Model()
    s = [m.int(f"s{i}", lb=0, ub=10) for i in range(2)]
    # Use task backend explicitly
    # We want to verify that in the implementation, eq_i = (si == t)
    # is always a Literal.
    # While we can't easily check internal locals, we can check 
    # that the constraint works and doesn't crash.
    m.cumulative(s, [2, 2], [1, 1], capacity=1, backend="task")
    
    # Also verify that si == t is a Literal in Hermax
    for si in s:
        for t in range(si.lb, si.ub + 1):
            eq_i = (si == t)
            assert isinstance(eq_i, Literal), f"si == t produced {type(eq_i)} instead of Literal"

def test_solve_result_decode_all_types():
    """Point (5): comprehensive SolveResult typed variable decode tests."""
    m = Model()
    
    # 1. IntVar
    x = m.int("x", lb=0, ub=10)
    m &= (x == 7)
    
    # 2. BoolVector (Literal)
    b = m.bool("b")
    m &= b
    v_bool = m.vector([b, ~b], name="v_bool")
    
    # 3. EnumVar
    e = m.enum("e", ["red", "green", "blue"])
    m &= (e == "green")
    
    # 4. IntSetVar
    s = m.int_set("s", lb=1, ub=5)
    m &= (s == {1, 3, 4})
    
    # 5. Containers
    y = m.int("y", lb=0, ub=20)
    m &= (y == x + 1)
    v_int = m.vector([x, y], name="v_int")
    d_int = m.int_dict("d_int", ["a", "b"], lb=0, ub=20)
    m &= (d_int["a"] == x)
    m &= (d_int["b"] == y + 1)
    
    # 6. Matrix
    mat = m.int_matrix("mat", rows=2, cols=2, lb=0, ub=2)
    m &= (mat[0, 0] == 1)
    m &= (mat[0, 1] == 0)
    m &= (mat[1, 0] == 0)
    m &= (mat[1, 1] == 1)
    
    # 7. IntervalVar
    iv = m.interval("iv", start=0, duration=5, end=10)
    m &= (iv.start == 2)
    
    r = m.solve()
    assert r.ok
    
    # Verify decoding
    assert r[x] == 7
    assert r[b] is True
    assert r[v_bool] == [True, False]
    assert r[e] == "green"
    assert r[s] == {1, 3, 4}
    assert r[v_int] == [7, 8]
    assert r[d_int] == {"a": 7, "b": 9}
    assert r[mat] == [[1, 0], [0, 1]]
    
    iv_decoded = r[iv]
    assert iv_decoded["start"] == 2
    assert iv_decoded["duration"] == 5
    assert iv_decoded["end"] == 7
    
    # Test nested decode
    nested = [(x, b), {"set": s, "enum": e}]
    assert r[nested] == [(7, True), {"set": {1, 3, 4}, "enum": "green"}]
