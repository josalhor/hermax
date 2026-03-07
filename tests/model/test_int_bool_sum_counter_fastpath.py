from __future__ import annotations

"""Fastpath tests for exact bool-sum <-> IntVar channeling.

Algorithm under test (in ``hermax.model._EncoderDispatch``):
1. Detect expressions of shape ``x + c1 == sum(unit_bools) + c2``.
2. Build a bidirectional sequential counter over the boolean literals:
   ``S[i,j] <-> (S[i-1,j] OR (S[i-1,j-1] AND b_i))`` where
   ``S[i,j]`` means "among first ``i`` literals, count >= ``j``".
3. Channel all integer threshold cuts (including implicit boundaries):
   ``(x >= k) <-> (count >= k - shift)``, with ``shift = c2 - c1``.

Asymptotic note:
- Let ``n`` be number of boolean literals and ``d = x.ub - x.lb``.
- Sequential counter construction is ``O(n^2)`` clauses/aux literals.
- Threshold channeling is ``O(d)`` clauses.
- Total: ``O(n^2 + d)``.
"""

import itertools
import random

import pytest

import hermax.model as hm
from hermax.model import Model
from pysat.formula import CNFPlus


def _solve(m: Model):
    return m.solve()


def _cmp(a: int, b: int) -> bool:
    return a == b


def _constraint_builder(x, lits, offset_x: int = 0, offset_s: int = 0, swapped: bool = False):
    lhs = x + offset_x
    rhs = sum(lits) + offset_s
    return (rhs == lhs) if swapped else (lhs == rhs)


def _constraint_builder_op(x, lits, op: str, offset_x: int = 0, offset_s: int = 0, swapped: bool = False):
    lhs = x + offset_x
    rhs = sum(lits) + offset_s
    if swapped:
        lhs, rhs = rhs, lhs
    if op == "==":
        return lhs == rhs
    if op == "<=":
        return lhs <= rhs
    if op == ">=":
        return lhs >= rhs
    if op == "<":
        return lhs < rhs
    if op == ">":
        return lhs > rhs
    raise ValueError(op)


def _bruteforce_sat(lb: int, ub: int, n_lits: int, offset_x: int = 0, offset_s: int = 0) -> bool:
    dom = range(lb, ub)
    for xv in dom:
        for bits in itertools.product([0, 1], repeat=n_lits):
            if _cmp(xv + offset_x, sum(bits) + offset_s):
                return True
    return False


def _bruteforce_sat_op(lb: int, ub: int, n_lits: int, op: str, offset_x: int = 0, offset_s: int = 0) -> bool:
    dom = range(lb, ub)
    for xv in dom:
        for bits in itertools.product([0, 1], repeat=n_lits):
            a = xv + offset_x
            b = sum(bits) + offset_s
            ok = (
                (a == b) if op == "==" else
                (a <= b) if op == "<=" else
                (a >= b) if op == ">=" else
                (a < b) if op == "<" else
                (a > b)
            )
            if ok:
                return True
    return False


@pytest.mark.parametrize("lb,ub,n_lits,ox,os", [
    (0, 5, 3, 0, 0),
    (0, 4, 4, 0, 0),
    (-2, 4, 3, 1, -1),
    (1, 7, 5, -2, 1),
    (0, 2, 0, 0, 0),
    (3, 6, 2, 0, 3),
    (3, 6, 2, 0, -3),
])
def test_bool_sum_intvar_equality_matches_bruteforce_sat(lb, ub, n_lits, ox, os):
    # Exhaustive SAT/UNSAT agreement on small domains.
    expected = _bruteforce_sat(lb, ub, n_lits, ox, os)
    m = Model()
    x = m.int("x", lb, ub)
    lits = [m.bool(f"b{i}") for i in range(n_lits)]
    m &= _constraint_builder(x, lits, offset_x=ox, offset_s=os)
    r = _solve(m)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("swapped", [False, True])
def test_bool_sum_intvar_equality_swapped_sides_equivalent(swapped: bool):
    # Detection must be orientation-agnostic: x==sum and sum==x.
    m = Model()
    x = m.int("x", 0, 6)
    b = [m.bool(f"b{i}") for i in range(4)]
    m &= _constraint_builder(x, b, offset_x=1, offset_s=2, swapped=swapped)
    r = _solve(m)
    assert r.ok


@pytest.mark.parametrize("xv,bits,ox,os", [
    (0, [0, 0, 0], 0, 0),
    (1, [1, 0, 0], 0, 0),
    (2, [1, 1, 0], 0, 0),
    (3, [1, 1, 1], 0, 0),
    (2, [1, 0, 1, 0], 1, 0),
    (4, [1, 1, 1, 1], -1, 1),
])
def test_bool_sum_intvar_equality_point_witnesses(xv, bits, ox, os):
    # Pointwise correctness, not only existence.
    m = Model()
    x = m.int("x", 0, 8)
    lits = [m.bool(f"b{i}") for i in range(len(bits))]
    m &= _constraint_builder(x, lits, offset_x=ox, offset_s=os)
    m &= (x == xv)
    for lit, val in zip(lits, bits):
        m &= (lit if val else ~lit)
    r = _solve(m)
    expected = (xv + ox) == (sum(bits) + os)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("xv,bits", [
    (0, [0, 0, 0]),
    (1, [0, 1, 0]),
    (2, [1, 1, 0]),
    (3, [1, 1, 1]),
])
def test_bool_sum_intvar_with_negated_literal_terms(xv, bits):
    m = Model()
    x = m.int("x", 0, 5)
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    # sum includes a negated literal term
    m &= (x == (a + ~b + c))
    m &= (x == xv)
    assign = [a, b, c]
    for lit, val in zip(assign, bits):
        m &= (lit if val else ~lit)
    r = _solve(m)
    count = int(bits[0]) + int(not bits[1]) + int(bits[2])
    assert (r.ok if xv == count else r.status == "unsat")


def test_bool_sum_intvar_equality_bypasses_pb_and_card(monkeypatch):
    # Core requirement: no PB/Card backend calls on supported shape.
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for x == sum(bools)")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for x == sum(bools)")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 6)
    b = [m.bool(f"b{i}") for i in range(5)]
    m &= (x == sum(b))
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


def test_bool_sum_intvar_equality_with_offsets_bypasses_pb_and_card(monkeypatch):
    # Same bypass guarantee under nontrivial constant shifts.
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for x+off == sum(b)+off")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for x+off == sum(b)+off")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", -2, 8)
    b = [m.bool(f"b{i}") for i in range(6)]
    m &= (x + 3 == sum(b) - 1)
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


@pytest.mark.parametrize("expr_builder", [
    lambda x, b: (x == (2 * b[0] + b[1] + b[2])),
    lambda x, b: (x == (b[0] + b[1] + b[2] + b[3] + b[4] + b[5] + b[0])),
    lambda x, b: ((2 * x) == sum(b)),
])
def test_bool_sum_intvar_falls_back_to_pb_for_unsupported_shapes(monkeypatch, expr_builder):
    # Unsupported forms must not accidentally use this fastpath.
    called = {"pb": 0}

    def wrapped(*args, **kwargs):
        called["pb"] += 1
        return CNFPlus()

    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(wrapped))

    m = Model()
    x = m.int("x", 0, 8)
    b = [m.bool(f"b{i}") for i in range(6)]
    m &= expr_builder(x, b)
    _solve(m)
    assert called["pb"] >= 1


def test_bool_sum_intvar_equality_adds_aux_bools_but_no_new_intvars():
    # Counter introduces auxiliary booleans but no extra IntVar ladders.
    m = Model()
    x = m.int("x", 0, 10)
    b = [m.bool(f"b{i}") for i in range(7)]
    top_before = m._top_id()
    int_vars_before = len(m._intvar_threshold_owner_by_litid)

    m &= (x == sum(b))

    assert m._top_id() > top_before
    assert len(m._intvar_threshold_owner_by_litid) == int_vars_before


def test_bool_sum_intvar_equality_empty_sum_edgecases():
    m1 = Model()
    x1 = m1.int("x1", 0, 1)
    m1 &= (x1 == sum([]))
    r1 = _solve(m1)
    assert r1.ok
    assert r1[x1] == 0

    m2 = Model()
    x2 = m2.int("x2", 1, 2)
    m2 &= (x2 + 0 == sum([]))
    r2 = _solve(m2)
    assert r2.status == "unsat"


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5, 1337])
def test_bool_sum_intvar_randomized_point_checks(seed: int):
    # Fuzzing for hidden corner cases in channeling arithmetic.
    rng = random.Random(seed)
    for _ in range(20):
        n = rng.randint(1, 6)
        lb = rng.randint(-2, 2)
        ub = lb + rng.randint(3, 8)
        ox = rng.randint(-2, 2)
        os = rng.randint(-2, 2)

        m = Model()
        x = m.int("x", lb, ub)
        lits = [m.bool(f"b{i}") for i in range(n)]
        m &= (x + ox == sum(lits) + os)

        xv = rng.randint(lb, ub - 1)
        bits = [rng.randint(0, 1) for _ in range(n)]
        m &= (x == xv)
        for lit, bit in zip(lits, bits):
            m &= (lit if bit else ~lit)

        r = _solve(m)
        expected = (xv + ox) == (sum(bits) + os)
        assert (r.ok if expected else r.status == "unsat")


def test_bool_sum_intvar_enforces_upper_boundary_cut_k_eq_ub():
    # Regression: missing k=ub cut can admit spurious SAT on shifted domains.
    # x in [3,6), bool sum in [0,2], constraint x == sum - 3 is impossible.
    m = Model()
    x = m.int("x", 3, 6)
    b0 = m.bool("b0")
    b1 = m.bool("b1")
    m &= (x == (b0 + b1 - 3))
    r = _solve(m)
    assert r.status == "unsat"


def test_bool_sum_intvar_enforces_lower_boundary_cut_k_eq_lb():
    # Regression: missing k=lb cut can admit spurious SAT for over-shifted sums.
    # x in [0,3), bool sum in [0,2], constraint x + 5 == sum is impossible.
    m = Model()
    x = m.int("x", 0, 3)
    b0 = m.bool("b0")
    b1 = m.bool("b1")
    m &= (x + 5 == (b0 + b1))
    r = _solve(m)
    assert r.status == "unsat"


def test_bool_sum_intvar_shifted_orientation_equivalence_pointwise():
    # Same semantics regardless of which side has IntVar affine form.
    # (x + 2 == sum + 1)  <=>  (sum + 1 == x + 2)
    m1 = Model()
    x1 = m1.int("x", -1, 5)
    b1 = [m1.bool(f"a{i}") for i in range(3)]
    m1 &= (x1 + 2 == sum(b1) + 1)
    m1 &= (x1 == 2)
    m1 &= b1[0]
    m1 &= ~b1[1]
    m1 &= b1[2]
    r1 = _solve(m1)

    m2 = Model()
    x2 = m2.int("x", -1, 5)
    b2 = [m2.bool(f"a{i}") for i in range(3)]
    m2 &= (sum(b2) + 1 == x2 + 2)
    m2 &= (x2 == 2)
    m2 &= b2[0]
    m2 &= ~b2[1]
    m2 &= b2[2]
    r2 = _solve(m2)

    assert r1.status == r2.status


def test_bool_sum_intvar_fastpath_does_not_trigger_with_int_terms_on_bool_side(monkeypatch):
    # If bool side contains Int terms, detection must reject and fallback.
    called = {"pb": 0, "card": 0}

    def wrapped(*args, **kwargs):
        called["pb"] += 1
        return CNFPlus()

    def wrapped_card(*args, **kwargs):
        called["card"] += 1
        return CNFPlus()

    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(wrapped))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(wrapped_card))

    m = Model()
    x = m.int("x", 0, 6)
    y = m.int("y", 0, 6)
    b = [m.bool(f"b{i}") for i in range(3)]
    m &= (x == (sum(b) + y))
    _solve(m)
    assert (called["pb"] + called["card"]) >= 1


@pytest.mark.parametrize("op", ["<=", ">=", "<", ">"])
@pytest.mark.parametrize("lb,ub,n_lits,ox,os", [
    (0, 5, 3, 0, 0),
    (0, 4, 4, 1, -1),
    (-2, 4, 3, 1, -1),
    (1, 7, 5, -2, 1),
    (0, 2, 0, 0, 0),
    (3, 6, 2, 0, 3),
    (3, 6, 2, 0, -3),
])
def test_bool_sum_intvar_inequalities_match_bruteforce_sat(op, lb, ub, n_lits, ox, os):
    expected = _bruteforce_sat_op(lb, ub, n_lits, op, ox, os)
    m = Model()
    x = m.int("x", lb, ub)
    lits = [m.bool(f"b{i}") for i in range(n_lits)]
    m &= _constraint_builder_op(x, lits, op=op, offset_x=ox, offset_s=os)
    r = _solve(m)
    assert (r.ok if expected else r.status == "unsat")


@pytest.mark.parametrize("op", ["<=", ">=", "<", ">"])
def test_bool_sum_intvar_inequalities_swapped_sides_equivalent(op):
    m1 = Model()
    x1 = m1.int("x", -1, 6)
    b1 = [m1.bool(f"b{i}") for i in range(4)]
    m1 &= _constraint_builder_op(x1, b1, op=op, offset_x=1, offset_s=2, swapped=False)
    r1 = _solve(m1)

    m2 = Model()
    x2 = m2.int("x", -1, 6)
    b2 = [m2.bool(f"b{i}") for i in range(4)]
    m2 &= _constraint_builder_op(x2, b2, op=op, offset_x=1, offset_s=2, swapped=True)
    r2 = _solve(m2)

    assert r1.status == r2.status


@pytest.mark.parametrize("op", ["<=", ">=", "<", ">"])
def test_bool_sum_intvar_inequalities_bypass_pb_and_card(monkeypatch, op):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for IntVar-vs-bool-sum inequality fastpath")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for IntVar-vs-bool-sum inequality fastpath")

    monkeypatch.setattr(hm.PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(hm.PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(hm.CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(hm.CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", -2, 8)
    b = [m.bool(f"b{i}") for i in range(6)]
    m &= _constraint_builder_op(x, b, op=op, offset_x=3, offset_s=-1)
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}


@pytest.mark.parametrize("seed", [7, 8, 9, 10, 2026])
def test_bool_sum_intvar_inequalities_randomized_point_checks(seed: int):
    rng = random.Random(seed)
    for _ in range(20):
        n = rng.randint(1, 6)
        lb = rng.randint(-2, 2)
        ub = lb + rng.randint(3, 8)
        ox = rng.randint(-2, 2)
        os = rng.randint(-2, 2)
        op = rng.choice(["<=", ">=", "<", ">"])

        m = Model()
        x = m.int("x", lb, ub)
        lits = [m.bool(f"b{i}") for i in range(n)]
        m &= _constraint_builder_op(x, lits, op=op, offset_x=ox, offset_s=os)

        xv = rng.randint(lb, ub - 1)
        bits = [rng.randint(0, 1) for _ in range(n)]
        m &= (x == xv)
        for lit, bit in zip(lits, bits):
            m &= (lit if bit else ~lit)

        r = _solve(m)
        a = xv + ox
        bval = sum(bits) + os
        expected = (
            (a <= bval) if op == "<=" else
            (a >= bval) if op == ">=" else
            (a < bval) if op == "<" else
            (a > bval)
        )
        assert (r.ok if expected else r.status == "unsat")
