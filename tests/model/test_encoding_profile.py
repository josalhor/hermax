from __future__ import annotations

import random

import pytest

from hermax.model import Model


def test_enable_profiling_toggles_profile_object():
    m = Model()
    assert m.get_encoding_profile() is None

    m.enable_profiling(True)
    assert m.get_encoding_profile() is not None

    m.enable_profiling(False)
    assert m.get_encoding_profile() is None


def test_profile_records_basic_hard_clause_event():
    m = Model()
    m.enable_profiling()
    a = m.bool("a")

    m &= a

    profile = m.get_encoding_profile()
    assert profile is not None
    assert len(profile.events) == 1
    event = profile.events[0]
    assert event.kind == "add_hard"
    assert event.hard_clause_delta == 1
    assert event.pending_pb_delta == 0
    assert event.success is True


def test_profile_records_failed_manual_scope():
    m = Model()
    m.enable_profiling()

    with pytest.raises(RuntimeError, match="boom"):
        with m.profile_scope("manual", label="explode"):
            raise RuntimeError("boom")

    profile = m.get_encoding_profile()
    assert profile is not None
    assert len(profile.events) == 1
    event = profile.events[0]
    assert event.kind == "manual"
    assert event.label == "explode"
    assert event.success is False


def test_deferred_pb_commit_keeps_origin_metadata():
    m = Model()
    m.enable_profiling()
    a = m.bool("a")
    b = m.bool("b")

    m &= (a + b <= 1)

    profile = m.get_encoding_profile()
    assert profile is not None
    add_event = next(ev for ev in profile.events if ev.kind == "add_hard_pb")
    assert add_event.pending_pb_delta == 1

    m._commit_pb()

    commit_events = [ev for ev in profile.events if ev.kind == "commit_pb_constraint"]
    assert len(commit_events) == 1
    commit_event = commit_events[0]
    assert commit_event.metadata["origin_event_id"] == add_event.event_id
    assert commit_event.metadata["origin_kind"] == "add_hard_pb"
    assert commit_event.hard_clause_delta > 0


def test_profile_summaries_aggregate_by_kind_and_label():
    m = Model()
    m.enable_profiling()
    a = m.bool("a")
    b = m.bool("b")

    with m.profile_scope("outer", label="batch"):
        m &= a
        m &= (a + b <= 1)
    m._commit_pb()

    profile = m.get_encoding_profile()
    assert profile is not None

    by_kind = profile.summary_by_kind()
    assert by_kind["outer"]["count"] == 1
    assert by_kind["add_hard"]["count"] == 1
    assert by_kind["add_hard_pb"]["count"] == 1
    assert by_kind["commit_pb"]["count"] == 1
    assert by_kind["commit_pb_constraint"]["count"] == 1

    by_label = profile.summary_by_label()
    assert by_label["batch"]["count"] == 1
    assert by_label["<none>"]["count"] >= 4


def test_profile_summary_tracks_multiple_scopes_and_clause_deltas():
    rng = random.Random(4)
    m = Model()
    m.enable_profiling()
    xs = m.bool_vector("x", length=4)

    expected_hard = 0
    for i in range(6):
        with m.profile_scope("batch", label=f"group-{i % 2}"):
            chosen = [x for x in xs if rng.randrange(2)]
            if not chosen:
                chosen = [xs[i % len(xs)]]
            for lit in chosen:
                m &= lit
                expected_hard += 1

    profile = m.get_encoding_profile()
    assert profile is not None

    by_kind = profile.summary_by_kind()
    by_label = profile.summary_by_label()

    assert by_kind["batch"]["count"] == 6
    assert by_kind["add_hard"]["count"] == expected_hard
    assert by_kind["add_hard"]["hard_clause_delta"] == expected_hard
    assert by_label["group-0"]["count"] == 3
    assert by_label["group-1"]["count"] == 3


def test_profile_summary_counts_success_and_failure_by_kind_and_label():
    m = Model()
    m.enable_profiling()

    for i in range(3):
        with m.profile_scope("batch", label="ok-group"):
            m &= m.bool(f"a_{i}")

    for i in range(2):
        with pytest.raises(ValueError, match="boom"):
            with m.profile_scope("batch", label="bad-group"):
                raise ValueError(f"boom-{i}")

    profile = m.get_encoding_profile()
    assert profile is not None

    by_kind = profile.summary_by_kind()
    by_label = profile.summary_by_label()

    assert by_kind["batch"]["count"] == 5
    assert by_kind["batch"]["failures"] == 2
    assert by_label["ok-group"]["count"] == 3
    assert by_label["ok-group"]["failures"] == 0
    assert by_label["bad-group"]["count"] == 2
    assert by_label["bad-group"]["failures"] == 2
