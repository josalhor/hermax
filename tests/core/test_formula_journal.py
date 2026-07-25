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
