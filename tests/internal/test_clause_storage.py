import itertools
import random
import sys

import pytest

from hermax.model import Clause, ClauseGroup, Model
from hermax.internal._clause_storage import ClauseStorage, to_cnf, to_wcnf


def test_storage_preserves_empty_clauses_order_and_plain_python_results():
    rows = [(), (1,), (-2, 3), (3, 3, -3)]
    storage = ClauseStorage(rows)
    assert list(storage) == rows
    assert storage[-1] == rows[-1]
    assert storage[1:3] == rows[1:3]
    assert storage[::-1] == rows[::-1]
    assert all(type(row) is tuple and all(type(lit) is int for lit in row) for row in storage)
    assert storage.to_lists() == [list(row) for row in rows]
    assert storage.max_var == 3
    assert ClauseStorage().max_var == 0
    with pytest.raises(IndexError):
        _ = storage[len(rows)]


def test_storage_copy_concatenation_iteration_and_self_extension_are_snapshots():
    storage = ClauseStorage([(1000, -1001), ()])
    copied = ClauseStorage(storage)
    iterator = iter(storage)
    saved_row = storage[0]
    joined = storage + ClauseStorage([(7,)])
    storage.extend(storage)
    assert list(iterator) == [(1000, -1001), ()]
    assert list(storage) == [(1000, -1001), ()] * 2
    assert list(copied) == [(1000, -1001), ()]
    assert list(joined) == [(1000, -1001), (), (7,)]
    copied.append((-9,))
    assert list(storage) == [(1000, -1001), ()] * 2
    assert saved_row == (1000, -1001)


@pytest.mark.parametrize("bad", [0, True, 1.5, "2", None])
def test_bad_clause_append_is_atomic(bad):
    storage = ClauseStorage([(1,)])
    with pytest.raises((TypeError, ValueError)):
        storage.append((2, bad))
    assert list(storage) == [(1,)]
    storage.append((3,))
    assert list(storage) == [(1,), (3,)]


def test_iterator_failure_retains_only_complete_preceding_clauses():
    storage = ClauseStorage([(1,)])

    def rows():
        yield (2,)
        raise ValueError("input failed")

    with pytest.raises(ValueError, match="input failed"):
        storage.extend(rows())
    assert list(storage) == [(1,), (2,)]


@pytest.mark.parametrize("wide", [2**31, -(2**31), 2**100, -(2**100)])
def test_large_ids_survive_copy_gating_export_and_rollback(wide):
    storage = ClauseStorage([(1,), (wide, -2), (), (-wide,)])
    copy = ClauseStorage(storage)
    exported = to_cnf(storage)
    assert exported.nv == abs(wide)
    assert exported.clauses == [[1], [wide, -2], [], [-wide]]
    gated = storage.with_literal(-wide)
    assert list(gated) == [(1, -wide), (wide, -2, -wide), (-wide,), (-wide, -wide)]
    del storage[1:]
    assert list(storage) == [(1,)]
    assert storage.max_var == 1
    assert list(copy) == [(1,), (wide, -2), (), (-wide,)]
    storage.extend(copy)
    assert list(storage) == [(1,), (1,), (wide, -2), (), (-wide,)]


def test_export_reuses_repeated_integer_objects_and_handles_sparse_ids():
    storage = ClauseStorage([(1000, -1000)] * 3000)
    rows = storage.to_lists()
    assert rows == [[1000, -1000]] * 3000
    assert rows[0][0] is rows[-1][0]
    assert rows[0][1] is rows[-1][1]
    rows[0].append(7)
    assert storage[0] == (1000, -1000)
    sparse = ClauseStorage([(2**31 - 1,), (-2**31 + 1,)])
    assert sparse.to_lists() == [[2**31 - 1], [-2**31 + 1]]


def test_tail_rollback_does_not_change_saved_rows_or_copies():
    storage = ClauseStorage([(1,), (2,), (3,)])
    copy = ClauseStorage(storage)
    tail = storage[1:]
    del storage[1:]
    storage.append((-4,))
    assert list(storage) == [(1,), (-4,)]
    assert list(copy) == [(1,), (2,), (3,)]
    assert tail == [(2,), (3,)]
    del storage[:]
    assert len(storage) == 0 and storage.max_var == 0


def test_cnf_and_wcnf_export_keep_public_types_and_do_not_alias_storage():
    storage = ClauseStorage([(1, -2), ()])
    cnf, wcnf = to_cnf(storage), to_wcnf(storage)
    assert cnf.clauses == wcnf.hard == [[1, -2], []]
    assert cnf.nv == wcnf.nv == 2
    assert type(cnf.clauses) is list and all(type(row) is list for row in cnf.clauses)
    wcnf.append([3], weight=2**100)
    assert wcnf.wght == [2**100] and wcnf.topw == 2**100 + 1
    cnf.clauses[0].append(9)
    wcnf.hard.clear()
    assert list(storage) == [(1, -2), ()]


def test_model_owns_posted_clauses_independently_of_later_group_mutation():
    m = Model()
    a, b = m.bool("a"), m.bool("b")
    group = ClauseGroup(m, [Clause(m, [a])])
    m &= group
    iterator = group.iter_dimacs()
    group.extend(~a, inplace=True)
    assert list(iterator) == [(a.id,)]
    assert m.to_cnf().clauses == [[a.id]]
    assert m.solve().ok
    extended = group & b
    assert tuple(group) == ((a.id,), (-a.id,))
    assert tuple(extended) == ((a.id,), (-a.id,), (b.id,))
    m &= extended
    assert not m.solve().ok


def test_group_public_exports_preserve_arbitrary_precision_literal_ids():
    m = Model()
    huge = 2**100
    group = ClauseGroup(m, [[huge, -huge]])
    m &= group
    assert tuple(group) == ((huge, -huge),)
    assert group.single_clause_or_none() == (huge, -huge)
    assert group.materialize_semantic()[0].dimacs == (huge, -huge)
    assert m.to_cnf().clauses == [[huge, -huge]]
    assert m.to_cnf().nv == huge


def test_extending_storage_realizes_deferred_group_before_reading_its_clauses():
    m = Model()
    a, gate = m.bool("a"), m.bool("gate")
    condition = (a == 2).only_if(gate)
    storage = ClauseStorage()
    storage.extend(condition)
    assert list(storage) == [(-gate.id,)]
    assert list(ClauseStorage(condition)) == [(-gate.id,)]


def test_extending_from_a_partial_iterator_consumes_only_remaining_clauses():
    source = ClauseStorage([(1,), (), (2**100,)])
    iterator = source.iter_from(1)
    target = ClauseStorage([(3,)])
    target.extend(iterator)
    assert list(target) == [(3,), (), (2**100,)]
    assert list(iterator) == []


def test_randomized_storage_operations_match_python_lists():
    rng = random.Random(731)
    storage, expected, snapshots = ClauseStorage(), [], []
    values = [-2**100, -2**31, -9, -1, 1, 8, 2**31 - 1, 2**100]
    for _ in range(400):
        operation = rng.choice(["append", "extend", "delete", "snapshot", "gate"])
        if operation == "append":
            row = tuple(rng.choices(values, k=rng.randrange(6)))
            storage.append(row)
            expected.append(row)
        elif operation == "extend":
            rows = [tuple(rng.choices(values, k=rng.randrange(4))) for _ in range(rng.randrange(5))]
            storage.extend(ClauseStorage(rows))
            expected.extend(rows)
        elif operation == "delete":
            selection = slice(rng.randrange(-20, 20), rng.randrange(-20, 20), rng.choice([-3, -1, 1, 2]))
            del storage[selection]
            del expected[selection]
        elif operation == "snapshot":
            snapshots.append((ClauseStorage(storage), iter(storage), list(expected)))
        else:
            gate = rng.choice(values)
            storage = storage.with_literal(gate)
            expected = [(*row, gate) for row in expected]
        if len(expected) > 50:
            del storage[20:]
            del expected[20:]
        assert list(storage) == expected
        assert storage.to_lists() == [list(row) for row in expected]
        assert storage.max_var == max((abs(v) for row in expected for v in row), default=0)
    for copy, iterator, expected in snapshots:
        assert list(copy) == list(iterator) == expected


def test_wide_id_references_are_released_after_copies_and_exports():
    wide = int("9" * 100)
    before = sys.getrefcount(wide)
    storage = ClauseStorage([(wide,)])
    copy = ClauseStorage(storage)
    storage.append((wide,))
    gated = copy.with_literal(wide)
    exported = to_cnf(gated)
    del storage, copy, gated, exported
    assert sys.getrefcount(wide) == before


def test_extend_generator_can_modify_storage_without_changing_saved_copies():
    storage = ClauseStorage([(1,)])
    copies = []

    def rows():
        copies.append(ClauseStorage(storage))
        storage.append((2,))
        yield (3,)

    storage.extend(rows())
    assert list(storage) == [(1,), (2,), (3,)]
    assert list(copies[0]) == [(1,)]


def test_integer_conversion_can_modify_storage_without_invalidating_the_append():
    storage = ClauseStorage([(1,)])
    copies = []

    class Integer:
        def __index__(self):
            copies.append(ClauseStorage(storage))
            storage.append((2,))
            return 3

    storage.append((Integer(),))
    assert list(storage) == [(1,), (2,), (3,)]
    assert list(copies[0]) == [(1,)]


@pytest.mark.parametrize("gate", [4, -4, 2**100, -(2**100)])
def test_native_gating_preserves_exact_truth_tables(gate):
    rows = [(1, -2), (3,), ()]
    gated = ClauseStorage(rows).with_literal(gate)
    assert list(gated) == [(*row, gate) for row in rows]
    for values in itertools.product([False, True], repeat=4):
        assignment = dict(zip([1, 2, 3, abs(gate)], values))
        def value(lit):
            return assignment[abs(lit)] == (lit > 0)
        assert all(any(value(lit) for lit in row) for row in gated) == (
            value(gate) or all(any(value(lit) for lit in row) for row in rows)
        )
