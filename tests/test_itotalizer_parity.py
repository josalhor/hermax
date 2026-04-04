import random

import pytest

pytest.importorskip("hermax.internal.card")
pytest.importorskip("pysat.card")
from hermax.internal.card import ITotalizer as HermaxITotalizer
from pysat.card import ITotalizer as PySATITotalizer


def _ensure_available():
    return


def _rand_lits(rng: random.Random, n: int, vmax: int = 60):
    vals = set()
    while len(vals) < n:
        v = rng.randint(1, vmax)
        vals.add(v if rng.random() < 0.5 else -v)
    return list(vals)


def _assert_state_eq(a, b):
    assert a.top_id == b.top_id
    assert a.ubound == b.ubound
    assert a.rhs == b.rhs
    assert a.nof_new == b.nof_new
    assert a.cnf.nv == b.cnf.nv
    assert a.cnf.clauses == b.cnf.clauses


def _new_pair(lits, ubound, top_id):
    a = HermaxITotalizer(lits=lits, ubound=ubound, top_id=top_id)
    b = PySATITotalizer(lits=lits, ubound=ubound, top_id=top_id)
    _assert_state_eq(a, b)
    return a, b


def _do_random_op(rng: random.Random, a, b):
    op = rng.choice(["increase", "extend", "merge"])

    if op == "increase":
        ubound = rng.randint(0, max(len(a.lits) + 3, 3))
        top_id = None if rng.random() < 0.35 else rng.randint(0, 120)
        a.increase(ubound=ubound, top_id=top_id)
        b.increase(ubound=ubound, top_id=top_id)
        _assert_state_eq(a, b)
        return

    if op == "extend":
        add_n = rng.randint(0, 8)
        add_lits = _rand_lits(rng, add_n, vmax=70)
        ubound = None if rng.random() < 0.4 else rng.randint(0, max(len(a.lits) + add_n + 3, 3))
        top_id = None if rng.random() < 0.35 else rng.randint(0, 140)
        a.extend(lits=add_lits, ubound=ubound, top_id=top_id)
        b.extend(lits=add_lits, ubound=ubound, top_id=top_id)
        _assert_state_eq(a, b)
        return

    # merge
    other_lits = _rand_lits(rng, rng.randint(1, 8), vmax=80)
    other_ub = rng.randint(0, max(len(other_lits), 1))
    other_top = None if rng.random() < 0.4 else rng.randint(0, 160)

    a2, b2 = _new_pair(other_lits, other_ub, other_top)
    try:
        ubound = None if rng.random() < 0.4 else rng.randint(0, max(len(a.lits) + len(other_lits) + 3, 3))
        top_id = None if rng.random() < 0.35 else rng.randint(0, 180)
        a.merge_with(a2, ubound=ubound, top_id=top_id)
        b.merge_with(b2, ubound=ubound, top_id=top_id)
        _assert_state_eq(a, b)
    finally:
        # merged trees are flagged internally; explicit delete remains safe
        a2.delete()
        b2.delete()


@pytest.mark.parametrize("seed", [7, 13, 29, 41, 73, 101, 211, 313, 509, 887])
def test_itotalizer_random_parity(seed):
    _ensure_available()
    rng = random.Random(seed)

    lits = _rand_lits(rng, rng.randint(1, 10), vmax=50)
    ubound = rng.randint(0, max(len(lits), 1))
    top_id = None if rng.random() < 0.4 else rng.randint(0, 100)

    a, b = _new_pair(lits, ubound, top_id)
    try:
        steps = 25
        for _ in range(steps):
            _do_random_op(rng, a, b)
    finally:
        a.delete()
        b.delete()


def test_itotalizer_edge_cases_parity():
    _ensure_available()

    a, b = _new_pair([1, -2, 3], ubound=1, top_id=None)
    try:
        # no-op increase
        a.increase(ubound=1, top_id=None)
        b.increase(ubound=1, top_id=None)
        _assert_state_eq(a, b)

        # extend with duplicates and existing literals
        a.extend(lits=[3, -2, 4, -4, 4], ubound=2, top_id=20)
        b.extend(lits=[3, -2, 4, -4, 4], ubound=2, top_id=20)
        _assert_state_eq(a, b)

        # extend without bound update
        a.extend(lits=[5, -6], ubound=None, top_id=None)
        b.extend(lits=[5, -6], ubound=None, top_id=None)
        _assert_state_eq(a, b)

        # merge with empty-ish bound effects
        a2, b2 = _new_pair([7, -8], ubound=1, top_id=10)
        try:
            a.merge_with(a2, ubound=None, top_id=None)
            b.merge_with(b2, ubound=None, top_id=None)
            _assert_state_eq(a, b)
        finally:
            a2.delete()
            b2.delete()
    finally:
        a.delete()
        b.delete()
