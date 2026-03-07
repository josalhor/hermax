from __future__ import annotations

import itertools
import random

import pytest

import hermax.model as hm
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus
from hermax.model import Clause, Model, Term


def _lit_value(lit, assignment: dict[int, bool]) -> int:
    v = assignment[lit.id]
    return int(v if lit.polarity else (not v))


def _eval_pbexpr(expr, assignment: dict[int, bool]) -> int:
    return int(expr.constant) + sum(int(t.coefficient) * _lit_value(t.literal, assignment) for t in expr.terms)


def _eval_clause(c: Clause, assignment: dict[int, bool]) -> bool:
    return any(_lit_value(l, assignment) == 1 for l in c.literals)


def test_private_normalize_pb_preserves_numeric_value_randomized():
    rnd = random.Random(12345)
    m = Model()
    lits = [m.bool(f"b{i}") for i in range(5)]

    for _ in range(120):
        lhs_terms = []
        rhs_terms = []
        for lit in lits:
            c1 = rnd.randint(-3, 3)
            c2 = rnd.randint(-3, 3)
            if c1 != 0:
                lhs_terms.append(Term(c1, lit))
            if c2 != 0:
                rhs_terms.append(Term(c2, lit))
        lhs = hm.PBExpr(m, lhs_terms, rnd.randint(-4, 4))
        rhs = hm.PBExpr(m, rhs_terms, rnd.randint(-4, 4))

        pairs, const = hm._EncoderDispatch._normalize_pb(lhs, rhs)
        for bits in itertools.product([False, True], repeat=len(lits)):
            asg = {l.id: b for l, b in zip(lits, bits)}
            raw = _eval_pbexpr(lhs - rhs, asg)
            norm = int(const) + sum(int(w) * _lit_value(l, asg) for w, l in pairs)
            assert raw == norm


@pytest.mark.parametrize("op,const,expected", [
    ("<=", 3, ("<=", -3)),
    ("<", 3, ("<=", -4)),
    (">=", 3, (">=", -3)),
    (">", 3, (">=", -2)),
    ("==", 3, ("==", -3)),
])
def test_private_bound_from_zero_compare(op, const, expected):
    assert hm._EncoderDispatch._bound_from_zero_compare(op, const) == expected


def test_private_extract_multi_int_affine_accepts_full_lift_and_rejects_partial_or_neg_polarity():
    m = Model()
    x = m.int("x", 2, 6)
    y = m.int("y", 0, 4)

    ok = hm._EncoderDispatch._extract_multi_int_affine(m, (2 * x) + (3 * y) + 7)
    assert ok is not None
    coeffs, offset = ok
    by_name = {v.name: c for v, c in coeffs}
    assert by_name["x"] == 2
    assert by_name["y"] == 3
    # offset = expr.constant - sum(c*lb)
    assert offset == 7

    # Partial lifted (single threshold literal) is not affine IntVar form.
    partial = hm.PBExpr(m, [Term(1, x.__ge__(3))], 0)
    assert hm._EncoderDispatch._extract_multi_int_affine(m, partial) is None

    # Negative-polarity threshold literal is rejected.
    neg = hm.PBExpr(m, [Term(1, ~x.__ge__(3))], 0)
    assert hm._EncoderDispatch._extract_multi_int_affine(m, neg) is None


@pytest.mark.parametrize("op,k", [
    ("<=", -1), ("<=", 1), ("<=", 20),
    ("<", 0), ("<", 2), ("<", 20),
    (">=", -5), (">=", 3), (">=", 15),
    (">", -5), (">", 3), (">", 15),
    ("==", -2), ("==", 4), ("==", 30),
])
def test_private_int_cmp_constraint_matches_semantics(op, k):
    m = Model()
    x = m.int("x", 1, 8)
    out = hm._EncoderDispatch._int_cmp_constraint(x, op, k)

    for xv in range(x.lb, x.ub):
        mm = Model()
        xx = mm.int("x", 1, 8)
        mm &= (xx == xv)
        if isinstance(out, bool):
            expected = out
        else:
            # Rebuild comparable literal on mirror model.
            if op == "<=":
                expected = (xv <= k)
                lit = (xx <= k)
            elif op == "<":
                expected = (xv < k)
                lit = (xx < k)
            elif op == ">=":
                expected = (xv >= k)
                lit = (xx >= k)
            elif op == ">":
                expected = (xv > k)
                lit = (xx > k)
            else:
                expected = (xv == k)
                lit = (xx == k)
            mm &= lit
            assert (mm.solve().status != "unsat") == expected
            continue
        assert expected == eval(f"{xv} {op} {k}")


def test_private_lit_implies_constant_folding_semantics():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    clauses: list[Clause] = []

    hm._EncoderDispatch._lit_implies(clauses, m, True, b)   # b
    hm._EncoderDispatch._lit_implies(clauses, m, False, b)  # tautology
    hm._EncoderDispatch._lit_implies(clauses, m, a, True)   # tautology
    hm._EncoderDispatch._lit_implies(clauses, m, a, False)  # ~a
    hm._EncoderDispatch._lit_implies(clauses, m, a, b)      # ~a v b

    for av, bv in itertools.product([False, True], repeat=2):
        asg = {a.id: av, b.id: bv}
        got = all(_eval_clause(c, asg) for c in clauses)
        expected = (bv and (not av) and ((not av) or bv))
        assert got == expected


class _PrivateFakeIP(IPAMIRSolver):
    def __init__(self):
        super().__init__()
        self.hard: list[list[int]] = []
        self.soft: dict[int, int] = {}
        self._status = SolveStatus.OPTIMUM

    def add_clause(self, clause: list[int]) -> None:
        self.hard.append([int(x) for x in clause])

    def set_soft(self, lit: int, weight: int) -> None:
        self.soft[int(lit)] = int(weight)

    def add_soft_unit(self, lit: int, weight: int) -> None:
        self.set_soft(lit, weight)

    def new_var(self) -> int:
        raise NotImplementedError

    def solve(self, assumptions=None, raise_on_abnormal: bool = False) -> bool:
        return True

    def get_status(self) -> SolveStatus:
        return self._status

    def get_cost(self) -> int:
        return 0

    def val(self, lit: int) -> int:
        return 0

    def get_model(self):
        return []

    def signature(self) -> str:
        return "private-fake"

    def close(self) -> None:
        return None


def test_private_incremental_route_soft_zero_weight_disables_in_backend():
    m = Model()
    a = m.bool("a")
    ref = m.add_soft(a, weight=5)
    s = _PrivateFakeIP()
    m._inc_state.bind_maxsat(s, {})
    sid = ref.soft_ids[0]
    # Ensure mapped in backend first.
    assert sid in m._inc_state.soft_lit_by_id
    lit = m._inc_state.soft_lit_by_id[sid]
    assert s.soft.get(int(lit), None) == 5

    # Zero weight is propagated to backend via private coordinator path.
    m._inc_state.update_soft_weight(int(sid), 0, allow_zero=True, allow_when_sat=True)
    assert s.soft[int(lit)] == 0


def test_private_equiv_literals_group_constant_folding_semantics():
    m = Model()
    a = m.bool("a")
    t = m._get_bool_constant_literal(True)
    f = m._get_bool_constant_literal(False)

    # a <-> a is tautological (empty group)
    g_same = m._equiv_literals_group(a, a)
    assert len(g_same.clauses) == 0

    # true <-> false is contradiction
    g_tf = m._equiv_literals_group(t, f)
    assert len(g_tf.clauses) == 1 and len(g_tf.clauses[0].literals) == 0

    # true <-> a  =>  (a)
    g_ta = m._equiv_literals_group(t, a)
    assert len(g_ta.clauses) == 1
    assert g_ta.clauses[0].literals == [a]

    # false <-> a => (~a)
    g_fa = m._equiv_literals_group(f, a)
    assert len(g_fa.clauses) == 1
    assert g_fa.clauses[0].literals == [~a]


def test_private_objective_proxy_current_weights_ignores_stale_sid_mapping():
    m = Model()
    a = m.bool("a")
    m.obj.set(a, weight=3)
    # Create stale sid mapping by deleting soft index entry.
    dim = m._lit_to_dimacs(~a)
    sid = m.obj._lit_to_sid[dim]
    del m._soft_id_to_index[sid]
    # Should ignore stale mapping instead of crashing.
    cur = m.obj._current_lit_weights()
    assert dim not in cur


def test_private_objective_proxy_apply_lit_weights_routes_deltas():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    # Start with one managed objective literal.
    m.obj.set(a, weight=2)
    old_const = m._objective_constant

    # Replace with another literal map and offset.
    lit_map = {m._lit_to_dimacs(~b): 7}
    m.obj._apply_lit_weights(lit_map, offset=5)
    cur = m.obj._current_lit_weights()
    assert cur == lit_map
    assert m._objective_constant == old_const + 5
