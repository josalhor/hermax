"""Check global reification against Python predicates over all small assignments."""

import itertools
import random

import pytest
from pysat.solvers import Solver

from hermax.model import Clause, ClauseGroup, EnumVar, IntVar, Literal, Model


MODES = ("iff", "eq", "ne", "only_if", "literal_implies", "implies", "both")


def _connect(global_constraint, indicator, mode):
    if mode == "iff":
        return global_constraint.iff(indicator)
    if mode == "eq":
        return indicator == global_constraint
    if mode == "ne":
        return indicator != global_constraint
    if mode == "only_if":
        return global_constraint.only_if(indicator)
    if mode == "literal_implies":
        return indicator.implies(global_constraint)
    if mode == "implies":
        return global_constraint.implies(indicator)
    if mode == "both":
        return global_constraint.only_if(indicator) & global_constraint.implies(indicator)
    raise AssertionError(mode)


def _holds(value, indicator, mode):
    if mode in ("iff", "eq", "both"):
        return value == indicator
    if mode == "ne":
        return value != indicator
    if mode in ("only_if", "literal_implies"):
        return not indicator or value
    return not value or indicator


def _assignment(model, item, value):
    if isinstance(item, IntVar):
        literals = item._exact_value_atoms(value)
    elif isinstance(item, Literal):
        literals = [item if value else ~item]
    elif isinstance(item, EnumVar):
        literals = (
            [~lit for lit in item._choice_lits.values()]
            if value is None else [item == value]
        )
    else:
        raise AssertionError(type(item))
    return [model._lit_to_dimacs(lit) for lit in literals]


def _check(model, items, domains, constraint, predicate, mode, *, negated=False, gated=False):
    boolean = model.bool("indicator")
    indicator = ~boolean if negated else boolean
    connected = _connect(constraint, indicator, mode)
    gate = model.bool("gate") if gated else None
    model &= connected.only_if(gate) if gated else connected
    with Solver(name="g3", bootstrap_with=model.to_cnf().clauses) as solver:
        for values in itertools.product(*domains):
            fixed = [dim for item, value in zip(items, values) for dim in _assignment(model, item, value)]
            for bv, enabled in itertools.product((False, True), (False, True) if gated else (True,)):
                assumptions = fixed + [model._lit_to_dimacs(boolean if bv else ~boolean)]
                if gated:
                    assumptions.append(model._lit_to_dimacs(gate if enabled else ~gate))
                expected = not enabled or _holds(predicate(values), not bv if negated else bv, mode)
                assert solver.solve(assumptions=assumptions) == expected, (
                    mode, values, bv, negated, enabled,
                )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("backend", ["auto", "pairwise", "bipartite"])
@pytest.mark.parametrize("negated,gated", [(False, False), (True, False), (False, True)])
def test_integer_all_different_truth_table(mode, backend, negated, gated):
    model = Model()
    xs = model.int_vector("x", 3, -1, 1)
    _check(model, xs, [range(-1, 2)] * 3, xs.all_different(backend),
           lambda values: len(set(values)) == len(values), mode, negated=negated, gated=gated)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("kind", ["empty", "singleton", "disjoint", "overlap", "fixed", "alias", "views"])
def test_integer_all_different_domains_and_aliases(mode, kind):
    model = Model()
    x = model.int("x", -1, 1)
    if kind == "empty":
        xs, domains = [], []
    elif kind == "singleton":
        xs, domains = [x], [range(-1, 2)]
    elif kind in ("disjoint", "overlap"):
        lo = 2 if kind == "disjoint" else 0
        y = model.int("y", lo, 3)
        xs, domains = [x, y], [range(-1, 2), range(lo, 4)]
    elif kind == "fixed":
        xs, domains = [x, model.as_int(0), model.as_int(0)], [range(-1, 2), [0], [0]]
    elif kind == "alias":
        xs, domains = [x, x], [range(-1, 2)] * 2
    else:
        b = model.bool("view")
        xs, domains = [model.as_int(b), model.as_int(~b), x], [range(2), range(2), range(-1, 2)]
    # Alias assignments that disagree are inconsistent independently of the global.
    if kind in ("alias", "views"):
        actual_items = [x] if kind == "alias" else [b, x]
        actual_domains = [range(-1, 2)] if kind == "alias" else [range(2), range(-1, 2)]
        predicate = (lambda values: False) if kind == "alias" else (
            lambda values: len({int(values[0]), int(not values[0]), values[1]}) == 3
        )
    else:
        actual_items, actual_domains = xs, domains
        predicate = lambda values: len(set(values)) == len(values)
    vector = model.int_vector("empty", 0, 0, 0) if not xs else model.vector(xs)
    _check(model, actual_items, actual_domains, vector.all_different(), predicate, mode)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("backend", ["auto", "pairwise", "bipartite"])
@pytest.mark.parametrize("nullable", [False, True])
def test_enum_all_different_truth_table(mode, backend, nullable):
    model = Model()
    xs = model.enum_vector("x", 3, ["red", "green", "blue"], nullable=nullable)
    domain = ["red", "green", "blue"] + ([None] if nullable else [])
    _check(model, xs, [domain] * 3, xs.all_different(backend),
           lambda values: len(set(values)) == len(values), mode)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("width", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("rows_kind", ["empty", "single", "multiple", "all"])
def test_table_truth_table_for_every_encoding(mode, width, rows_kind):
    model = Model()
    xs = model.int_vector("x", width, 0, 1)
    rows = list(itertools.product(range(2), repeat=width))
    if rows_kind == "empty":
        rows = []
    elif rows_kind == "single":
        rows = rows[:1]
    elif rows_kind == "multiple":
        rows = rows[::2]
    allowed = set(rows)
    _check(model, xs, [range(2)] * width, model.table(xs, allowed=iter(rows)),
           lambda values: values in allowed, mode)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("negated,gated", [(False, False), (True, False), (False, True)])
def test_table_mixed_columns_pruning_and_nullable_enums(mode, negated, gated):
    model = Model()
    enabled = model.bool("enabled")
    integer = model.int("integer", -1, 2)
    color = model.enum("color", ["red", "blue"], nullable=True)
    rows = [(True, 0, "red"), (False, 2, None)]
    constraint = model.table([~enabled, integer, color], allowed=rows + [rows[0], (False, 9, "blue")])
    _check(model, [enabled, integer, color], [[False, True], range(-1, 3), ["red", "blue", None]],
           constraint, lambda values: (not values[0], values[1], values[2]) in rows,
           mode, negated=negated, gated=gated)


@pytest.mark.parametrize("mode", MODES)
def test_table_repeated_columns_and_boolean_views(mode):
    model = Model()
    b = model.bool("view")
    x = model.int("x", 0, 2)
    rows = [(0, 1, 1, 1), (1, 0, 2, 2), (0, 0, 0, 0), (1, 0, 0, 2)]
    constraint = model.table([model.as_int(b), model.as_int(~b), x, x], allowed=rows)
    _check(model, [b, x], [[False, True], range(3)], constraint,
           lambda values: (int(values[0]), int(not values[0]), values[1], values[1]) in rows, mode)


@pytest.mark.parametrize("kind", ["alldifferent", "table"])
def test_global_can_share_its_indicator_with_an_argument(kind):
    for bv, xv in itertools.product((False, True), range(3)):
        model = Model()
        b = model.bool("b")
        x = model.int("x", 0, 2)
        g = (model.vector([model.as_int(b), x]).all_different() if kind == "alldifferent"
             else model.table([b, x], allowed=[(True, 0), (False, 2)]))
        model &= g.iff(b)
        model &= b if bv else ~b
        model &= x == xv
        truth = int(bv) != xv if kind == "alldifferent" else (bv, xv) in [(True, 0), (False, 2)]
        assert model.solve().ok == (bv == truth)


@pytest.mark.parametrize("kind", ["alldifferent", "table"])
def test_construction_and_unused_reification_are_lazy(kind):
    model = Model()
    xs = model.int_vector("x", 3, 0, 3)
    b = model.bool("b")
    before = model._top_id(), tuple(model._hard), dict(model._pending_literal_defs)
    g = (xs.all_different("bipartite") if kind == "alldifferent"
         else model.table(xs, allowed=[(1, 2, 3), (0, 1, 2)]))
    for mode in MODES:
        _connect(g, b, mode)
    assert (model._top_id(), tuple(model._hard), dict(model._pending_literal_defs)) == before


@pytest.mark.parametrize("kind", ["alldifferent", "table"])
def test_repeated_reification_reuses_encoding_variables(kind):
    model = Model()
    xs = model.int_vector("x", 3, 0, 3)
    b, c = model.bool("b"), model.bool("c")
    g = (xs.all_different() if kind == "alldifferent"
         else model.table(xs, allowed=[(1, 2, 3), (0, 1, 2)]))
    model &= g.iff(b)
    top = model._top_id()
    model &= g.iff(c)
    assert model._top_id() == top
    model &= b
    model &= ~c
    assert model.solve().status == "unsat"


@pytest.mark.parametrize("kind", ["alldifferent", "table", "int_relation"])
@pytest.mark.parametrize("method", ["iff", "implies"])
def test_reification_validates_indicators_without_allocating(kind, method):
    model = Model()
    xs = model.int_vector("x", 2, 0, 2)
    g = {"alldifferent": lambda: xs.all_different(),
         "table": lambda: model.table(xs, allowed=[(1, 2)]),
         "int_relation": lambda: xs[0] <= xs[1]}[kind]()
    before = model._top_id(), len(model._hard)
    for invalid in (True, 1, None, xs[0], ClauseGroup(model, [])):
        with pytest.raises(TypeError):
            getattr(g, method)(invalid)
    with pytest.raises(ValueError):
        getattr(g, method)(Model().bool("foreign"))
    assert (model._top_id(), len(model._hard)) == before


@pytest.mark.parametrize("mode", ["iff", "implies"])
def test_integer_relations_share_the_logical_api(mode):
    model = Model()
    xs = model.int_vector("x", 2, -1, 1)
    _check(model, xs, [range(-1, 2)] * 2, xs[0] <= xs[1], lambda values: values[0] <= values[1], mode)


def test_conditioned_and_combined_groups_do_not_keep_original_global_semantics():
    model = Model()
    xs = model.int_vector("x", 2, 0, 2)
    b = model.bool("b")
    g = xs.all_different()
    for group in (g.only_if(b), g & b):
        with pytest.raises(TypeError):
            group.implies(b)
        with pytest.raises(TypeError):
            _ = b == group


def test_mutating_a_global_keeps_added_constraints_and_invalidates_reification():
    model = Model()
    a, b, indicator = model.bool("a"), model.bool("b"), model.bool("indicator")
    g = model.table([a, b], allowed=[(True, False), (False, True)])
    g.extend(Clause(model, [a]), inplace=True)
    with pytest.raises(TypeError):
        model &= g.iff(indicator)
    model &= g
    model &= ~a
    assert model.solve().status == "unsat"


@pytest.mark.parametrize("mode", ["iff", "implies"])
def test_in_place_extension_cannot_silently_change_a_pending_reification(mode):
    model = Model()
    a, b, indicator = model.bool("a"), model.bool("b"), model.bool("indicator")
    g = model.table([a, b], allowed=[(True, False), (False, True)])
    connected = getattr(g, mode)(indicator)
    g.extend(Clause(model, [a]), inplace=True)
    with pytest.raises(TypeError):
        model &= connected


def test_table_reverse_direction_adds_no_row_selectors():
    model = Model()
    xs = model.int_vector("x", 3, 0, 1)
    b = model.bool("b")
    g = model.table(xs, allowed=[(0, 1, 0), (1, 0, 1)])
    top = model._top_id()
    model &= g.implies(b)
    assert model._top_id() == top
    assert len(model.to_cnf().clauses) == 2


def test_all_different_reverse_direction_uses_one_witness_per_overlapping_pair():
    model = Model()
    xs = model.int_vector("x", 4, 0, 3)
    b = model.bool("b")
    top = model._top_id()
    model &= xs.all_different().implies(b)
    assert model._top_id() - top == 6


@pytest.mark.parametrize("seed", range(8))
def test_random_tables_match_python_membership(seed):
    rng = random.Random(seed)
    width = rng.randint(1, 4)
    domain = range(-1, 2)
    rows = [tuple(rng.choice(domain) for _ in range(width)) for _ in range(rng.randint(0, 12))]
    model = Model()
    xs = model.int_vector("x", width, -1, 1)
    _check(model, xs, [domain] * width, xs.is_in(rows), lambda values: values in rows,
           "iff", negated=bool(seed % 2), gated=bool(seed % 3 == 0))


@pytest.mark.parametrize("seed", range(12))
def test_random_all_different_heterogeneous_domains(seed):
    rng = random.Random(seed)
    model = Model()
    items, domains = [], []
    for i in range(rng.randint(1, 4)):
        lo = rng.randint(-2, 2)
        hi = lo + rng.randint(0, 2)
        items.append(model.int(f"x{i}", lo, hi))
        domains.append(range(lo, hi + 1))
    indices = [rng.randrange(len(items)) for _ in range(rng.randint(1, 5))]
    constraint = model.vector([items[i] for i in indices]).all_different()
    _check(model, items, domains, constraint,
           lambda values: len({values[i] for i in indices}) == len(indices),
           "iff", negated=bool(seed % 2), gated=bool(seed % 3 == 0))


@pytest.mark.parametrize("kind", ["alldifferent", "table"])
def test_positive_posting_does_not_build_the_negative_encoding(kind):
    model = Model()
    xs = model.int_vector("x", 3, 0, 1)
    b = model.bool("b")
    g = (xs.all_different() if kind == "alldifferent"
         else model.table(xs, allowed=[(0, 1, 0), (1, 0, 1)]))
    top = model._top_id()
    model &= g.only_if(b)
    # Pairwise AllDifferent needs no helpers; a ternary table needs only its two selectors.
    assert model._top_id() - top == (0 if kind == "alldifferent" else 2)


def test_gated_all_different_does_not_register_unconditional_amos():
    model = Model()
    xs = model.int_vector("x", 3, 0, 2)
    b = model.bool("b")
    before = set(model._known_amo_groups)
    model &= xs.all_different("bipartite").iff(b)
    assert set(model._known_amo_groups) == before
    model &= ~b
    for x in xs:
        model &= x == 1
    # Exercise PB compilation after the gated global has been posted.
    model &= sum(x == 1 for x in xs) >= 2
    assert model.solve().ok


def test_positive_bipartite_all_different_preserves_amo_metadata():
    model = Model()
    xs = model.int_vector("x", 3, 0, 2)
    before = set(model._known_amo_groups)
    model &= xs.all_different("bipartite")
    assert len(set(model._known_amo_groups) - before) == 3


@pytest.mark.parametrize("backend", ["auto", "pairwise", "bipartite"])
@pytest.mark.parametrize("length", [0, 1])
def test_degenerate_enum_all_different_is_true(backend, length):
    model = Model()
    xs = model.enum_vector("x", length, ["a", "b"], nullable=True)
    _check(model, xs, [["a", "b", None]] * length, xs.all_different(backend),
           lambda values: True, "iff")


def test_integer_relation_reify_remains_a_compatible_alias():
    model = Model()
    x, y = model.int("x", 0, 2), model.int("y", 0, 2)
    b = model.bool("b")
    model &= (x <= y).reify(b)
    model &= ~b
    model &= x == 0
    model &= y == 2
    assert model.solve().status == "unsat"


@pytest.mark.parametrize("kind", ["alldifferent", "table"])
def test_reification_can_be_added_after_an_incremental_sat_solve(kind):
    model = Model()
    xs = model.int_vector("x", 3, 0, 2)
    b = model.bool("b")
    # Domain definitions and existing clauses are already in the live solver.
    model &= xs[0] == 0
    assert model.solve().ok
    g = (xs.all_different() if kind == "alldifferent"
         else xs.is_in([(0, 1, 2), (1, 0, 2)]))
    model &= g.iff(b)
    model &= ~b
    model &= xs[1] == 1
    model &= xs[2] == 2
    assert model.solve().status == "unsat"
