import pytest

from hermax.model import BoolMatrix, EnumMatrix, IntMatrix, IntVector, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_int_matrix_construction_shape_and_element_names():
    m = Model()
    mat = m.int_matrix("m", rows=2, cols=3, lb=0, ub=4)

    assert isinstance(mat, IntMatrix)
    assert mat.name == "m"
    assert len(mat._grid) == 2
    assert len(mat._grid[0]) == 3
    assert len(mat._grid[1]) == 3

    assert mat._grid[0][0].name == "m[0,0]"
    assert mat._grid[0][2].name == "m[0,2]"
    assert mat._grid[1][1].name == "m[1,1]"
    assert all(len(cell._threshold_lits) == 3 for row in mat._grid for cell in row)


def test_bool_matrix_and_enum_matrix_construction_and_typed_views():
    m = Model()
    bm = m.bool_matrix("bm", rows=2, cols=2)
    em = m.enum_matrix("em", rows=2, cols=2, choices=["r", "g"], nullable=False)

    assert isinstance(bm, BoolMatrix)
    assert isinstance(em, EnumMatrix)

    br0 = bm.row(0)
    bc1 = bm.col(1)
    er1 = em.row(1)
    ec0 = em.col(0)

    from hermax.model import BoolVector, EnumVector

    assert isinstance(br0, BoolVector)
    assert isinstance(bc1, BoolVector)
    assert isinstance(er1, EnumVector)
    assert isinstance(ec0, EnumVector)
    assert len(br0) == 2 and len(bc1) == 2
    assert len(er1) == 2 and len(ec0) == 2
    assert br0[0] is bm._grid[0][0]
    assert ec0[1] is em._grid[1][0]


def test_numpy_like_matrix_indexing_returns_cells_vectors_and_submatrix_views():
    m = Model()
    im = m.int_matrix("im", rows=3, cols=4, lb=0, ub=3)
    bm = m.bool_matrix("bm", rows=2, cols=3)
    em = m.enum_matrix("em", rows=2, cols=3, choices=["r", "g"], nullable=True)

    from hermax.model import BoolVector, EnumVector

    assert im[1, 2] is im._grid[1][2]
    assert bm[0, 1] is bm._grid[0][1]
    assert em[1, 0] is em._grid[1][0]

    r = im[1, :]
    c = im[:, 2]
    assert isinstance(r, IntVector)
    assert isinstance(c, IntVector)
    assert [x for x in r] == im._grid[1]
    assert [x for x in c] == [im._grid[i][2] for i in range(3)]

    br = bm[0, :]
    ec = em[:, 1]
    assert isinstance(br, BoolVector)
    assert isinstance(ec, EnumVector)

    sub = im[1:3, 1:4]
    assert sub._rows == 2 and sub._cols == 3
    assert sub._grid[0][0] is im._grid[1][1]
    assert sub._grid[1][2] is im._grid[2][3]
    flat = sub.flatten()
    assert isinstance(flat, IntVector)
    assert [x for x in flat] == [
        im._grid[1][1], im._grid[1][2], im._grid[1][3],
        im._grid[2][1], im._grid[2][2], im._grid[2][3],
    ]
    # Chained indexing should match tuple indexing.
    assert im[1][2] is im[1, 2]
    assert bm[0][1] is bm[0, 1]
    assert em[1][0] is em[1, 0]


def test_matrix_row_and_col_return_typed_vectors_with_correct_lengths():
    m = Model()
    mat = m.int_matrix("m", rows=3, cols=2, lb=0, ub=5)

    r0 = mat.row(0)
    r2 = mat.row(2)
    c0 = mat.col(0)
    c1 = mat.col(1)

    assert isinstance(r0, IntVector)
    assert isinstance(r2, IntVector)
    assert isinstance(c0, IntVector)
    assert isinstance(c1, IntVector)

    assert len(r0) == 2
    assert len(r2) == 2
    assert len(c0) == 3
    assert len(c1) == 3

    # View names are typed helper names (not registered containers).
    assert r0.name == "m.row(0)"
    assert c1.name == "m.col(1)"


def test_matrix_row_and_col_views_preserve_element_identity():
    m = Model()
    mat = m.int_matrix("m", rows=2, cols=2, lb=0, ub=4)

    r0 = mat.row(0)
    r1 = mat.row(1)
    c0 = mat.col(0)
    c1 = mat.col(1)

    assert r0[0] is mat._grid[0][0]
    assert r0[1] is mat._grid[0][1]
    assert r1[0] is mat._grid[1][0]
    assert r1[1] is mat._grid[1][1]
    assert c0[0] is mat._grid[0][0]
    assert c0[1] is mat._grid[1][0]
    assert c1[0] is mat._grid[0][1]
    assert c1[1] is mat._grid[1][1]


def test_matrix_decode_via_assignment_view_end_to_end():
    m = Model()
    mat = m.int_matrix("m", rows=2, cols=2, lb=0, ub=4)

    # Use exact Int==int literals to pin values.
    m &= (mat._grid[0][0] == 0)
    m &= (mat._grid[0][1] == 1)
    m &= (mat._grid[1][0] == 2)
    m &= (mat._grid[1][1] == 3)

    r = _solve_ok(m)
    assert r[mat] == [[0, 1], [2, 3]]
    assert r[mat.row(0)] == [0, 1]
    assert r[mat.col(1)] == [1, 3]
    assert r[mat[0, :]] == [0, 1]
    assert r[mat[:, 1]] == [1, 3]
    assert r[mat[:, :]] == [[0, 1], [2, 3]]
    assert r[mat[:, :].flatten()] == [0, 1, 2, 3]


def test_bool_and_enum_matrix_decode_end_to_end():
    m = Model()
    bm = m.bool_matrix("bm", rows=2, cols=2)
    em = m.enum_matrix("em", rows=2, cols=2, choices=["r", "g"], nullable=False)

    m &= bm._grid[0][0]
    m &= ~bm._grid[0][1]
    m &= ~bm._grid[1][0]
    m &= bm._grid[1][1]

    m &= (em._grid[0][0] == "r")
    m &= (em._grid[0][1] == "g")
    m &= (em._grid[1][0] == "g")
    m &= (em._grid[1][1] == "r")

    r = _solve_ok(m)
    assert r[bm] == [[True, False], [False, True]]
    assert r[em] == [["r", "g"], ["g", "r"]]
    assert r[bm.row(0)] == [True, False]
    assert r[em.col(1)] == ["g", "r"]


def test_matrix_cells_participate_in_vector_constraints_end_to_end():
    m = Model()
    mat = m.int_matrix("m", rows=2, cols=2, lb=0, ub=4)

    # Enforce row 0 increasing and row 1 increasing, plus lex(row0,row1).
    m &= mat.row(0).increasing()
    m &= mat.row(1).increasing()
    m &= mat.row(0).lexicographic_less_than(mat.row(1))

    # Pin a concrete satisfying assignment:
    # row0 = [0,1], row1 = [1,2]
    m &= (mat._grid[0][0] == 0)
    m &= (mat._grid[0][1] == 1)
    m &= (mat._grid[1][0] == 1)
    m &= (mat._grid[1][1] == 2)

    r = _solve_ok(m)
    assert r[mat] == [[0, 1], [1, 2]]


def test_arbitrary_subset_intvector_view_from_matrix_cells_supports_all_different():
    m = Model()
    grid = m.int_matrix("g", rows=3, cols=3, lb=1, ub=4)  # domain {1,2,3}

    # Sudoku-style arbitrary subset (e.g., a 2x2-ish sample / custom region).
    region = m.vector([grid._grid[0][0], grid._grid[0][1], grid._grid[1][0]], name="region")
    assert isinstance(region, IntVector)
    m &= region.all_different()

    # Force duplicate values in the subset -> UNSAT.
    m &= (grid._grid[0][0] == 1)
    m &= (grid._grid[0][1] == 1)
    r = m.solve()
    assert r.status == "unsat"


def test_submatrix_flatten_supports_sudoku_style_box_constraints():
    m = Model()
    grid = m.int_matrix("g", rows=3, cols=3, lb=1, ub=6)  # {1,2,3,4,5}

    # NumPy-like submatrix slicing plus flatten().
    box = grid[0:2, 0:2].flatten()
    m &= box.all_different()
    m &= (grid[0, 0] == 1)
    m &= (grid[0, 1] == 2)
    m &= (grid[1, 0] == 3)
    m &= (grid[1, 1] == 4)

    r = _solve_ok(m)
    assert sorted(r[box]) == [1, 2, 3, 4]


def test_matrix_subvector_is_in_table_constraint_reads_cleanly():
    m = Model()
    grid = m.int_matrix("g", rows=2, cols=2, lb=0, ub=5)
    spec = grid[:, :].flatten()
    m &= spec.is_in([(1, 2, 3, 4), (4, 3, 2, 1)])
    m &= (grid[0, 0] == 4)
    m &= (grid[0, 1] == 3)
    m &= (grid[1, 0] == 2)
    m &= (grid[1, 1] == 1)
    r = _solve_ok(m)
    assert r[spec] == [4, 3, 2, 1]


def test_model_vector_builds_typed_views_and_validates_homogeneity():
    m = Model()
    bm = m.bool_matrix("bm", rows=1, cols=2)
    em = m.enum_matrix("em", rows=1, cols=2, choices=["r", "g"], nullable=True)
    im = m.int_matrix("im", rows=1, cols=2, lb=0, ub=3)

    from hermax.model import BoolVector, EnumVector

    vb = m.vector([bm._grid[0][0], bm._grid[0][1]], name="vb")
    ve = m.vector([em._grid[0][0], em._grid[0][1]], name="ve")
    vi = m.vector([im._grid[0][0], im._grid[0][1]], name="vi")
    assert isinstance(vb, BoolVector)
    assert isinstance(ve, EnumVector)
    assert isinstance(vi, IntVector)

    with pytest.raises(TypeError, match="homogeneous items"):
        m.vector([bm._grid[0][0], im._grid[0][0]])

    with pytest.raises(ValueError, match="at least one item"):
        m.vector([])


def test_int_matrix_name_collisions_are_rejected():
    m = Model()
    m.int_matrix("m", rows=1, cols=1, lb=0, ub=2)

    with pytest.raises(ValueError, match="already registered"):
        m.int_matrix("m", rows=1, cols=1, lb=0, ub=2)

    m2 = Model()
    m2.bool("x")
    with pytest.raises(ValueError, match="already registered"):
        m2.int_matrix("x", rows=1, cols=1, lb=0, ub=2)


def test_bool_and_enum_matrix_name_collisions_are_rejected():
    m = Model()
    m.bool_matrix("b", rows=1, cols=1)
    with pytest.raises(ValueError, match="already registered"):
        m.enum_matrix("b", rows=1, cols=1, choices=["r", "g"])

    m2 = Model()
    m2.enum_matrix("e", rows=1, cols=1, choices=["r", "g"])
    with pytest.raises(ValueError, match="already registered"):
        m2.bool_matrix("e", rows=1, cols=1)


def test_int_matrix_invalid_bounds_propagate_from_int_cells():
    m = Model()
    with pytest.raises(ValueError):
        m.int_matrix("m", rows=2, cols=2, lb=3, ub=3)


def test_matrix_declaration_emits_cell_domain_constraints_in_export():
    m = Model()
    mat = m.int_matrix("m", rows=2, cols=2, lb=0, ub=3)  # each cell contributes 2 threshold lits + 1 clause

    # IDs should be contiguous across the 4 cells * 2 threshold lits.
    ids = [lit.id for row in mat._grid for cell in row for lit in cell._threshold_lits]
    assert ids == list(range(1, 9))

    cnf = m.to_cnf()
    # Each cell with span=3 contributes 1 monotonicity clause in compact ladder.
    assert len(cnf.clauses) == 4


def test_bool_matrix_declaration_emits_no_domain_constraints_but_enum_matrix_does():
    m = Model()
    _bm = m.bool_matrix("b", rows=2, cols=2)
    em = m.enum_matrix("e", rows=1, cols=2, choices=["r", "g"], nullable=False)

    cnf = m.to_cnf()
    hard = {tuple(cl) for cl in cnf.clauses}
    # Bool cells add no domain clauses. Two enum cells (2 choices each) add 4 clauses total.
    e00r = em._grid[0][0]._choice_lits["r"].id
    e00g = em._grid[0][0]._choice_lits["g"].id
    e01r = em._grid[0][1]._choice_lits["r"].id
    e01g = em._grid[0][1]._choice_lits["g"].id
    expected = {
        (-e00r, -e00g), (e00r, e00g),
        (-e01r, -e01g), (e01r, e01g),
    }
    assert hard == expected


def test_matrix_row_col_helpers_are_ephemeral_views_not_registered_containers():
    m = Model()
    mat = m.int_matrix("m", rows=2, cols=2, lb=0, ub=3)
    r0 = mat.row(0)
    c1 = mat.col(1)

    # Helper views should not reserve container names in the model registry.
    m.int_vector("r0", length=2, lb=0, ub=3)
    m.int_vector("c1", length=2, lb=0, ub=3)

    # But they still behave like real vectors.
    assert isinstance(r0, IntVector)
    assert isinstance(c1, IntVector)
