import pytest

from hermax.model import Model


@pytest.mark.parametrize(
    "kind",
    [
        "comparison",
        "equality",
        "distance",
        "increasing",
        "all_different",
        "table",
        "lex",
        "vector_neq",
        "set_eq",
        "set_neq",
        "subset",
        "constant_set",
        "array_element",
        "variable_element",
    ],
)
def test_constraint_construction_does_not_populate_operation_cache(kind):
    m = Model()
    xs = m.int_vector("x", 3, 0, 3)
    ys = m.int_vector("y", 3, 0, 3)
    a = m.int_set("a", values=[0, 1])
    b = m.int_set("b", values=[0, 1])
    index = m.int("index", 0, 2)

    def build():
        if kind == "comparison":
            return xs[0] <= ys[0]
        if kind == "equality":
            return xs[0] == ys[0]
        if kind == "distance":
            return xs[0].distance_at_most(ys[0], 2)
        if kind == "increasing":
            return xs.increasing()
        if kind == "all_different":
            return xs.all_different()
        if kind == "table":
            return m.table(xs, allowed=[(0, 1, 2), (1, 2, 3)])
        if kind == "lex":
            return xs.lexicographic_less_than(ys)
        if kind == "vector_neq":
            return xs != ys
        if kind == "set_eq":
            return a == b
        if kind == "set_neq":
            return a != b
        if kind == "subset":
            return a.subset_of(b)
        if kind == "constant_set":
            return a != {0}
        if kind == "array_element":
            return ([3, 1, 2] @ index) <= 2
        return xs[index] <= 2

    for _ in range(2):
        tuple(build())
    assert not m._operation_cache._results


def test_operation_cache_contains_only_result_variables():
    from hermax.model.variables import IntVar, IntSetVar, IntVector

    m = Model()
    xs = m.int_vector("x", 3, 0, 4)
    a = m.int_set("a", values=[0, 1, 2])
    b = m.int_set("b", values=[0, 1, 2])
    m.floor_div(xs[0], 2)
    m.modulo(xs[0], 3)
    m.scale(xs[0], -2)
    m.min(xs)
    m.max(xs)
    m.sum_var(xs)
    a.card()
    a.union(b)
    a.intersection(b)
    a.difference(b)
    a.symmetric_difference(b)
    xs.running_sum()
    xs.running_min()
    xs.running_max()
    assert m._operation_cache._results
    assert all(
        isinstance(result, (IntVar, IntSetVar, IntVector))
        for result in m._operation_cache._results.values()
    )
