import itertools
import operator

import pytest
from pysat.solvers import Solver

from hermax.model import ClauseGroup, IntervalVar, Model
from hermax.model._integer_views import binary_view_ready


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
    # start in [0, 19], end in [5, 24]
    assert task.start.lb == 0 and task.start.ub == 19
    assert task.end.lb == 5 and task.end.ub == 24

    # Pin start and verify end is forced by the structural equality.
    m &= (task.start == 7)
    r = _solve_ok(m)
    assert r[task.start] == 7
    assert r[task.end] == 12
    assert r[task] == {"start": 7, "end": 12, "duration": 5}


def test_interval_endpoints_share_one_order_encoding():
    m = Model()
    before_hard = len(m._hard)
    task = m.interval("A", start=0, duration=5, end=24)

    span = task.start.ub - task.start.lb
    assert span == (task.end.ub - task.end.lb)
    ncuts = len(task.start._threshold_lits)

    assert task.end._threshold_lits is task.start._threshold_lits
    assert len(m._hard) - before_hard == ncuts - 1
    assert m._top_id() == ncuts
    assert len(m._registry) == 0


@pytest.mark.parametrize("start,duration,width", [(-5, 3, 0), (-5, 3, 1), (-5, 3, 4), (2, 7, 4)])
def test_shifted_endpoint_predicates_reuse_start_predicates(start, duration, width):
    m = Model()
    task = m.interval("job", start=start, duration=duration, end=start + width + duration)
    for value in range(start, start + width + 1):
        assert (task.end >= value + duration) is (task.start >= value)
        assert (task.end <= value + duration) is (task.start <= value)
        assert (task.end == value + duration) is (task.start == value)
        equal = task.end == value + duration
        decoded = m.decode_model([m._lit_to_dimacs(equal)])
        assert decoded[task.end] == value + duration
        assert decoded[task.start] == value


@pytest.mark.parametrize("first_endpoint", ["start", "end"])
def test_interval_endpoints_reuse_the_same_binary_view(first_endpoint):
    m = Model()
    task = m.interval("job", start=-3, duration=5, end=42)
    first = getattr(task, first_endpoint)._get_binary_view()
    before = m._next_id, len(m._pending_literal_defs)
    assert task.start._get_binary_view() is first
    assert task.end._get_binary_view() is first
    assert (m._next_id, len(m._pending_literal_defs)) == before


def test_interval_end_equality_preserves_canonical_integer_ownership():
    m = Model()
    task = m.interval("job", start=-2, duration=3, end=5)
    for value in range(task.start.lb, task.start.ub + 1):
        literal = task.end == value + task.duration
        owner, owner_value = m._intvar_eq_owner_by_litid[m._lit_to_dimacs(literal)]
        assert owner is task.start
        assert owner_value == value


def test_shifted_endpoint_binary_readiness_follows_the_shared_owner():
    m = Model()
    task = m.interval("job", start=0, duration=3, end=43)
    task.start._get_binary_view()
    assert not binary_view_ready(task.end)
    m.to_cnf()
    assert binary_view_ready(task.start)
    assert binary_view_ready(task.end)


@pytest.mark.parametrize("comparison", [operator.le, operator.eq, operator.ge])
def test_shared_interval_endpoints_in_weighted_reified_arithmetic(comparison):
    m = Model()
    a = m.interval("a", start=-2, duration=3, end=5)
    b = m.interval("b", start=-1, duration=2, end=4)
    flag = m.bool("flag")
    m &= comparison(2 * a.end - 3 * a.start + b.end, 7).iff(flag)
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for av, bv, fv in itertools.product(range(-2, 3), range(-1, 3), (False, True)):
            fixed = [m._lit_to_dimacs(lit) for var, value in [(a.start, av), (b.start, bv)]
                     for lit in var._exact_value_atoms(value)]
            fixed.append(flag.id if fv else -flag.id)
            assert solver.solve(assumptions=fixed) is (
                fv == comparison(2 * (av + 3) - 3 * av + bv + 2, 7)
            )


@pytest.mark.parametrize("coefficient", [-3, 1, 4])
def test_shared_interval_endpoints_in_binary_objectives(coefficient):
    m = Model()
    task = m.interval("job", start=-2, duration=3, end=40)
    m.obj = coefficient * task.end
    result = m.solve()
    assert result.cost == coefficient * (1 if coefficient > 0 else 40)
    assert result[task.end] == result[task.start] + 3


def test_shared_interval_endpoints_keep_both_names_reserved():
    m = Model()
    m.interval("job", start=0, duration=2, end=5)
    for name in ("job", "job.start", "job.end"):
        with pytest.raises(ValueError, match="already registered"):
            m.bool(name)


def test_interval_invalid_duration_and_horizon_are_rejected():
    m = Model()
    with pytest.raises(ValueError, match="duration must be positive"):
        m.interval("A", start=0, duration=0, end=10)
    with pytest.raises(ValueError, match="horizon is too small"):
        m.interval("B", start=0, duration=5, end=4)

    with pytest.raises(TypeError, match="must be ints"):
        m.interval("bool_start", start=True, duration=2, end=10)
    with pytest.raises(TypeError, match="must be ints"):
        m.interval("bool_duration", start=0, duration=True, end=10)
    with pytest.raises(TypeError, match="must be ints"):
        m.interval("bool_end", start=0, duration=2, end=False)


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


def test_interval_no_overlap_duplicate_deferred_construction_reuses_internal_helper():
    m = Model()
    a = m.interval("A", start=0, duration=2, end=10)
    b = m.interval("B", start=0, duration=2, end=10)

    c1 = a.no_overlap(b)
    c2 = a.no_overlap(b)

    hard_before = len(m._hard)
    top_before = m._top_id()
    m &= c1
    top_after_first = m._top_id()
    m &= c2

    assert len(m._hard) >= hard_before
    assert m._top_id() == top_after_first

    m &= (a.start == 0)
    m &= (b.start == 1)
    assert m.solve().status == "unsat"
