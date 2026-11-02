import pytest

from hermax.core.formula_journal import FormulaJournal


def test_journal_tracks_vars_hard_clauses_and_soft_units():
    journal = FormulaJournal()

    assert journal.new_var() == 1
    journal.add_hard([1, -2])
    journal.set_soft(-2, 5)
    journal.set_soft(-2, 7)
    journal.set_soft(1, 3)
    journal.set_soft(1, 0)

    assert journal.num_vars == 2
    assert journal.snapshot() == {
        "num_vars": 2,
        "hard_clauses": [[1, -2]],
        "soft_units": [(-2, 7)],
        "soft_nonunit": [],
    }


def test_journal_tracks_stored_nonunit_soft_clauses():
    journal = FormulaJournal()
    journal.add_soft_nonunit([-1, 2], 4)

    assert journal.snapshot() == {
        "num_vars": 2,
        "hard_clauses": [],
        "soft_units": [],
        "soft_nonunit": [([-1, 2], 4)],
    }


def test_snapshot_with_assumptions_does_not_change_journal():
    journal = FormulaJournal()
    journal.add_hard([1])
    journal.ensure_var(2)

    snapshot = journal.snapshot(assumptions_as_hard_units=[-2])

    assert snapshot["hard_clauses"] == [[1], [-2]]
    assert journal.snapshot()["hard_clauses"] == [[1]]
    assert journal.num_vars == 2


def test_journal_replays_its_canonical_state_in_order():
    journal = FormulaJournal()
    journal.ensure_var(2)
    journal.add_hard([1, -2])
    journal.set_soft(-2, 3)
    journal.add_soft_nonunit([1, 2], 4)
    replayed = []

    journal.replay(
        new_var=lambda var: replayed.append(("var", var)),
        add_hard=lambda clause: replayed.append(("hard", clause)),
        set_soft=lambda lit, weight: replayed.append(("soft", lit, weight)),
        add_soft_nonunit=lambda clause, weight: replayed.append(("nonunit", clause, weight)),
    )

    assert replayed == [
        ("var", 1),
        ("var", 2),
        ("hard", [1, -2]),
        ("soft", -2, 3),
        ("nonunit", [1, 2], 4),
    ]


@pytest.mark.parametrize("operation", ["hard", "soft", "nonunit"])
def test_formula_journal_rejects_zero_literals(operation):
    journal = FormulaJournal()

    with pytest.raises((TypeError, ValueError), match="literal|zero"):
        if operation == "hard":
            journal.add_hard([0])
        elif operation == "soft":
            journal.set_soft(0, 1)
        else:
            journal.add_soft_nonunit([0, 1], 1)


@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_formula_journal_rejects_non_integer_hard_literals(raw_literal):
    journal = FormulaJournal()

    with pytest.raises((TypeError, ValueError)):
        journal.add_hard([raw_literal])


def test_journal_exports_an_independent_native_formula_with_overwrite_semantics():
    from hermax.formula import WCNF
    journal = FormulaJournal()
    journal.ensure_var(8)
    journal.add_hard([1, -2])
    journal.set_soft(-1, 3)
    journal.set_soft(-1, 7)
    journal.add_soft_nonunit([1, 2], 5)
    formula = journal.to_formula(assumptions=[-3])
    assert isinstance(formula, WCNF)
    assert formula.nv == 8
    assert formula.hard == [[1, -2], [-3]]
    assert list(zip(formula.soft, formula.wght)) == [((-1,), 7), ((1, 2), 5)]
    formula.append([6])
    formula.wght[0] = 9
    assert journal.snapshot()['hard_clauses'] == [[1, -2]]
    assert journal.soft_units == {-1: 7}


def test_journal_snapshot_roundtrip_preserves_native_storage_and_ownership():
    from hermax.internal._clause_storage import ClauseStorage
    source = FormulaJournal()
    source.add_hard([1, -2])
    source.add_soft_nonunit([2, 3], 5)
    snapshot = source.snapshot()
    copied = FormulaJournal.from_snapshot(snapshot)
    assert isinstance(copied.hard_clauses, ClauseStorage)
    snapshot['hard_clauses'][0][0] = -1
    snapshot['soft_nonunit'][0][0][0] = -2
    assert copied.snapshot() == source.snapshot()


@pytest.mark.parametrize('field,value', [
    ('num_vars', 1.5),
    ('hard_clauses', [[True]]),
    ('soft_units', [(1, 2.5)]),
    ('soft_nonunit', [([1, 2], -3)]),
])
def test_journal_snapshot_rejects_malformed_data(field, value):
    snapshot = FormulaJournal().snapshot()
    snapshot[field] = value
    with pytest.raises((TypeError, ValueError)):
        FormulaJournal.from_snapshot(snapshot)
