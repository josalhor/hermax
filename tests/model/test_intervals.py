import pytest

from hermax.model import ClauseGroup, IntervalVar, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_interval_construction_creates_start_end_and_enforces_duration_relation():
    m = Model()
    task = m.interval("A", start=0, duration=5, end=24)

    assert isinstance(task, IntervalVar)
    assert task.name == "A"
    assert task.duration == 5
    # Inclusive latest-end semantics:
    # start in [0, 20), end in [5, 25)
    assert task.start.lb == 0 and task.start.ub == 20
    assert task.end.lb == 5 and task.end.ub == 25

    # Pin start and verify end is forced by the structural equality.
    m &= (task.start == 7)
    r = _solve_ok(m)
    assert r[task.start] == 7
    assert r[task.end] == 12
    assert r[task] == {"start": 7, "end": 12, "duration": 5}


def test_interval_identity_is_linear_ladder_weld_without_pb_aux_blowup():
    m = Model()
    before_hard = len(m._hard)
    task = m.interval("A", start=0, duration=5, end=24)

    span = task.start.ub - task.start.lb
    assert span == (task.end.ub - task.end.lb)

    # Domain constraints:
    # - start ladder: (span-2) monotonic over compact (span-1)-bit ladder
    # - end ladder:   (span-2) monotonic over compact (span-1)-bit ladder
    # Weld constraints:
    # - 2 binary clauses per threshold bit = 2*(span-1)
    expected_added_hard = (span - 2) + (span - 2) + (2 * (span - 1))
    assert len(m._hard) - before_hard == expected_added_hard

    # No auxiliary helper variables should be introduced beyond the two endpoint ladders.
    # start and end each allocate `span-1` threshold literals.
    assert len(task.start._threshold_lits) == span - 1
    assert len(task.end._threshold_lits) == span - 1
    assert len(m._registry) == 2 * (span - 1)

    # Weld clauses should be binary and pairwise over the aligned ladders.
    weld = m._hard[-(2 * (span - 1)):]
    for cl in weld:
        assert len(cl.literals) == 2


def test_interval_invalid_duration_and_horizon_are_rejected():
    m = Model()
    with pytest.raises(ValueError, match="duration must be positive"):
        m.interval("A", start=0, duration=0, end=10)
    with pytest.raises(ValueError, match="horizon is too small"):
        m.interval("B", start=0, duration=5, end=4)


def test_interval_ends_before_semantics():
    m = Model()
    a = m.interval("A", start=0, duration=5, end=24)
    b = m.interval("B", start=0, duration=3, end=24)
    c = a.ends_before(b)
    assert isinstance(c, ClauseGroup)
    m &= c

    # Force a to end at 10 and b to start at 10 (touching allowed).
    m &= (a.start == 5)
    m &= (b.start == 10)
    r = _solve_ok(m)
    assert r[a.end] == 10
    assert r[b.start] == 10

    # Violation should be UNSAT.
    m2 = Model()
    a2 = m2.interval("A", start=0, duration=5, end=24)
    b2 = m2.interval("B", start=0, duration=3, end=24)
    m2 &= a2.ends_before(b2)
    m2 &= (a2.start == 8)   # a2.end = 13
    m2 &= (b2.start == 12)  # 13 <= 12 false
    assert m2.solve().status == "unsat"


def test_interval_no_overlap_allows_both_orientations_and_rejects_overlap():
    # Orientation A before B.
    m1 = Model()
    a1 = m1.interval("A", start=0, duration=5, end=24)
    b1 = m1.interval("B", start=0, duration=3, end=24)
    m1 &= a1.no_overlap(b1)
    m1 &= (a1.start == 2)   # a1.end = 7
    m1 &= (b1.start == 7)   # touching okay
    r1 = _solve_ok(m1)
    assert r1[a1.end] == 7
    assert r1[b1.start] == 7

    # Orientation B before A.
    m2 = Model()
    a2 = m2.interval("A", start=0, duration=5, end=24)
    b2 = m2.interval("B", start=0, duration=3, end=24)
    m2 &= a2.no_overlap(b2)
    m2 &= (a2.start == 10)  # a2.end = 15
    m2 &= (b2.start == 7)   # b2.end = 10
    r2 = _solve_ok(m2)
    assert r2[b2.end] == 10
    assert r2[a2.start] == 10

    # True overlap should be UNSAT.
    m3 = Model()
    a3 = m3.interval("A", start=0, duration=5, end=24)
    b3 = m3.interval("B", start=0, duration=3, end=24)
    m3 &= a3.no_overlap(b3)
    m3 &= (a3.start == 2)  # [2,7]
    m3 &= (b3.start == 6)  # [6,9] overlaps
    assert m3.solve().status == "unsat"


def test_interval_methods_validate_type_and_model():
    m1 = Model()
    m2 = Model()
    a = m1.interval("A", start=0, duration=2, end=10)
    b_other = m2.interval("B", start=0, duration=2, end=10)

    with pytest.raises(TypeError, match="IntervalVar"):
        a.ends_before(object())
    with pytest.raises(TypeError, match="IntervalVar"):
        a.no_overlap(object())
    with pytest.raises(ValueError, match="different models"):
        a.ends_before(b_other)
    with pytest.raises(ValueError, match="different models"):
        a.no_overlap(b_other)


def test_interval_no_overlap_self_is_contradiction():
    m = Model()
    a = m.interval("A", start=0, duration=2, end=10)
    m &= a.no_overlap(a)
    assert m.solve().status == "unsat"
