"""Integer thresholds must retain their semantics when materialized lazily."""

import pytest
from itertools import product

from pysat.solvers import Solver

from hermax.model import Clause, ClauseGroup, Model
from hermax.model.expressions import Literal


def test_declaration_and_decode_do_not_materialize_threshold_literals(monkeypatch):
    calls = []
    original = Literal.__init__

    def record(self, *args, **kwargs):
        calls.append(args[1])
        original(self, *args, **kwargs)

    monkeypatch.setattr(Literal, "__init__", record)
    model = Model()
    value = model.int("value", -2, 98)
    assert calls == []
    assert model.decode_model([1, -2, 3, -100]).val(value) == 0
    assert calls == []

    threshold = value >= 3
    assert threshold.id == 5
    assert calls == [5, 5]
    assert (value >= 3) is threshold
    assert model._dimacs_to_lit(5) is threshold
    assert model._dimacs_to_lit(-5) is ~threshold
    assert ~~threshold is threshold
    assert calls == [5, 5]


def test_threshold_names_are_private_to_the_integer():
    model = Model()
    before = model.bool("before")
    value = model.int("value", -1, 2)
    after = model.bool("after")
    assert (before.id, after.id) == (1, 5)
    user_literal = model.bool("value<=#1")
    other = model.int("value<=#2", 0, 0)
    assert user_literal.id != value._threshold_lits[1].id
    assert other.name == "value<=#2"
    assert model._registry["value<=#1"] is user_literal


def test_preexisting_user_name_does_not_collide_with_threshold():
    model = Model()
    user_literal = model.bool("value<=#1")
    value = model.int("value", 0, 3)
    assert user_literal.id != value._threshold_lits[1].id
    assert model._registry["value<=#1"] is user_literal
    assert model.bool("after").id == 5


def test_lazy_thresholds_preserve_export_solve_and_integer_views():
    model = Model()
    value = model.int("value", -2, 3)
    flag = model.bool("flag")
    view = model.as_int(~flag)
    model &= (value >= 1)
    model &= (value <= 2)
    model &= flag
    model &= (value + view <= 2)
    cnf = model.to_cnf()
    assert all(clause in cnf.clauses for clause in [[-2, 1], [-3, 2], [-4, 3], [-5, 4]])
    result = model.solve()
    assert result.ok
    assert result[flag] is True
    assert result[view] == 0
    assert 1 <= result[value] <= 2


def test_sparse_external_id_does_not_overlap_threshold_ids():
    model = Model()
    model._reserve_literal_ids_up_to(1000)
    value = model.int("value", 0, 2)
    assert (value >= 1).id == 1001
    assert model._dimacs_to_lit(1002) is (value >= 2)
    assert model.bool("next").id == 1003


def test_every_threshold_assignment_and_decoded_value():
    model = Model()
    value = model.int("value", -2, 2)
    formula = model.to_cnf()
    with Solver(bootstrap_with=formula.clauses) as solver:
        for bits in product((False, True), repeat=4):
            assumptions = [i if bit else -i for i, bit in enumerate(bits, 1)]
            valid = list(bits) == sorted(bits, reverse=True)
            assert solver.solve(assumptions=assumptions) == valid
            # Decoding retains its existing interpretation even for an
            # arbitrary, non-satisfying raw assignment.
            assert model.decode_model(assumptions).val(value) == -2 + sum(bits)


def test_multiple_models_and_registry_iteration_remain_independent():
    first, second = Model(), Model()
    first.bool("before")
    x = first.int("x", 0, 3)
    first.bool("after")
    y = second.int("x", 0, 3)
    assert list(first._registry) == ["before", "after"]
    assert list(first._lits_by_id) == [1, 5]
    assert (x >= 2) is first._dimacs_to_lit(3)
    assert (y >= 2) is second._dimacs_to_lit(2)
    assert (x >= 2) is not (y >= 2)


def test_container_name_does_not_collide_with_threshold():
    model = Model()
    model.int("x<=#2", 0, 0)
    value = model.int("x", 0, 4)
    assert (value >= 3).name == "x<=#2"
    assert model.bool("next").id == 5


def test_decode_is_scoped_to_each_integer_and_does_not_create_literals(monkeypatch):
    model = Model()
    x = model.int("x", -2, 1)
    y = model.int("y", 3, 5)
    other = model.bool("other")
    assert other.id == 6
    created = []
    original = Literal.__init__

    def record(self, *args, **kwargs):
        created.append(args[1])
        original(self, *args, **kwargs)

    monkeypatch.setattr(Literal, "__init__", record)
    assignment = model.decode_model([1, 2, -3, 4, -5, 6])
    assert assignment.val(x) == 0
    assert assignment.val(y) == 4
    assert created == []


def test_threshold_names_do_not_change_when_integer_name_is_modified():
    model = Model()
    value = model.int("original", 0, 2)
    value.name = "renamed"
    assert list(model._registry) == []
    assert (value >= 1).name == "original<=#0"
    assert model._dimacs_to_lit(1) is (value >= 1)


def test_reserved_ids_are_owned_by_the_integer():
    model = Model()
    value = model.int("value", 0, 3)
    with pytest.raises(ValueError, match="already allocated"):
        model._new_literal_pair("other", var_id=2)
    assert model._dimacs_to_lit(2) is value._threshold_lits[1]
    assert model.bool("next").id == 4


def test_id_lookup_across_separate_ranges_and_ordinary_literals():
    model = Model()
    before = model.bool("before")
    x = model.int("x", 0, 2)
    middle = model.bool("middle")
    model._reserve_literal_ids_up_to(20)
    y = model.int("y", 0, 2)
    after = model.bool("after")
    assert [before.id, middle.id, after.id] == [1, 4, 23]
    for lit_id, literal in ((1, before), (2, x._threshold_lits[0]),
                            (3, x._threshold_lits[1]), (4, middle),
                            (21, y._threshold_lits[0]),
                            (22, y._threshold_lits[1]), (23, after)):
        assert model._dimacs_to_lit(lit_id) is literal
        assert model._dimacs_to_lit(-lit_id) is ~literal
    assert model._dimacs_to_lit(10).id == 10
    assert model.bool("next").id == 24


def test_deferred_definition_for_threshold_is_resolved_by_reserved_id():
    model = Model()
    value = model.int("value", 0, 2)
    threshold = value >= 1
    flag = model.bool("flag")
    model._register_literal_definition(threshold, ClauseGroup(model, [Clause(model, [flag])]))
    model._ensure_deferred_defs_in_group(ClauseGroup._from_dimacs_trusted(model, [(threshold.id,)]))
    assert threshold.id in model._realized_literal_defs
    assert any(model._clause_to_dimacs_list(clause) == [flag.id] for clause in model._hard)


def test_decode_preserves_changes_to_exposed_literal_attributes():
    model = Model()
    value = model.int("value", 0, 2)
    first = value >= 1
    second = value >= 2
    first.id = 50
    second.polarity = False
    assert model.decode_model([50]).val(value) == 2


def test_integer_declared_after_incremental_backend_reserves_auxiliary_ids():
    model = Model()
    a, b = model.bool("a"), model.bool("b")
    model.obj.add(a, weight=1)
    assert model.solve(incremental=True, backend="maxsat").ok
    model.obj.add_soft(a | b, weight=5)
    backend_top = model._inc_state.ip_next_vid
    value = model.int("value", 0, 2)
    assert (value >= 1).id > backend_top
    model &= value == 1
    result = model.solve(incremental=True, backend="maxsat")
    assert result.ok
    assert result[value] == 1
