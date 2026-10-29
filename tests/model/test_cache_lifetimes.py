from hermax.model import Model


def test_temporary_fixed_integer_membership_does_not_reuse_another_value():
    m = Model()
    selected = m.int_set("selected", values=[1])
    m &= selected == {1}
    result = m.solve()
    for i in range(100):
        value = i % 2
        indicator = selected.contains(m.int(f"fixed{i}", value, value))
        assert result[indicator] is (value == 1)


def test_independent_temporary_intervals_do_not_share_an_orientation():
    m = Model()

    def add_pair(index):
        ap, bp = (2, 0) if (index // 2) % 2 else (0, 2)
        a = m.interval(f"a{index}", start=ap, duration=1, end=ap + 1)
        b = m.interval(f"b{index}", start=bp, duration=1, end=bp + 1)
        m.__iand__(a.no_overlap(b))

    for i in range(20):
        add_pair(i)
    assert m.solve().ok


def test_independent_temporary_vector_orders_do_not_share_witnesses():
    m = Model()
    for i in range(100):
        av, bv = ([0, 0], [0, 1]) if i % 3 == 0 else ([0, 9], [1, 0])
        left = m.vector([m.int(f"a{i}_{j}", v, v) for j, v in enumerate(av)])
        right = m.vector([m.int(f"b{i}_{j}", v, v) for j, v in enumerate(bv)])
        m &= left.lexicographic_less_than(right)
        del left, right
    assert m.solve().ok


def test_nullable_table_does_not_use_another_enums_none_indicator():
    m = Model()
    for i in range(50):
        item = m.enum(f"e{i}", [1, 2], nullable=True)
        m &= m.table([item], allowed=[(None,)])
        del item
    item = m.enum("selected", [1, 2], nullable=True)
    m &= item == 1
    m &= m.table([item], allowed=[(None,)])
    assert not m.solve().ok


def test_repeated_boolean_views_preserve_internal_comparison_names():
    m = Model()
    flags = m.bool_vector("b", 4)
    for _ in range(2):
        left = m.vector([m.as_int(flags[0]), m.as_int(flags[1])])
        right = m.vector([m.as_int(flags[2]), m.as_int(flags[3])])
        m &= left.lexicographic_less_than(right)
    assert m.solve().ok


def test_repeated_boolean_view_maximum_reuses_its_encoding():
    m = Model()
    flags = m.bool_vector("b", 2)
    first = m.max([m.as_int(flag) for flag in flags])
    before = m._next_id, len(m._hard)
    for _ in range(100):
        assert m.max([m.as_int(flag) for flag in flags]) is first
    assert (m._next_id, len(m._hard)) == before
