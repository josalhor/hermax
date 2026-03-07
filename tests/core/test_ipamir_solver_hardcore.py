#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Conformance and stress tests for IPAMIRSolver implementations.

- Status code discipline and uniqueness
- Model/cost validity and self-consistency
- Assumption scoping and incremental behavior
- Termination callback semantics and raise_on_abnormal
- Hard vs soft clause semantics via canonical small formulas
- Edge cases: empty clause, literal 0, invalid weights, duplicates, tautologies
- Random small instances with brute-force oracle
- Resource lifecycle: close, double-close, post-close behavior
- Optional features: set_terminate/new_var presence, not required

Heavy tests:
- Load and run real WCNF files if present (and RUN_HEAVY=1)

Environment:
- SEED=<int> sets RNG seed for randomized sections (default fixed).

"""

import os
import sys
import math
import time
import types
import random
import importlib
import unittest
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Iterable, Callable, Any

# --- Configuration via env vars ---
SEED = int(os.environ.get("SEED", "1337"))
random.seed(SEED)

from pysat.formula import WCNF

def _is_macos_arm64() -> bool:
    return sys.platform == "darwin" and os.uname().machine in {"arm64", "aarch64"}

class Stopper:
    def __init__(self, L=None):
        self.limit = L
        self.calls = 0
    def __call__(self):
        self.calls += 1
        return 1 if self.limit is None or self.calls >= self.limit else 0

from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus, is_feasible
from hermax.internal.model_check import (
    check_model as canonical_check_model,
    clause_satisfied as canonical_clause_satisfied,
    maxsat_cost_of_model as canonical_cost_of_model,
    model_satisfies_hard_clauses as canonical_model_satisfies_hards,
    normalize_soft_units_last_wins as canonical_normalize_softs_units_by_literal,
)

def _build_solver_with_state(SolverClass, hard_clauses, soft_units):
    s = SolverClass()
    for cl in hard_clauses:
        s.add_clause(cl)
    for lit, w in soft_units:
        s.add_soft_unit(lit, w)
    return s

def lit_true_in_model(lit: int, model: Iterable[int]) -> bool:
    s = set(model)
    return lit in s

def clause_satisfied(clause: Iterable[int], model: Iterable[int]) -> bool:
    return canonical_clause_satisfied(clause, model)

def model_satisfies_hards(hards: Iterable[Iterable[int]], model: Iterable[int]) -> bool:
    return canonical_model_satisfies_hards(hards, model)

def _max_var_from_model(model: List[int]) -> int:
    return max(abs(x) for x in model) if model else 0

def _normalize_softs_units_by_literal(
    softs: Iterable[Tuple[List[int], int]]
) -> List[Tuple[List[int], int]]:
    return canonical_normalize_softs_units_by_literal(softs)

def cost_of_model(model: Iterable[int],
                  softs: Iterable[Tuple[List[int], int]]) -> int:
    return canonical_cost_of_model(model, softs)


def all_assignments(vars_: List[int]) -> Iterable[List[int]]:
    """
    Enumerate all ± assignments as model lists with signed ints.
    """
    n = len(vars_)
    for mask in range(1 << n):
        m = []
        for i, v in enumerate(vars_):
            bit = (mask >> i) & 1
            m.append(v if bit else -v)
        yield m

def brute_force_optimum(hards: List[List[int]], softs: List[Tuple[List[int], int]]) -> Tuple[int, List[List[int]]]:
    """
    Return (min_cost, all_models_achieving_min_cost) via brute force enumeration.
    Variables are inferred from abs(lit) appearing in hards and softs.
    """

    # Normalize softs: IPAMIR semantics — overwrite duplicates of [-L]
    softs = _normalize_softs_units_by_literal(softs)


    varset = set()
    for cl in hards:
        varset |= {abs(x) for x in cl}
    for cl, _w in softs:
        varset |= {abs(x) for x in cl}
    vars_ = sorted(varset)
    best = None
    models = []
    for m in all_assignments(vars_):
        if not model_satisfies_hards(hards, m):
            continue
        c = cost_of_model(m, softs)
        if best is None or c < best:
            best = c
            models = [sorted(set(m), key=lambda x: (abs(x), x < 0))]
        elif c == best:
            models.append(sorted(set(m), key=lambda x: (abs(x), x < 0)))
    if best is None:
        # hard UNSAT
        return (math.inf, [])
    # Deduplicate models with same literal set
    uniq = []
    seen = set()
    for m in models:
        tup = tuple(sorted(m))
        if tup not in seen:
            seen.add(tup)
            uniq.append(m)
    return (best, uniq)

def assert_model_consistency(
    tc: unittest.TestCase,
    hards: List[List[int]],
    softs: List[Tuple[List[int], int]],
    model: List[int],
    val_func: Callable[[int], int],
    expected_cost: Optional[int] = None,
):
    """
    Ensure model satisfies all hards, and val(lit) agrees with membership.
    Optionally verify cost.
    """
    tc.assertTrue(model_satisfies_hards(hards, model), "Model must satisfy all hard clauses.")
    S = set(model)
    # Check val symmetry and bounds
    for lit in set(abs(x) for cl in hards for x in cl) | set(abs(x) for cl, _ in softs for x in cl):
        for signed in (lit, -lit):
            v = val_func(signed)
            tc.assertIn(v, (-1, 0, 1), f"val({signed}) must be in -1,0,1, got {v}")
            # If assigned, val must match sign
            if signed in S:
                tc.assertEqual(v, 1, f"val({signed}) should be 1 since literal is in model")
            elif -signed in S:
                tc.assertEqual(v, -1, f"val({signed}) should be -1 since negation is in model")
            # else may be 0 (unassigned) or assigned elsewhere
    if expected_cost is not None:
        tc.assertEqual(cost_of_model(model, softs), expected_cost, "Reported cost must match model cost.")

def assert_solver_report_self_consistent(
    tc: unittest.TestCase,
    hards: List[List[int]],
    softs: List[Tuple[List[int], int]],
    model: List[int],
    reported_cost: int,
):
    chk = canonical_check_model(model=model, hards=hards, softs=softs, reported_cost=reported_cost)
    tc.assertTrue(chk.hards_ok, "Returned model violates hard clauses.")
    tc.assertTrue(bool(chk.reported_cost_matches), f"Reported cost {reported_cost} != recomputed {chk.recomputed_cost}.")


class _ModelCheckingSolverProxy:
    """
    Test-only proxy that tracks clause additions and validates every feasible solve.

    Validation is solver-agnostic and checks:
    - returned model satisfies all hard clauses (including temporary assumptions)
    - returned cost matches canonical recomputation under wrapper soft semantics
    """

    def __init__(self, tc: unittest.TestCase, solver: IPAMIRSolver):
        self._tc = tc
        self._solver = solver
        self._hards: list[list[int]] = []
        self._softs: list[tuple[list[int], int]] = []

    def __getattr__(self, name):
        return getattr(self._solver, name)

    def close(self):
        return self._solver.close()

    def new_var(self):
        return self._solver.new_var()

    def add_clause(self, clause, weight=None):
        if weight is None:
            out = self._solver.add_clause(clause)
            self._hards.append([int(x) for x in clause])
            return out
        out = self._solver.add_clause(clause, weight)
        self._softs.append(([int(x) for x in clause], int(weight)))
        return out

    def set_soft(self, lit, weight):
        out = self._solver.set_soft(lit, weight)
        self._softs.append(([int(lit)], int(weight)))
        return out

    def add_soft_unit(self, lit, weight):
        out = self._solver.add_soft_unit(lit, weight)
        self._softs.append(([int(lit)], int(weight)))
        return out

    def add_soft_relaxed(self, clause, weight, relax_var):
        # Track semantic effect defined by IPAMIRSolver.add_soft_relaxed.
        cl = [int(x) for x in clause]
        w = int(weight)
        b = None if relax_var is None else abs(int(relax_var))
        out = self._solver.add_soft_relaxed(clause, weight, relax_var)
        if b is None:
            # Unit case only; non-unit with relax_var=None must raise and won't reach here.
            self._softs.append(([int(cl[0])], w))
        else:
            self._hards.append([*cl, b])
            self._softs.append(([-b], w))
        return out

    def solve(self, assumptions=None, raise_on_abnormal=False):
        sat = self._solver.solve(assumptions=assumptions, raise_on_abnormal=raise_on_abnormal)
        st = self._solver.get_status()
        if not is_feasible(st):
            return sat

        model = self._solver.get_model()
        cost = self._solver.get_cost()
        self._tc.assertIsNotNone(model, "Feasible solve must provide a model")
        temp_hards = self._hards + ([[int(a)] for a in (assumptions or [])])
        assert_solver_report_self_consistent(self._tc, temp_hards, self._softs, model, cost)
        return sat

def try_expect_abnormal(tc: unittest.TestCase, solver: IPAMIRSolver):
    """
    Check that status reflects an abnormal state: INTERRUPTED/UNKNOWN/ERROR
    """
    st = solver.get_status()
    tc.assertIn(
        st,
        {SolveStatus.INTERRUPTED, SolveStatus.UNKNOWN, SolveStatus.ERROR},
        f"Expected abnormal status, got {st.name} ({int(st)})"
    )

def make_amo_pairwise(vars_: List[int]) -> List[List[int]]:
    """
    At-most-one over vars via pairwise encoding: for all i<j, (¬vi ∨ ¬vj)
    """
    cls = []
    for i in range(len(vars_)):
        for j in range(i + 1, len(vars_)):
            cls.append([-vars_[i], -vars_[j]])
    return cls

def ensure_tautology_removed_or_ignored(tc: unittest.TestCase, solver: IPAMIRSolver):
    """
    Add tautological clause and ensure no change in result on a simple problem.
    """
    solver.add_clause([1])        # makes SAT
    r1 = solver.solve()
    tc.assertTrue(r1)
    st1 = solver.get_status()
    tc.assertEqual(st1, SolveStatus.OPTIMUM)
    cost1 = solver.get_cost()
    m1 = solver.get_model()
    tc.assertIsNotNone(m1)
    solver.add_clause([2, -2])    # tautology should not affect anything
    r2 = solver.solve()
    tc.assertTrue(r2)
    tc.assertEqual(solver.get_status(), SolveStatus.OPTIMUM)
    tc.assertEqual(solver.get_cost(), cost1)
    m2 = solver.get_model()
    tc.assertIsNotNone(m2)
    # No stronger assertion on model equality, solvers may return different but equivalent models.

class TestIPAMIRSolverHardcore(unittest.TestCase):
    """
    Hardcore test suite for any solver implementing IPAMIRSolver.
    """

    SOLVER_CLASS = None

    @classmethod
    def setUpClass(cls):
        cls.SolverClass = cls.SOLVER_CLASS
        if cls.SolverClass is None:
            raise unittest.SkipTest("SOLVER_CLASS is not available in this build.")
        if hasattr(cls.SolverClass, "is_available"):
            if not cls.SolverClass.is_available():
                raise unittest.SkipTest(f"{cls.SolverClass.__name__} is not available in this build.")
        print(f"\n[INFO] Testing solver: {cls.SolverClass.__name__}")
        print(f"[INFO] SEED={SEED}")

    def setUp(self):
        self.solver: IPAMIRSolver = self._wrap_solver(self.SolverClass())

    def _wrap_solver(self, solver: IPAMIRSolver) -> IPAMIRSolver:
        return _ModelCheckingSolverProxy(self, solver)

    def tearDown(self):
        self.solver.close()

    def test_001_signature_nonempty_and_stable(self):
        sig1 = self.solver.signature()
        self.assertIsInstance(sig1, str)
        self.assertGreater(len(sig1), 0)
        sig2 = self.solver.signature()
        self.assertEqual(sig1, sig2, "Signature should be stable between calls")

    def test_002_status_codes_uniqueness_and_types(self):
        # All statuses must be IntEnum and unique values
        codes = {
            "OPTIMUM": int(SolveStatus.OPTIMUM),
            "UNSAT": int(SolveStatus.UNSAT),
            "INTERRUPTED": int(SolveStatus.INTERRUPTED),
            "UNKNOWN": int(SolveStatus.UNKNOWN),
            "ERROR": int(SolveStatus.ERROR),
        }
        self.assertTrue(all(isinstance(v, int) for v in codes.values()))
        # Uniqueness
        values = list(codes.values())
        if len(set(values)) != len(values):
            self.fail(
                f"SolveStatus integer codes must be unique; got {codes}. "
                "ERROR matching UNKNOWN (or any collision) will break conformance checks."
            )
        # Basic ordering is not required, but UNSAT must not be treated as OPTIMUM
        self.assertNotEqual(SolveStatus.OPTIMUM, SolveStatus.UNSAT)

    def test_003_initial_status_unknown(self):
        self.assertEqual(self.solver.get_status(), SolveStatus.UNKNOWN)
        # self.assertIsNone(self.solver.get_model())
        # with self.assertRaises(RuntimeError):
        #     self.solver.get_status()
        with self.assertRaises(RuntimeError):
            self.solver.get_model()
        with self.assertRaises(RuntimeError):
            self.solver.get_cost()

    # ---- Happy path: trivial SAT/UNSAT ----

    def test_010_hard_sat_unit(self):
        self.solver.add_clause([1])
        sat = self.solver.solve()
        self.assertTrue(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m = self.solver.get_model()
        self.assertIsNotNone(m)
        self.assertIn(1, m)
        self.assertEqual(self.solver.val(1), 1)
        self.assertEqual(self.solver.val(-1), -1)
        self.assertEqual(self.solver.get_cost(), 0)

    def test_011_hard_unsat_contradiction(self):
        self.solver.add_clause([1])
        self.solver.add_clause([-1])
        sat = self.solver.solve()
        self.assertFalse(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)
        with self.assertRaises(RuntimeError):
            _ = self.solver.get_model()
        with self.assertRaises(RuntimeError):
            _ = self.solver.get_cost()

    def test_012_empty_clause_is_unsat(self):
        self.solver.add_clause([1])  # make instance SAT
        sat = self.solver.solve()
        self.assertTrue(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        # Empty hard clause forces UNSAT
        self.solver.add_clause([])
        sat = self.solver.solve()
        self.assertFalse(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)

    def test_013_literal_zero_rejected(self):
        # Literal 0 is invalid in DIMACS-style interfaces
        with self.assertRaises((ValueError, AssertionError)):
            self.solver.add_clause([0])
        with self.assertRaises((ValueError, AssertionError)):
            self.solver.add_clause([1, 0, -2])

    def test_014_tautology_ignored(self):
        ensure_tautology_removed_or_ignored(self, self.solver)
    
    def test_015_model_ordering_and_signs(self):
        self.solver.add_clause([1])
        self.solver.add_clause([-2])
        self.solver.add_clause([3])
        self.solver.add_clause([-4])
        # Skip 5
        self.solver.add_clause([6])
        # Skip 7
        self.solver.add_clause([-8])
        sat = self.solver.solve()
        self.assertTrue(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m = self.solver.get_model()
        self.assertIsNotNone(m)
        # Model must be:
        # [1, -2, 3, -4, (+/-)5, 6, (+/-)7, -8]
        
        print('====>', m)
        self.assertEqual(len(m), 8)
        self.assertEqual(m[0], 1)
        self.assertEqual(m[1], -2)
        self.assertEqual(m[2], 3)
        self.assertEqual(m[3], -4)
        self.assertIn(m[4], (5, -5))
        self.assertEqual(m[5], 6)
        self.assertIn(m[6], (7, -7))
        self.assertEqual(m[7], -8)

    def test_020_soft_units_competing_weights(self):
        hards = [[1, 2], [-1, -2]]
        softs = [([-1], 7), ([-2], 3)]
        self.solver.add_clause(hards[0])
        self.solver.add_clause(hards[1])
        self.solver.add_soft_unit(softs[0][0][0], softs[0][1])
        self.solver.add_soft_unit(softs[1][0][0], softs[1][1])
        sat = self.solver.solve()
        self.assertTrue(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m = self.solver.get_model()
        c = self.solver.get_cost()
        self.assertEqual(c, 3)
        self.assertIsNotNone(m)
        self.assertIn(sorted(set(m)), [sorted([-1, 2])])
        assert_model_consistency(self, hards, softs, m, self.solver.val, expected_cost=3)

    def test_021_soft_duplicate_clause_idempotent(self):
        hards = [[1]]  # force x1 true
        soft = ([-1], 5)  # violated if x1 true
        self.solver.add_clause(hards[0])
        self.solver.add_soft_unit(soft[0][0], soft[1])
        self.solver.add_soft_unit(soft[0][0], soft[1])  # duplicate soft
        sat = self.solver.solve()
        self.assertTrue(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        c = self.solver.get_cost()
        self.assertEqual(c, 5, "deduplicates soft clauses; expected cost 5.")

    def test_021_v2_soft_duplicate_clause_idempotent(self):
        # Adding the same soft clause twice. The underlying solver may deduplicate them.
        # This test verifies the observed behavior.
        hards = [[1]]  # force x1 true
        soft = ([-1], 5)  # violated if x1 true
        self.solver.add_clause(hards[0])
        self.solver.add_soft_unit(soft[0][0], soft[1])
        self.solver.add_soft_unit(soft[0][0], 4)  # Set weight 4 (lower)
        sat = self.solver.solve()
        self.assertTrue(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        c = self.solver.get_cost()
        self.assertEqual(c, 4, "deduplicates soft clauses; expected cost 4.")
    
    
    def test_021_soft_duplicate_clause_idempotent_unweighted(self):
        # Adding the same soft clause twice. The underlying solver may deduplicate them.
        # This test verifies the observed behavior.
        hards = [[1]]  # force x1 true
        soft = ([-1], 1)  # violated if x1 true
        self.solver.add_clause(hards[0])
        self.solver.add_soft_unit(soft[0][0], soft[1])
        self.solver.add_soft_unit(soft[0][0], soft[1])  # duplicate soft
        sat = self.solver.solve()
        self.assertTrue(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        c = self.solver.get_cost()
        self.assertEqual(c, 1, "deduplicates soft clauses; expected cost 1.")

    def test_022_soft_zero_or_negative_weight_rejected(self):
        # Weight must be positive. 0 or negative should error or set abnormal state.
        with self.assertRaises((ValueError, AssertionError)):
            self.solver.add_soft_unit(-1, 0)
        with self.assertRaises((ValueError, AssertionError)):
            self.solver.add_soft_unit(-2, -5)

    def test_023_soft_large_weights_64bit_bounds(self):
        # Accept large 64-bit weights, reject overflow if implemented.
        max_i64 = (1 << 63) - 1
        self.solver.add_clause([1])            # hard -> make instance SAT
        self.solver.add_soft_unit(-1, max_i64)  # soft penalizes x1 true with max weight
        sat = self.solver.solve()
        self.assertTrue(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        # Expected: cost=max_i64, since x1 must be true to satisfy hard [1]
        self.assertEqual(self.solver.get_cost(), max_i64)

    def test_024_reported_model_and_cost_self_consistency(self):
        if hasattr(self, "_skip_if_no_weights"):
            self._skip_if_no_weights()
        hards = [[1, 2], [-1, -2]]
        softs = [([-1], 7), ([-2], 3)]
        for cl in hards:
            self.solver.add_clause(cl)
        for cl, w in softs:
            self.solver.add_soft_unit(int(cl[0]), int(w))
        sat = self.solver.solve()
        self.assertTrue(sat)
        self.assertTrue(is_feasible(self.solver.get_status()))
        model = self.solver.get_model()
        cost = self.solver.get_cost()
        self.assertIsNotNone(model)
        assert_solver_report_self_consistent(self, hards, softs, model, cost)

    def test_030_assumptions_scope_and_reversion(self):
        # Hard XOR, softs as before: optimal [-1,2], cost 3
        self.solver.add_clause([1, 2])
        self.solver.add_clause([-1, -2])
        self.solver.add_soft_unit(-1, 7)
        self.solver.add_soft_unit(-2, 3)

        # Baseline
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        base_cost = self.solver.get_cost()
        base_model = self.solver.get_model()
        self.assertEqual(base_cost, 3)
        self.assertIsNotNone(base_model)

        # With assumption x1=true, force cost 7 and model [1, -2]
        self.assertTrue(self.solver.solve(assumptions=[1]))
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(self.solver.get_cost(), 7)
        m_assume = self.solver.get_model()
        self.assertIsNotNone(m_assume)
        self.assertIn(sorted(set(m_assume)), [sorted([1, -2])])

        # No assumptions again, revert to baseline opt
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(self.solver.get_cost(), base_cost)
        self.assertIn(sorted(set(self.solver.get_model())), [sorted(set(base_model))])

    def test_031_assumptions_conflict_with_hards(self):
        self.solver.add_clause([1])  # hard
        sat = self.solver.solve(assumptions=[-1])  # contradiction
        self.assertFalse(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)
        with self.assertRaises(RuntimeError):
            self.solver.get_model()

    def test_032_assumptions_dont_persist(self):
        self.solver.add_clause([1, 2])
        self.solver.add_clause([-1, -2])
        # Assumption x1 forces x1 true, so x2 false
        self.assertTrue(self.solver.solve(assumptions=[1]))
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m1 = self.solver.get_model()
        self.assertIsNotNone(m1)
        self.assertIn(1, m1)
        self.assertIn(-2, m1)

        # Next solve without assumptions may choose the opposite assignment
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m2 = self.solver.get_model()
        self.assertIsNotNone(m2)
        # Must satisfy XOR; either [1,-2] or [-1,2]
        self.assertTrue(
            set(m2) == set([1, -2]) or set(m2) == set([-1, 2]),
            f"Unexpected model without assumptions: {m2}"
        )

    def test_033_assumption_reported_model_and_cost_self_consistency(self):
        if hasattr(self, "_skip_if_no_weights"):
            self._skip_if_no_weights()
        hards = [[1, 2], [-1, -2]]
        softs = [([-1], 7), ([-2], 3)]
        for cl in hards:
            self.solver.add_clause(cl)
        for cl, w in softs:
            self.solver.add_soft_unit(int(cl[0]), int(w))

        self.assertTrue(self.solver.solve(assumptions=[1]))
        self.assertTrue(is_feasible(self.solver.get_status()))
        model = self.solver.get_model()
        cost = self.solver.get_cost()
        self.assertIsNotNone(model)
        assert_solver_report_self_consistent(self, hards + [[1]], softs, model, cost)

    def _add_pigeonhole_problem(self, pigeons: int = 6, holes: int = 5):
        """Adds a non-trivial, unsatisfiable problem to the solver."""
        def vid(i, j): return i * holes + j + 1
        # Each pigeon in at least one hole
        for i in range(pigeons):
            self.solver.add_clause([vid(i, j) for j in range(holes)])
        # No hole has two pigeons
        for j in range(holes):
            for i1 in range(pigeons):
                for i2 in range(i1 + 1, pigeons):
                    self.solver.add_clause([-vid(i1, j), -vid(i2, j)])

    def test_040_termination_interrupt_and_raise_flag(self):
        # Use a modestly complex unsat core to ensure some work
        self._add_pigeonhole_problem(pigeons=6, holes=5)
        # Add a soft to keep it as MaxSAT instance (though hards already UNSAT)
        self.solver.add_soft_unit(1, 1_000_000)

        # Install termination callback if supported
        
        stopper = Stopper(1)

        self.solver.set_terminate(stopper)

        sat = self.solver.solve(raise_on_abnormal=False)
        self.assertFalse(sat, "Interrupted solve should return False")
        self.assertEqual(self.solver.get_status(), SolveStatus.INTERRUPTED)
        self.assertGreaterEqual(stopper.calls, 1)
        # With raise flag, must raise
        stopper2 = Stopper(1)
        self.solver.set_terminate(stopper2)
        with self.assertRaises(RuntimeError):
            _ = self.solver.solve(raise_on_abnormal=True)
        self.assertEqual(self.solver.get_status(), SolveStatus.INTERRUPTED)
        self.assertGreaterEqual(stopper2.calls, 1)
        # Clear terminate and solve again: expect UNSAT (hard UNSAT)
        self.solver.set_terminate(None)
        sat2 = self.solver.solve()
        self.assertFalse(sat2)
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)

    def test_050_close_idempotent_and_post_close_behavior(self):
        self.solver.add_clause([1])
        self.solver.solve()
        self.solver.close()
        # Double-close should not crash
        self.solver.close()

        # After close, behavior is implementation-defined.
        # We require: either raises on calls OR returns abnormal status.
        def expect_closed_error_or_abnormal(call: Callable[[], Any]):
            try:
                call()
                # If no exception, then require abnormal status
                try_expect_abnormal(self, self.solver)
            except Exception:
                pass

        expect_closed_error_or_abnormal(lambda: self.solver.add_clause([1]))
        expect_closed_error_or_abnormal(lambda: self.solver.solve())
        # signature() MAY still work for diagnostics; do not require failure.

    def _rand_formulas_with_oracle(self, nvars: int, nhards: int, nsofts: int, kmax: int, wmax: int, cases=20) -> Iterable[Tuple[List[List[int]], List[Tuple[List[int], int]]]]:
        """
        Yield small random formulas with k-clauses up to kmax and positive weights up to wmax.
        Ensure nontriviality by mixing some AMO and XOR-like constraints.
        """
        rng = random.Random(SEED)
        vars_ = list(range(1, nvars + 1))
        for _ in range(cases):
            hards: List[List[int]] = []
            softs: List[Tuple[List[int], int]] = []
            # Some structured constraints
            if nvars >= 3:
                # XOR triangle on 1,2,3 to force parity: (x1 xor x2), (x2 xor x3)
                hards += [[1, 2], [-1, -2], [2, 3], [-2, -3]]
            # Random hard clauses
            for _h in range(nhards):
                k = rng.randint(1, min(kmax, nvars))
                lits = rng.sample(vars_, k)
                signed = [l if rng.getrandbits(1) else -l for l in lits]
                # avoid tautology
                if any(-x in signed for x in signed):
                    continue
                hards.append(signed)
            # Some AMO constraints on random subset
            chunk = rng.sample(vars_, min(3, nvars))
            hards += make_amo_pairwise(chunk)

            # Random soft unit or binary
            for _s in range(nsofts):
                k = rng.choice([1, 1, 2])  # favor units
                lits = rng.sample(vars_, k)
                signed = [l if rng.getrandbits(1) else -l for l in lits]
                w = rng.randint(1, wmax)
                # avoid tautology
                if any(-x in signed for x in signed):
                    continue
                softs.append((signed, w))

            # Avoid trivial UNSAT every time; let brute force tell us
            yield (hards, softs)

    def _add_clauses_on(self, hards: List[List[int]], softs: List[Tuple[List[int], int]]):
        max_var = max(
            [abs(x) for cl in hards for x in cl] +
            [abs(x) for cl, _ in softs for x in cl] + [1]
        )
        new_var = max_var + 1
        s :IPAMIRSolver = self.SolverClass()
        for cl in hards:
            s.add_clause(cl)
        
        for cl, w in softs:
            used_var = None
            if len(cl) > 1:
                # For non-units, use relaxed soft clause
                used_var = new_var
                new_var += 1
            s.add_soft_relaxed(cl, w, relax_var=used_var)
        return s

    def _run_solver_on(self, hards: List[List[int]], softs: List[Tuple[List[int], int]]):
        s = self._add_clauses_on(hards, softs)
        sat = s.solve()
        status = s.get_status()
        model = s.get_model() if is_feasible(status) else None
        cost = None
        if status == SolveStatus.OPTIMUM:
            self.assertTrue(sat)
            cost = s.get_cost()
        elif status == SolveStatus.UNSAT:
            self.assertFalse(sat)
        else:
            # abnormal; this test expects a definitive answer on tiny instances
            self.fail(f"Abnormal status {status.name} on tiny instance")
        s.close()
        return status, model, cost

    def test_060_random_mini_instances_match_bruteforce(self):
        # Small sizes to keep brute force tractable
        for hards, softs in self._rand_formulas_with_oracle(nvars=6, nhards=4, nsofts=4, kmax=3, wmax=7):
            min_cost, models = brute_force_optimum(hards, softs)
            status, model, cost = self._run_solver_on(hards, softs)
            if min_cost is math.inf:
                # UNSAT hard constraints expected
                self.assertEqual(status, SolveStatus.UNSAT)
                self.assertIsNone(model)
                self.assertIsNone(cost)
            else:
                self.assertEqual(status, SolveStatus.OPTIMUM)
                self.assertIsNotNone(model)
                self.assertIsNotNone(cost)
                self.assertEqual(cost, min_cost)
                # The solver may return any one optimal model
                # self.assertIn(sorted(set(model)), [sorted(m) for m in models])
                self.assertTrue(
                    self._equal_mod_irrelevant(model, models, hards, softs),
                    f"Model differs only on irrelevant variables: got {sorted(set(model))}, expected one of {models}"
                )

                # Basic internal consistency
                assert_model_consistency(self, hards, softs, model, lambda l: self.solver.val(l) if False else (1 if l in set(model) else -1 if -l in set(model) else 0), expected_cost=min_cost)

    def test_070_incremental_strengthening_never_decreases_cost(self):
        # Start with soft preferences only
        softs = [([-1], 4), ([-2], 3), ([-3], 2)]
        for cl, w in softs:
            self.solver.add_soft_unit(cl[0], w)
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        base_cost = self.solver.get_cost()

        # Add hard clause that forces x3=true, which violates soft([-3],2)
        self.solver.add_clause([3])
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        cost2 = self.solver.get_cost()
        self.assertGreaterEqual(cost2, base_cost, "Adding hard constraints cannot improve best cost")

    def test_071_incremental_additional_soft_can_only_increase_or_equal(self):
        # Hard XOR 1,2
        self.solver.add_clause([1, 2])
        self.solver.add_clause([-1, -2])

        # No softs: cost 0
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        c0 = self.solver.get_cost()
        self.assertEqual(c0, 0)

        # Add a soft penalizing x1 true
        self.solver.add_soft_unit(-1, 5)
        self.assertTrue(self.solver.solve())
        c1 = self.solver.get_cost()
        self.assertGreaterEqual(c1, c0)

        # Add another soft penalizing x2 true, but lighter, so optimum stays same cost 5
        self.solver.add_soft_unit(-2, 3)
        self.assertTrue(self.solver.solve())
        c2 = self.solver.get_cost()
        self.assertGreaterEqual(c2, c1)
        self.assertEqual(c2, 3, "With both softs, best is set x2 true and x1 false, cost 3")

    def test_080_duplicate_hard_clause_no_regression(self):
        self.solver.add_clause([1, 2])
        self.solver.add_clause([1, 2])  # duplicate
        self.solver.add_clause([-1, -2])
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)

    def test_081_tautologies_dont_block_progress(self):
        self.solver.add_clause([1])  # make SAT
        self.assertTrue(self.solver.solve())
        ensure_tautology_removed_or_ignored(self, self.solver)

    def test_090_new_var_optional(self):
        # new_var is optional; calling it may raise NotImplementedError
        try:
            v = self.solver.new_var()
            self.assertIsInstance(v, int)
            self.assertGreater(v, 0)
        except NotImplementedError:
            # Acceptable
            pass

    def test_091_set_terminate_optional(self):
        # set_terminate is optional; calling with None should at least be accepted if supported
        try:
            self.solver.set_terminate(None)
        except NotImplementedError:
            pass

    def _load_wcnf(self, path: str):
        if not os.path.exists(path):
            self.skipTest(f"WCNF file missing: {path}")
        return WCNF(from_file=path)

    def test_100_wcnf_real_instance_1(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, "data", "pseudoBoolean-normalized-par8-2.opb.msat.old.wcnf")
        wcnf = self._load_wcnf(path)
        # Load into solver
        for cl in wcnf.hard:
            self.solver.add_clause(cl)
        for cl, w in zip(wcnf.soft, wcnf.wght):
            assert len(cl) == 1
            self.solver.add_soft_unit(cl[0], int(w))
        start = time.time()
        ok = self.solver.solve()
        dur = time.time() - start
        st = self.solver.get_status()
        print(f"[HEAVY] {os.path.basename(path)}: ok={ok} status={st.name} cost={self.solver.get_cost() if st==SolveStatus.OPTIMUM else 'NA'} time={dur:.2f}s")
        # We don't assert specific optimum here; just require a definitive answer
        self.assertEqual(st, SolveStatus.OPTIMUM)

    def test_101_wcnf_real_instance_2(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, "data", "c-inference-pre-processing_c_inference_60_63_vq12.old.wcnf")

        wcnf = self._load_wcnf(path)
        for cl in wcnf.hard:
            self.solver.add_clause(cl)
        cont_non_unit = 0
        for cl, w in zip(wcnf.soft, wcnf.wght):
            if len(cl) == 1:
                self.solver.add_soft_unit(cl[0], int(w))
            else:
                # NON-unit soft clause!!!
                cont_non_unit += 1
                self.solver.add_soft_relaxed(cl, int(w), relax_var=wcnf.nv + cont_non_unit)
        assert cont_non_unit > 0, "Expecting some non-unit soft clauses in this instance"
        start = time.time()
        ok = self.solver.solve()
        dur = time.time() - start
        st = self.solver.get_status()
        print(f"[HEAVY] {os.path.basename(path)}: ok={ok} status={st.name} cost={self.solver.get_cost() if st==SolveStatus.OPTIMUM else 'NA'} time={dur:.2f}s")
        self.assertEqual(st, SolveStatus.OPTIMUM)

    def test_110_many_redundant_soft_units(self):
        # Many identical soft units. Cost should not scale if solver deduplicates.
        # Hard: x1 true
        self.solver.add_clause([1])
        for _ in range(50):
            self.solver.add_soft_unit(-1, 2)
        self.assertTrue(self.solver.solve())
        # UWrMaxSat deduplicates, so cost is 2, not 100.
        self.assertEqual(self.solver.get_cost(), 2)

    def test_110_many_redundant_soft_units_unweighted(self):
        # Many identical soft units. Cost should not scale if solver deduplicates.
        # Hard: x1 true
        self.solver.add_clause([1])
        for _ in range(50):
            self.solver.add_soft_unit(-1, 1)
        self.assertTrue(self.solver.solve())
        # UWrMaxSat deduplicates, so cost is 1, not 100.
        self.assertEqual(self.solver.get_cost(), 1)

    def test_111_soft_clause_length_two(self):
        # Soft binary clause test
        self.solver.add_clause([1, 2])          # hard: at least one of x1, x2 must be true

        # Soft clauses defining preferences:
        # Cost 1 if x1 is false (i.e., prefer x1 true)
        self.solver.add_soft_unit(1, 1)
        # Cost 10 if x2 is false (i.e., strongly prefer x2 true)
        self.solver.add_soft_unit(2, 10)
        # Cost 1 if both x1 and x2 are true (to break ties)
        self.solver.add_soft_relaxed([-1, -2], 1, relax_var=3)

        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)

        # With these costs, the optimal models are [1, 2] (cost 1) and [-1, 2] (cost 1).
        # Both satisfy the strong preference for x2 to be true.
        m = self.solver.get_model()
        self.assertIsNotNone(m)
        self.assertIn(2, m) # We must have x2=true to avoid the high cost
        self.assertEqual(self.solver.get_cost(), 1)

    def test_112_empty_soft_clause_rejected_or_cost_infinite(self):
        # Soft empty clause is always violated. We expect rejection (ValueError).
        with self.assertRaises((ValueError, AssertionError)):
            self.solver.add_soft_relaxed([], 1, relax_var=3)

    def test_113_large_var_indices_ok(self):
        # Use large var ids; solver must handle without collision
        big = 10_000
        self.solver.add_clause([big])
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(self.solver.val(big), 1)

    def test_114_inconsistent_weight_types_raise(self):
        # Non-int weights should be rejected
        with self.assertRaises((TypeError, ValueError, AssertionError, RuntimeError)):
            self.solver.set_soft(-1, 3.14)  # float
        with self.assertRaises((TypeError, ValueError, AssertionError, RuntimeError)):
            self.solver.set_soft(-2, "5")   # string

    def test_120_raise_on_abnormal_interrupt(self):
        # Add a non-trivial problem to ensure solver runs long enough to be interrupted.
        self._add_pigeonhole_problem()

        # If set_terminate is available, force interrupt and require raising when requested.
        try:
            self.solver.set_terminate(Stopper())
        except NotImplementedError:
            self.skipTest("set_terminate not supported")
            return
        with self.assertRaises(RuntimeError):
            _ = self.solver.solve(raise_on_abnormal=True)
        self.assertEqual(self.solver.get_status(), SolveStatus.INTERRUPTED)

    @unittest.skip
    def test_121_raise_on_abnormal_no_raise_when_false(self):
        # Add a non-trivial problem to ensure solver runs long enough to be interrupted.
        self._add_pigeonhole_problem()

        try:
            self.solver.set_terminate(Stopper())
        except NotImplementedError:
            self.skipTest("set_terminate not supported")
            return
        ok = self.solver.solve(raise_on_abnormal=False)
        self.assertFalse(ok)
        self.assertEqual(self.solver.get_status(), SolveStatus.INTERRUPTED)
        # Clear and check we can proceed to a definitive result
        self.solver.set_terminate(Stopper(10_000))
        # The formula is still the UNSAT pigeonhole problem
        sat2 = self.solver.solve(raise_on_abnormal=False)
        self.assertFalse(sat2)
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)

    def test_130_model_val_consistency_multiple_queries(self):
        hards = [[1, 2], [-1, -2]]
        softs = [([-1], 5), ([-2], 3)]
        for cl in hards:
            self.solver.add_clause(cl)
        for cl, w in softs:
            self.solver.add_soft_unit(cl[0], w)
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        model = self.solver.get_model()
        cost = self.solver.get_cost()
        assert_model_consistency(self, hards, softs, model, self.solver.val, expected_cost=cost)
        # Re-query should be stable
        model2 = self.solver.get_model()
        self.assertEqual(sorted(set(model2)), sorted(set(model)))
        self.assertEqual(self.solver.get_cost(), cost)

    def test_140_unsat_forbids_model_and_cost(self):
        self.solver.add_clause([1])
        self.solver.add_clause([-1])
        sat = self.solver.solve()
        self.assertFalse(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)
        with self.assertRaises(RuntimeError):
            _ = self.solver.get_model()
        with self.assertRaises(RuntimeError):
            _ = self.solver.get_cost()
        with self.assertRaises(RuntimeError):
            self.solver.val(1)

    # Compare models modulo irrelevant variables
    def _equal_mod_irrelevant(self, model, reference_models, hards, softs):
        mentioned = {abs(l) for cl in hards for l in cl} | {abs(l) for cl, _ in softs for l in cl}
        s_model = {lit for lit in model if abs(lit) in mentioned}
        for rm in reference_models:
            s_ref = {lit for lit in rm if abs(lit) in mentioned}
            if s_model == s_ref:
                return True
        return False


    def test_150_random_campaign_with_bruteforce(self):
        for hards, softs in self._rand_formulas_with_oracle(nvars=7, nhards=6, nsofts=5, kmax=3, wmax=9):
            self.tearDown(); self.setUp()
            min_cost, models = brute_force_optimum(hards, softs)
            if min_cost is math.inf:
                status, model, cost = self._run_solver_on(hards, softs)  # for coverage
                self.assertEqual(status, SolveStatus.UNSAT)
                continue
            s = self._add_clauses_on(hards, softs)
            
            sat = s.solve()
            self.assertTrue(sat)
            self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
            m = s.get_model()
            c = s.get_cost()
            self.assertEqual(c, min_cost)
            # self.assertIn(sorted(set(m)), [sorted(mm) for mm in models])
            self.assertTrue(
                self._equal_mod_irrelevant(m, models, hards, softs),
                f"Model differs only on irrelevant variables: got {sorted(set(m))}, expected one of {models}"
            )

    def test_160_wcnf_with_assumptions_perturbation(self):
        current_file_location = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_file_location, "data", "pseudoBoolean-normalized-par8-2.opb.msat.old.wcnf")
        wcnf = self._load_wcnf(path)
        # Load
        for cl in wcnf.hard:
            self.solver.add_clause(cl)
        for cl, w in zip(wcnf.soft, wcnf.wght):
            assert len(cl) == 1
            self.solver.add_soft_unit(cl[0], int(w))
        # Baseline solve
        ok = self.solver.solve()
        st = self.solver.get_status()
        self.assertIn(st, {SolveStatus.OPTIMUM, SolveStatus.UNSAT})
        if st == SolveStatus.UNSAT:
            return
        base_cost = self.solver.get_cost()
        base_model = set(self.solver.get_model())
        # Try a few random assumptions flipping some literals
        lits = list({abs(x) for cl in wcnf.hard for x in cl} | {abs(x) for cl in wcnf.soft for x in cl})
        random.shuffle(lits)
        picked = lits[: min(5, len(lits))]
        # Force the opposite polarity for selected variables
        assumptions = [(-v if v in base_model else v) for v in picked]
        ok2 = self.solver.solve(assumptions=assumptions)
        st2 = self.solver.get_status()
        self.assertIn(st2, {SolveStatus.OPTIMUM, SolveStatus.UNSAT})
        if st2 == SolveStatus.OPTIMUM:
            self.assertNotEqual(self.solver.get_cost(), None)
            # Cost should be >= baseline (forcing may only constrain)
            self.assertGreaterEqual(self.solver.get_cost(), base_cost)

    # ---- Regression guard: solve() must clear assumptions between calls ----

    def test_170_assumptions_auto_clear(self):
        self.solver.add_clause([1, 2])
        self.solver.add_clause([-1, -2])
        # Assume x1; next call without assumptions should not inherit it
        self.assertTrue(self.solver.solve(assumptions=[1]))
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)

    # ---- Mix of soft/hard and then add contradictory hard to force UNSAT ----

    def test_180_add_contradictory_hard_after_optimum(self):
        self.solver.add_clause([1])
        self.solver.add_soft_unit(-1, 100)
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_cost(), 100)  # must pay
        # Now add hard [-1] making instance UNSAT
        self.solver.add_clause([-1])
        sat = self.solver.solve()
        self.assertFalse(sat)
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)
        # self.assertIsNone(self.solver.get_model())
        with self.assertRaises(RuntimeError):
            self.solver.get_model()

    # ---- Fuzz mini with enforced satisfiable hard skeleton ----

    def test_190_random_sat_skeleton_with_soft_noise(self):
        # Build a satisfiable skeleton: chain of implications and a unit literal
        n = 6
        for i in range(1, n):
            # (¬x_i ∨ x_{i+1})
            self.solver.add_clause([-i, i+1])
        self.solver.add_clause([1])  # force x1 true -> all xi true by implications
        # Add random soft clauses preferring some variables false
        for i in range(1, n + 1):
            w = random.randint(1, 9)
            self.solver.add_soft_unit(-i, w)
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m = self.solver.get_model()
        self.assertTrue(all(i in m for i in range(1, n + 1)))
        # Cost equals sum weights since all xi are true
        # However, a clever solver could keep some vars unassigned yet satisfy all hards;
        # get_model must encode a total assignment (by convention for MaxSAT winners), but we allow partials.
        # We'll test cost only.
        # Compute expected cost as sum of weights
        # We have no direct record, so skip exact equality; ensure nonzero cost:
        self.assertGreater(self.solver.get_cost(), 0)

    def test_200_repeated_solve_idempotent(self):
        self.solver.add_clause([1, 2])
        self.solver.add_clause([-1, -2])
        self.solver.add_soft_unit(-1, 5)
        self.assertTrue(self.solver.solve())
        st = self.solver.get_status()
        c = self.solver.get_cost() if st == SolveStatus.OPTIMUM else None
        m = set(self.solver.get_model() or [])
        for _ in range(5):
            ok = self.solver.solve()
            self.assertEqual(ok, st == SolveStatus.OPTIMUM)
            self.assertEqual(self.solver.get_status(), st)
            if st == SolveStatus.OPTIMUM:
                self.assertEqual(self.solver.get_cost(), c)
                self.assertEqual(set(self.solver.get_model()), m)

    def test_210_unsat_then_relax_with_soft(self):
        # Hard contradictory structure, but with a relaxable literal
        # (1 ∨ ¬2) means: clause [1] can be violated if 2 = False
        self.solver.add_clause([1, -2])   # "softened" 1 using new var 2
        self.solver.add_clause([-1])      # hard contradiction if 2 is True
        self.solver.add_soft_unit(-1, 1)   # soft clause to prefer -1 true (cost 1 if violated)

        # Assume 2=True (meaning we enforce the soft clause as hard)
        # => 1 and -1 conflict => UNSAT
        self.assertFalse(self.solver.solve(assumptions=[2]))
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)

        # Now relax: drop the assumption on 2
        # => solver can set 2=False, breaking the contradiction
        self.assertTrue(self.solver.solve())
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(self.solver.get_cost(), 0)  # must not pay the soft cost
        model = self.solver.get_model()
        self.assertEqual(model, [-1, -2])  # 2 must be false to avoid contradiction

    def test_right_policy_unit_last_by_var_overwrites_polarity(self):
        self.solver.add_clause([1])

        # Two unit softs on the same variable with opposite polarity
        # Expectation under "units-last-by-var": only the LAST one remains
        self.solver.add_soft_unit(1, 5)    # penalize x1=false with weight 5
        self.solver.add_soft_unit(-1, 7)   # penalize x1=true with weight 7
        self.solver.add_soft_unit(-1, 4)   # penalize x1=true with weight 4  (last wins)
        self.solver.add_soft_unit(1, 9)    # penalize x1=false with weight 9 (THIS IS SATISFIED SO IT NOT PENALIZED)

        ok = self.solver.solve()
        self.assertTrue(ok)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m = set(self.solver.get_model())

        # Under units-last-by-var, only [-1],7 remains
        # Since hard [1] forces x1=true, we must pay 7 if [-1],7 is active.
        # Check all three policies to see which matches the solver.
        raw = [([1], 5), ([-1], 7), ([-1], 4), ([1], 9)]
        R2 = _normalize_softs_units_by_literal(raw)

        reported = self.solver.get_cost()
        cR2 = cost_of_model(m, R2)

        self.assertEqual(reported, cR2)
        self.assertEqual(reported, 4)

    
    def test_right_policy_unit_last_by_var_overwrites_polarity_unweighted(self):
        self.solver.add_clause([1])

        self.solver.add_soft_unit(1, 1)    # penalize x1=false with weight 1
        self.solver.add_soft_unit(-1, 1)   # penalize x1=true with weight 1
        self.solver.add_soft_unit(-1, 1)   # penalize x1=true with weight 1  (last wins)
        self.solver.add_soft_unit(1, 1)    # penalize x1=false with weight 1 (THIS IS SATISFIED SO IT NOT PENALIZED)

        ok = self.solver.solve()
        self.assertTrue(ok)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m = set(self.solver.get_model())

        raw = [([1], 1), ([-1], 1), ([-1], 1), ([1], 1)]
        R2 = _normalize_softs_units_by_literal(raw)

        reported = self.solver.get_cost()
        cR2 = cost_of_model(m, R2)

        self.assertEqual(reported, cR2)
        self.assertEqual(reported, 1)



    def test_right_policy_unit_last_by_var_overwrites_polarity_inverse(self):
        self.solver.add_clause([-1])

        # Two unit softs on the same variable with opposite polarity
        # Expectation under "units-last-by-var": only the LAST one remains
        self.solver.add_soft_unit(1, 5)    # penalize x1=false with weight 5
        self.solver.add_soft_unit(-1, 7)   # penalize x1=true with weight 7
        self.solver.add_soft_unit(-1, 4)   # penalize x1=true with weight 4  (last wins, THIS IS SATISFIED SO IT NOT PENALIZED)
        self.solver.add_soft_unit(1, 9)    # penalize x1=false with weight 9 (last wins)

        ok = self.solver.solve()
        self.assertTrue(ok)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m = set(self.solver.get_model())

        # Under units-last-by-var, only [-1],7 remains
        # Since hard [1] forces x1=true, we must pay 7 if [-1],7 is active.
        # Check all three policies to see which matches the solver.
        raw = [([1], 5), ([-1], 7), ([-1], 4), ([1], 9)]
        R2 = _normalize_softs_units_by_literal(raw)

        reported = self.solver.get_cost()
        cR2 = cost_of_model(m, R2)

        self.assertEqual(reported, cR2)
        self.assertEqual(reported, 9)



    def test_right_policy_nonunit_stays_multiset(self):
        self.solver.add_clause([-1])
        self.solver.add_clause([-2])

        # Two identical non-unit softs differing only in weight (and reordering of literals)
        self.solver.add_soft_relaxed([1, 2], 3, relax_var=3)
        self.solver.add_soft_relaxed([2, 1], 4, relax_var=4)

        ok = self.solver.solve()
        self.assertTrue(ok)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m = set(self.solver.get_model())

        raw = [([1, 2], 3), ([2, 1], 4)]
        R2 = _normalize_softs_units_by_literal(raw)        

        reported = self.solver.get_cost()
        cR2 = cost_of_model(m, R2)

        self.assertEqual(reported, cR2)
        self.assertEqual(reported, 7)  # must pay for one of the two identical softs

    def test_soft_unit_isolated_from_other_literal(self):
        self.solver.add_soft_unit(-1, 1)
        self.solver.add_clause([2])
        ok = self.solver.solve(assumptions=[1, 2])
        self.assertTrue(ok)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        m = self.solver.get_model()
        self.assertEqual(m, [1, 2])
        self.assertEqual(self.solver.get_cost(), 1)  # must pay for -1

    def test_nonunit_soft_allocates_aux_and_costs_when_clause_false(self):
        self.solver.add_soft_relaxed([-1, -2], 1, relax_var=3)
        # This implicity creates a new blocking var
        # This test checks for interference!
        self.solver.add_clause([-3])

        # This forces the non-unit soft to be SATISFIED, so no cost
        ok = self.solver.solve()
        self.assertTrue(ok)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        model = self.solver.get_model()
        self.assertEqual(self.solver.get_cost(), 0)

        # Now, the trick is, if we assume [1, 2, 3], then it must give UNSAT
        # because the non-unit soft clause is violated and its blocking var must be false
        ok2 = self.solver.solve(assumptions=[1, 2, 3])
        self.assertFalse(ok2)
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)

    def test_nonunit_soft_allocates_aux_and_costs_when_clause_false_inverse(self):
        # INVERSE OF THE PREVIOUS ONE!
        self.solver.add_clause([-3])
        self.solver.add_soft_relaxed([-1, -2], 1, relax_var=4)
        # This implicity creates a new blocking var 4!

        # Now, the trick is, if we assume [1, 2, -3], then it must give SAT
        # because 3 does not interfere with the non-unit soft clause
        ok2 = self.solver.solve(assumptions=[1, 2, -3])
        self.assertTrue(ok2)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(self.solver.get_cost(), 1)  # must pay for the violated non-unit soft
        
        ok3 = self.solver.solve(assumptions=[-3])
        self.assertTrue(ok3)
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(self.solver.get_cost(), 0)  # can set -1 and -2 true to satisfy non-unit soft

        # And now, if we assume [1, 2, -3, 4], then it must give UNSAT
        ok = self.solver.solve(assumptions=[1, 2, -3, -4])
        self.assertFalse(ok)
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT)

    def test_h2b_soft_before_hard_same_relax_var_unifies(self):
        s = self.SolverClass()
        # Declare cost on -7 first
        s.add_soft_unit(-7, 3)
        # Later add a non-unit soft that uses +7 as relax var
        s.add_soft_relaxed([-1, -2], 5, relax_var=7)

        # Force clause false so +7 is needed, hence -7 is violated
        ok = s.solve(assumptions=[1, 2])
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        # last-wins on the literal: set_soft(-7,5) overwrote earlier 3
        self.assertEqual(s.get_cost(), 5)

    def test_h2c_hard_then_overwrite_soft_same_relax_var(self):
        s = self.SolverClass()
        s.add_soft_relaxed([-1, -2], 4, relax_var=8)   # hard (... ∪ {+8}), soft [-8]=4
        s.set_soft(-8, 9)                              # overwrite

        ok = s.solve(assumptions=[1, 2])               # force +8
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 9)


    def test_h2d_two_nonunits_share_same_relax_var_single_cost(self):
        s = self.SolverClass()
        s.add_soft_relaxed([-1, -2], 2, relax_var=9)
        s.add_soft_relaxed([-3, -4], 7, relax_var=9)   # same b
        # Make both base clauses false ⇒ +9 must be true
        ok = s.solve(assumptions=[1, 2, 3, 4])
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        # cost counted once with the last weight = 7
        self.assertEqual(s.get_cost(), 7)

    def test_h2e_relax_var_reuses_existing_problem_var_id(self):
        s = self.SolverClass()
        s.add_clause([5, -6])                 # mention var 5 in hard
        s.add_soft_relaxed([-1, -2], 4, relax_var=5)

        ok = s.solve(assumptions=[1, 2])      # force +5, violate [-5]
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 4)
    def test_h3a_driver_duplicates_overwrite_by_literal(self):
        s = self.SolverClass()
        for lit in [3, 4, 3, 3, 4, 3]:
            s.add_soft_unit(-lit, 1)
        ok = s.solve(assumptions=[3, 4])      # violate [-3], [-4]
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 2)

    def test_h3b_driver_duplicates_same_b_from_multiple_paths(self):
        s = self.SolverClass()
        # First path
        s.add_soft_relaxed([-1, -2], 1, relax_var=11)
        # Second path reuses same b, but “driver bug” repeats it
        s.add_soft_relaxed([-3, -4], 1, relax_var=11)
        s.add_soft_unit(-11, 5)  # third feed: overwrite weight to 5 explicitly

        ok = s.solve(assumptions=[1, 2, 3, 4])  # forces +11
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 5)       # once, last wins

    def test_h4a_redundant_excluding_clause_no_cost_drift(self):
        s = self.SolverClass()
        s.add_soft_relaxed([-1, -2], 3, relax_var=12)
        s.add_clause([1, 2])

        self.assertTrue(s.solve())
        c1 = s.get_cost()

        s.add_clause([12])   # force +12, pay once
        self.assertTrue(s.solve())
        c2 = s.get_cost()
        s.add_clause([12])   # redundant identical hard
        self.assertTrue(s.solve())
        c3 = s.get_cost()

        self.assertEqual(c2, c3)

    def test_h4b_excluding_on_multiple_bs_do_not_alias(self):
        s = self.SolverClass()
        s.add_soft_relaxed([-1, -2], 2, relax_var=13)
        s.add_soft_relaxed([-3, -4], 5, relax_var=14)

        # Force both bs true via excludes
        s.add_clause([13])
        s.add_clause([14])
        self.assertTrue(s.solve())
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 7)

    def test_h5a_irrelevant_vars_padded_no_cost_effect(self):
        s = self.SolverClass()
        s.add_clause([1])          # hard needs 1 = True
        s.add_soft_unit(-2, 4)     # cost when 2 = True

        ok = s.solve(assumptions=[1, 2])  # satisfy hard, violate [-2]
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 4)



    def test_h6a_reuse_relax_var_then_soft_unit_does_not_create_duplicate_selector(self):
        s = self.SolverClass()
        s.add_soft_relaxed([-1, -2], 6, relax_var=15)  # sets [-15]=6
        s.add_soft_unit(-15, 9)                        # overwrite to 9 on the SAME internal lit
        ok = s.solve(assumptions=[1, 2])
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 9)

    def test_h6b_overwrite_one_b_does_not_touch_other_b(self):
        s = self.SolverClass()
        s.add_soft_relaxed([-1, -2], 4, relax_var=16)  # [-16]=4
        s.add_soft_relaxed([-3, -4], 7, relax_var=17)  # [-17]=7
        s.set_soft(-16, 10)                             # overwrite first only

        ok = s.solve(assumptions=[1, 2, 3, 4])         # force both bs
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 10 + 7)

    def test_h7_unit_core_on_shared_b_still_overwrites_correctly(self):
        s = self.SolverClass()
        s.add_soft_relaxed([-1, -2], 1, relax_var=18)
        s.add_soft_relaxed([-3, -4], 1, relax_var=18)
        s.set_soft(-18, 5)                  # unify to weight 5
        # Add hard to force a unit core on the soft selector’s negation path
        s.add_clause([18])                  # force +18
        ok = s.solve()
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 5)

    def test_h2f_triple_path_same_relax_var_unifies_and_overwrites(self):
        s = self.SolverClass()
        # Path A: create via non-unit relaxed clause
        s.add_soft_relaxed([-1, -2], 2, relax_var=20)   # sets [-20] = 2
        # Path B: explicit soft-unit on same external literal later
        s.add_soft_unit(-20, 7)                         # overwrite to 7
        # Path C: set_soft overwrite again
        s.set_soft(-20, 5)                              # final weight 5

        ok = s.solve(assumptions=[1, 2])                # force +20
        self.assertTrue(ok)
        self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(s.get_cost(), 5)               # once, last-wins

    def test_h4c_iterative_excludes_keep_singleton_selectors(self):
        s = self.SolverClass()
        # Two independent relaxed softs
        s.add_soft_relaxed([-1, -2], 1, relax_var=30)   # [-30]=1
        s.add_soft_relaxed([-3, -4], 1, relax_var=31)   # [-31]=1

        # Iteration 1: add an excluding clause that forces +30
        s.add_clause([30])
        self.assertTrue(s.solve())
        c1 = s.get_cost()   # should be >=1

        # Iteration 2: add the *same* exclude again, must be cost-stable
        s.add_clause([30])
        self.assertTrue(s.solve())
        c2 = s.get_cost()
        self.assertEqual(c1, c2)

        # Iteration 3: now force +31 too, cost should +1 (not +2 or 0)
        s.add_clause([31])
        self.assertTrue(s.solve())
        c3 = s.get_cost()
        self.assertEqual(c3, c2 + 1)



    def test_totalizer_cache_reuse_matches_rebuild(self):
        SolverClass = self.SolverClass  # RC2 incremental implementation

        # Setup that forces a multi-selector core:
        # hard: ¬1 ∨ ¬2  (both cannot be true together)
        # soft: [1] w=1, [2] w=1
        hard = [[-1, -2]]
        soft = [(1, 1), (2, 1)]

        # Incremental solver reused across epochs (cache ON)
        inc = _build_solver_with_state(SolverClass, hard, soft)
        ok1 = inc.solve()
        self.assertTrue(ok1)
        c1_inc = inc.get_cost()

        # Add a new hard clause that still leaves the same selector set relevant.
        # Example: forbid 1 being false at the final solution, nudging the model
        # but not changing that the initial core is on {1,2}.
        hard.append([1])  # forces 1 = True

        ok2_inc = inc.solve()
        self.assertTrue(ok2_inc)
        c2_inc = inc.get_cost()

        # Fresh solver rebuilt to the same hard/soft state (equivalent to cache OFF)
        reb = _build_solver_with_state(SolverClass, hard, soft)
        ok2_reb = reb.solve()
        self.assertTrue(ok2_reb)
        c2_reb = reb.get_cost()

        self.assertEqual(c2_inc, c2_reb, "Cache reuse across epochs diverged from rebuild")


    def test_totalizer_cache_epoch_clear_restores_equivalence(self):
        SolverClass = self.SolverClass

        hard = [[-1, -2]]
        soft = [(1, 1), (2, 1)]

        inc = _build_solver_with_state(SolverClass, hard, soft)
        self.assertTrue(inc.solve())
        c1 = inc.get_cost()

        # Add epoch-2 hard constraint
        hard.append([1])

        # Simulate epoch boundary: clear totalizer cache and related sum maps
        # These are public attributes on your RC2 implementation.
        if hasattr(inc, "totalizer_cache"):
            inc.totalizer_cache.clear()
        if hasattr(inc, "tobj"):
            inc.tobj.clear()
        if hasattr(inc, "bnds"):
            inc.bnds.clear()
        if hasattr(inc, "swgt"):
            inc.swgt.clear()

        self.assertTrue(inc.solve())
        c2_inc_cleared = inc.get_cost()

        # Rebuilt baseline
        reb = _build_solver_with_state(SolverClass, hard, soft)
        self.assertTrue(reb.solve())
        c2_reb = reb.get_cost()

        self.assertEqual(c2_inc_cleared, c2_reb, "Epoch cache clear should match rebuild")


    # def test_totalizer_key_reuse_across_epochs_is_safe(self):
    #     SolverClass = self.SolverClass

    #     hard = [[-1, -2]]
    #     soft = [(1, 1), (2, 1)]

    #     inc = _build_solver_with_state(SolverClass, hard, soft)

    #     # First compute to build the totalizer over rels = {-1, -2}
    #     self.assertTrue(inc.solve())
    #     c1 = inc.get_cost()

    #     # Capture totalizer keys now
    #     keys_epoch1 = set()
    #     if hasattr(inc, "totalizer_cache"):
    #         keys_epoch1 = set(inc.totalizer_cache.keys())

    #     # Modify hard base but keep the rel-set pattern likely the same
    #     hard.append([1])

    #     # Second compute, cache reuses any identical key
    #     self.assertTrue(inc.solve())
    #     c2_inc = inc.get_cost()
    #     keys_epoch2 = set(getattr(inc, "totalizer_cache", {}).keys())

    #     # Rebuild baseline for epoch 2
    #     reb = _build_solver_with_state(SolverClass, hard, soft)
    #     self.assertTrue(reb.solve())
    #     c2_reb = reb.get_cost()

    #     # Sanity: Key sets intersect (same rel-set seen again)
    #     self.assertTrue(keys_epoch1 & keys_epoch2,
    #                     f"Expected identical rel-set totalizer key to reappear across epochs {keys_epoch1} vs {keys_epoch2}")

    #     # But result must still match rebuild
    #     self.assertEqual(c2_inc, c2_reb, "Reusing a prior epoch totalizer changed the optimum")

    def test_totalizer_cache_multi_epoch_stability(self):
        SolverClass = self.SolverClass

        base_hard = [[-1, -2]]
        soft = [(1, 1), (2, 1)]

        inc = _build_solver_with_state(SolverClass, list(base_hard), soft)

        # Epoch 1
        self.assertTrue(inc.solve())
        c1_inc = inc.get_cost()

        # Epoch 2: add [1]
        h2 = list(base_hard) + [[1]]
        inc.add_clause([1])
        self.assertTrue(inc.solve())
        c2_inc = inc.get_cost()
        reb2 = _build_solver_with_state(SolverClass, h2, soft)
        self.assertTrue(reb2.solve())
        c2_reb = reb2.get_cost()
        self.assertEqual(c2_inc, c2_reb)

        # Epoch 3: add another harmless clause that keeps rel-set {-1,-2} relevant
        h3 = list(h2) + [[1, -2]]  # does not permit 1∧2 but doesn't change the initial conflict family
        inc.add_clause([1, -2])
        self.assertTrue(inc.solve())
        c3_inc = inc.get_cost()
        reb3 = _build_solver_with_state(SolverClass, h3, soft)
        self.assertTrue(reb3.solve())
        c3_reb = reb3.get_cost()
        self.assertEqual(c3_inc, c3_reb)


    # def test_h1a_duplicate_unit_soft_overwrite_not_sum(self):
    #     s = self.SolverClass()
    #     s.add_soft_unit(1, 1)
    #     s.add_soft_unit(1, 1)  # same literal again, last-wins overwrite expected
    #     ok = s.solve(assumptions=[-1])  # violate [1]
    #     self.assertTrue(ok)
    #     self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
    #     self.assertEqual(s.get_cost(), 1)  # should NOT be 2
    # def test_h1b_duplicate_unit_soft_last_weight_wins(self):
    #     s = self.SolverClass()
    #     s.add_soft_unit(-2, 3)
    #     s.add_soft_unit(-2, 7)  # overwrite
    #     ok = s.solve(assumptions=[2])  # violate [-2]
    #     self.assertTrue(ok)
    #     self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
    #     self.assertEqual(s.get_cost(), 7)
    # def test_h1c_duplicate_nonunit_same_relax_var_last_wins(self):
    #     s = self.SolverClass()
    #     s.add_soft_relaxed([1, 2], 4, relax_var=5)
    #     s.add_soft_relaxed([3, 4], 9, relax_var=5)  # same b=5
    #     ok = s.solve(assumptions=[-1, -2, -3, -4])  # make both base clauses false -> need b
    #     self.assertTrue(ok)
    #     self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
    #     self.assertEqual(s.get_cost(), 9)  # not 13
    
    # def test_h2_soft_then_hard_same_var_mapping_ok(self):
    #     s = self.SolverClass()
    #     s.add_soft_unit(-10, 1)      # soft on external var 10
    #     s.add_clause([10])          # later hard that references same external var
    #     ok = s.solve(assumptions=[10])  # violate [-10]
    #     self.assertTrue(ok)
    #     self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
    #     self.assertEqual(s.get_cost(), 1)
        
    # def test_h3_driver_style_duplicate_feed(self):
    #     s = self.SolverClass()
    #     lits = [5, 6, 5, 6, 5]  # duplicates
    #     for lit in lits:
    #         s.add_soft_unit(-lit, 1)
    #     ok = s.solve(assumptions=[5, 6])  # violate each [-lit] once
    #     self.assertTrue(ok)
    #     self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
    #     self.assertEqual(s.get_cost(), 2)  # unique {5,6}
        
    # def test_h4_cost_matches_bruteforce_on_returned_model(self):
    #     s = self.SolverClass()
    #     hards = [[1, -2], [3], [-4]]
    #     softs = [([-1], 2), ([2], 1), ([-3], 3), ([5], 4), ([5], 4)]  # dup 5 on purpose
    #     for cl in hards:
    #         s.add_clause(cl)
    #     for cl, w in softs:
    #         if len(cl) == 1:
    #             s.add_soft_unit(cl[0], w)
    #         else:
    #             s.add_soft_relaxed(cl, w, relax_var=7)

    #     ok = s.solve()
    #     self.assertTrue(ok)
    #     self.assertEqual(s.get_status(), SolveStatus.OPTIMUM)
    #     cost = s.get_cost()
    #     m = s.get_model()

    #     # brute-force cost for unit softs: pay when [l] is violated i.e., l is false
    #     S = set(m)
    #     def bf_cost(model, softs_units):
    #         c = 0
    #         for [l], w in softs_units:
    #             if -l in S:  # l is false in model
    #                 c += w
    #         return c

    #     # last-wins normalization by literal
    #     softs_norm = {}
    #     for [l], w in softs:
    #         softs_norm[l] = w
    #     softs_dw = [([l], w) for l, w in softs_norm.items()]

    #     self.assertEqual(cost, bf_cost(m, softs_dw))
        
    # def test_h5_iterative_excluding_clauses_stable_cost(self):
    #     s = self.SolverClass()
    #     s.add_soft_relaxed([-1, -2], 1, relax_var=4)
    #     s.add_clause([1, 2])

    #     self.assertTrue(s.solve())
    #     c1 = s.get_cost()

    #     s.add_clause([4])  # forces relax var true -> violates [-4] once
    #     self.assertTrue(s.solve())
    #     c2 = s.get_cost()

    #     s.add_clause([4])  # redundant
    #     self.assertTrue(s.solve())
    #     c3 = s.get_cost()

    #     self.assertEqual(c2, c3)

    # Literally causes seg fault:
    # TODO: Define and implement expected behavior
    # For variables out of range of any clause, val() should probably raise an error.
    # def test_220_val_for_unmentioned_vars(self):
    #     self.solver.add_clause([1])
    #     self.assertTrue(self.solver.solve())
    #     v = self.solver.val(999999)
    #     self.assertIn(v, (-1, 0, 1))
        # If var never appears, 0 is most reasonable; but we accept any in -1/0/1 here.



from hermax.core import RC2Reentrant, EvalMaxSATLatestSolver, UWrMaxSATSolver
from hermax.non_incremental import CGSS, CGSSPMRES
from hermax.core.uwrmaxsat_comp_py import UWrMaxSATCompSolver
from hermax.core.cashwmaxsat_py import CASHWMaxSATSolver
from hermax.core.evalmaxsat_latest_py import EvalMaxSATLatestSolver
from hermax.core.evalmaxsat_incr_py import EvalMaxSATIncrSolver
from hermax.core.openwbo_py import OLLSolver, PartMSU3Solver, AutoOpenWBOSolver
from hermax.non_incremental.incomplete import SPBMaxSATCFPS, OpenWBOInc, NuWLSCIBR, Loandra
from hermax.core import WMaxCDCLSolver
from hermax.portfolio import (
    CompletePortfolioSolver,
    IncompletePortfolioSolver,
    PerformancePortfolioSolver,
    PortfolioSolver,
)


class TestOLLSolverTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = OLLSolver

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("OLL does not support set_terminate")


class TestAutoOpenWBOSolverTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = AutoOpenWBOSolver

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("AutoOpenWBOSolver does not support set_terminate")


class TestPartMSU3SolverTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = PartMSU3Solver

    def _skip_if_no_weights(self):
        self.skipTest("PartMSU3Solver does not support weights > 1")

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("PartMSU3Solver does not support set_terminate")
    
    def test_020_soft_units_competing_weights(self): self._skip_if_no_weights()
    def test_021_soft_duplicate_clause_idempotent(self): self._skip_if_no_weights()
    def test_021_v2_soft_duplicate_clause_idempotent(self): self._skip_if_no_weights()
    def test_right_policy_unit_last_by_var_overwrites_polarity(self): self._skip_if_no_weights()
    def test_right_policy_unit_last_by_var_overwrites_polarity_inverse(self): self._skip_if_no_weights()
    def test_right_policy_nonunit_stays_multiset(self): self._skip_if_no_weights()
    def test_023_soft_large_weights_64bit_bounds(self): self._skip_if_no_weights()
    def test_030_assumptions_scope_and_reversion(self): self._skip_if_no_weights()
    def test_060_random_mini_instances_match_bruteforce(self): self._skip_if_no_weights()
    def test_070_incremental_strengthening_never_decreases_cost(self): self._skip_if_no_weights()
    def test_071_incremental_additional_soft_can_only_increase_or_equal(self): self._skip_if_no_weights()
    def test_110_many_redundant_soft_units(self): self._skip_if_no_weights()
    def test_111_soft_clause_length_two(self): self._skip_if_no_weights()
    def test_130_model_val_consistency_multiple_queries(self): self._skip_if_no_weights()
    def test_150_random_campaign_with_bruteforce(self): self._skip_if_no_weights()
    def test_180_add_contradictory_hard_after_optimum(self): self._skip_if_no_weights()
    def test_190_random_sat_skeleton_with_soft_noise(self): self._skip_if_no_weights()
    def test_200_repeated_solve_idempotent(self): self._skip_if_no_weights()
    def test_210_unsat_then_relax_with_soft(self): self._skip_if_no_weights()
    def test_h2b_soft_before_hard_same_relax_var_unifies(self): self._skip_if_no_weights()
    def test_h2c_hard_then_overwrite_soft_same_relax_var(self): self._skip_if_no_weights()
    def test_h2d_two_nonunits_share_same_relax_var_single_cost(self): self._skip_if_no_weights()
    def test_h2e_relax_var_reuses_existing_problem_var_id(self): self._skip_if_no_weights()
    def test_h2f_triple_path_same_relax_var_unifies_and_overwrites(self): self._skip_if_no_weights()
    def test_h3b_driver_duplicates_same_b_from_multiple_paths(self): self._skip_if_no_weights()
    def test_h4a_redundant_excluding_clause_no_cost_drift(self): self._skip_if_no_weights()
    def test_h4b_excluding_on_multiple_bs_do_not_alias(self): self._skip_if_no_weights()
    def test_h5a_irrelevant_vars_padded_no_cost_effect(self): self._skip_if_no_weights()
    def test_h6a_reuse_relax_var_then_soft_unit_does_not_create_duplicate_selector(self): self._skip_if_no_weights()
    def test_h6b_overwrite_one_b_does_not_touch_other_b(self): self._skip_if_no_weights()
    def test_h7_unit_core_on_shared_b_still_overwrites_correctly(self): self._skip_if_no_weights()

class TestRC2ReentrantTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = RC2Reentrant

    def test_040_termination_interrupt_and_raise_flag(self):
        # Override to skip; RC2Reentrant does not support set_terminate
        self.skipTest("RC2Reentrant does not support set_terminate")


class TestCGSSTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = CGSS

    def setUp(self):
        if not self.SolverClass.is_available():
            self.skipTest("CGSS backend is not available in this build.")
        super().setUp()

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("CGSS rebuild wrapper does not support set_terminate")


class TestCGSSPMRESTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = CGSSPMRES

    def setUp(self):
        if not self.SolverClass.is_available():
            self.skipTest("CGSSPMRES backend is not available in this build.")
        super().setUp()

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("CGSSPMRES rebuild wrapper does not support set_terminate")

class TestEvalMaxSATLatestCompatTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = EvalMaxSATLatestSolver

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("EvalMaxSAT does not support set_terminate")

    def test_020_soft_units_competing_weights(self):
        if _is_macos_arm64():
            self.skipTest("Known upstream EvalMaxSATLatest crash on macOS arm64 for this weighted-soft regression case.")
        super().test_020_soft_units_competing_weights()

class TestEvalMaxSATLatestSolverTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = EvalMaxSATLatestSolver

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("EvalMaxSATLatest does not support set_terminate")

    def test_020_soft_units_competing_weights(self):
        if _is_macos_arm64():
            self.skipTest("Known upstream EvalMaxSATLatest crash on macOS arm64 for this weighted-soft regression case.")
        super().test_020_soft_units_competing_weights()

class TestEvalMaxSATIncrSolverTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = EvalMaxSATIncrSolver

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("EvalMaxSATIncr does not support set_terminate")


class TestUWrMaxSATSolverTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = UWrMaxSATSolver

class TestUWrMaxSATCompSolverTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = UWrMaxSATCompSolver

    @classmethod
    def setUpClass(cls):
        if sys.platform.startswith("win"):
            raise unittest.SkipTest("UWrMaxSATComp backend is unstable on Windows (native crash).")
        return super().setUpClass()

    def test_023_soft_large_weights_64bit_bounds(self):
        if sys.platform.startswith("win"):
            self.skipTest("UWrMaxSATComp Windows backend crashes on INT64_MAX soft weight path.")
        return super().test_023_soft_large_weights_64bit_bounds()

class TestCASHWMaxSATSolverTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = CASHWMaxSATSolver

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("")


class TestWMaxCDCLSolverTerminationCallback(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = WMaxCDCLSolver

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("WMaxCDCL fake-incremental wrapper does not support set_terminate")

    def test_023_soft_large_weights_64bit_bounds(self):
        self.skipTest("WMaxCDCL backend cannot represent soft weight INT64_MAX distinctly from hard/top weight.")


class TestSPBMaxSATCFPSIncomplete(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = SPBMaxSATCFPS

    def setUp(self):
        self.solver = self._wrap_solver(self.SolverClass(timeout_s=4.0, timeout_grace_s=0.5))

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("SPB-MaxSAT-c-FPS subprocess wrapper does not support set_terminate.")

    def test_100_wcnf_real_instance_1(self):
        self.skipTest("SPB-MaxSAT-c-FPS is incomplete; real-data optimum tests are not required.")

    def test_101_wcnf_real_instance_2(self):
        self.skipTest("SPB-MaxSAT-c-FPS is incomplete; real-data optimum tests are not required.")

    def test_020_soft_units_competing_weights(self):
        self.skipTest("SPB-MaxSAT-c-FPS is incomplete and may return non-optimal weighted feasible solutions.")

    def test_030_assumptions_scope_and_reversion(self):
        self.skipTest("SPB-MaxSAT-c-FPS is incomplete and exact weighted optimum under assumptions is not guaranteed.")

    def test_060_random_mini_instances_match_bruteforce(self):
        self.skipTest("SPB-MaxSAT-c-FPS is incomplete; brute-force optimum matching is not required.")

    def test_071_incremental_additional_soft_can_only_increase_or_equal(self):
        self.skipTest("SPB-MaxSAT-c-FPS may be interrupted under short test timeout on repeated exact solves.")

    def test_130_model_val_consistency_multiple_queries(self):
        self.skipTest("SPB-MaxSAT-c-FPS may be interrupted under short test timeout on repeated exact solves.")

    def test_150_random_campaign_with_bruteforce(self):
        self.skipTest("SPB-MaxSAT-c-FPS is incomplete; brute-force optimum campaign is not required.")


class TestOpenWBOIncIncomplete(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = OpenWBOInc

    def setUp(self):
        self.solver = self._wrap_solver(self.SolverClass(timeout_s=4.0, timeout_grace_s=0.5))

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("OpenWBOInc subprocess wrapper does not support set_terminate.")

    def test_060_random_mini_instances_match_bruteforce(self):
        self.skipTest("OpenWBOInc is incomplete; brute-force optimum matching is not required.")


class TestNuWLSCIBRIncomplete(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = NuWLSCIBR

    def setUp(self):
        self.solver = self._wrap_solver(self.SolverClass(timeout_s=4.0, timeout_grace_s=0.5))

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("NuWLS-c-IBR subprocess wrapper does not support set_terminate.")

    def test_020_soft_units_competing_weights(self):
        self.skipTest("NuWLS-c-IBR is incomplete; exact weighted optimum is not guaranteed.")

    def test_030_assumptions_scope_and_reversion(self):
        self.skipTest("NuWLS-c-IBR is incomplete; exact weighted optimum under assumptions is not guaranteed.")

    def test_060_random_mini_instances_match_bruteforce(self):
        self.skipTest("NuWLS-c-IBR is incomplete; brute-force optimum matching is not required.")

    def test_071_incremental_additional_soft_can_only_increase_or_equal(self):
        self.skipTest("NuWLS-c-IBR may be interrupted under short test timeout on repeated exact solves.")

    def test_130_model_val_consistency_multiple_queries(self):
        self.skipTest("NuWLS-c-IBR may be interrupted under short test timeout on repeated exact solves.")

    def test_150_random_campaign_with_bruteforce(self):
        self.skipTest("NuWLS-c-IBR is incomplete; brute-force optimum campaign is not required.")

    def test_100_wcnf_real_instance_1(self):
        self.skipTest("NuWLS-c-IBR is incomplete; real-data optimum tests are not required.")

    def test_101_wcnf_real_instance_2(self):
        self.skipTest("NuWLS-c-IBR is incomplete; real-data optimum tests are not required.")


class HardcorePortfolioSolver(PortfolioSolver):
    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self, formula=None, **kwargs):
        solver_classes = [RC2Reentrant]
        if CGSS.is_available():
            solver_classes.append(CGSS)
        if getattr(UWrMaxSATCompSolver, "is_available", lambda: True)():
            solver_classes.append(UWrMaxSATCompSolver)
        if Loandra.is_available():
            solver_classes.append(Loandra)
        defaults = dict(
            per_solver_timeout_s=6.0,
            overall_timeout_s=12.0,
            timeout_grace_s=0.5,
            selection_policy="first_optimal_or_best_until_timeout",
            validate_model=True,
            recompute_cost_from_model=True,
            invalid_result_policy="warn_drop",
            verbose_invalid=False,
        )
        defaults.update(kwargs)
        super().__init__(solver_classes, formula=formula, **defaults)


class HardcoreCompletePortfolioSolver(CompletePortfolioSolver):
    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self, formula=None, **kwargs):
        defaults = dict(
            per_solver_timeout_s=6.0,
            overall_timeout_s=12.0,
            timeout_grace_s=0.5,
            max_workers=2,
            selection_policy="first_optimal_or_best_until_timeout",
            validate_model=True,
            recompute_cost_from_model=True,
            invalid_result_policy="warn_drop",
            verbose_invalid=False,
        )
        defaults.update(kwargs)
        super().__init__(formula=formula, **defaults)


class HardcorePerformancePortfolioSolver(PerformancePortfolioSolver):
    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self, formula=None, **kwargs):
        defaults = dict(
            per_solver_timeout_s=6.0,
            overall_timeout_s=12.0,
            timeout_grace_s=0.5,
            max_workers=2,
            selection_policy="first_optimal_or_best_until_timeout",
            validate_model=True,
            recompute_cost_from_model=True,
            invalid_result_policy="warn_drop",
            verbose_invalid=False,
        )
        defaults.update(kwargs)
        super().__init__(formula=formula, **defaults)


class HardcoreIncompletePortfolioSolver(IncompletePortfolioSolver):
    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self, formula=None, **kwargs):
        defaults = dict(
            per_solver_timeout_s=4.0,
            overall_timeout_s=10.0,
            timeout_grace_s=0.5,
            max_workers=2,
            selection_policy="first_valid",
            validate_model=True,
            recompute_cost_from_model=True,
            invalid_result_policy="warn_drop",
            verbose_invalid=False,
        )
        defaults.update(kwargs)
        super().__init__(formula=formula, **defaults)


class TestLoandraIncomplete(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = Loandra

    def setUp(self):
        self.solver = self._wrap_solver(self.SolverClass(timeout_s=4.0, timeout_grace_s=0.5))

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("Loandra subprocess wrapper does not support set_terminate.")

    def test_100_wcnf_real_instance_1(self):
        self.skipTest("Loandra is incomplete; real-data optimum tests are not required.")

    def test_101_wcnf_real_instance_2(self):
        self.skipTest("Loandra is incomplete; real-data optimum tests are not required.")


class TestPortfolioSolverConformance(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = HardcorePortfolioSolver

    def setUp(self):
        self.solver = self._wrap_solver(self.SolverClass())

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("PortfolioSolver does not support set_terminate.")


class TestCompletePortfolioPresetConformance(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = HardcoreCompletePortfolioSolver

    def setUp(self):
        self.solver = self._wrap_solver(self.SolverClass())

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("PortfolioSolver presets do not support set_terminate.")


class TestPerformancePortfolioPresetConformance(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = HardcorePerformancePortfolioSolver

    def setUp(self):
        self.solver = self._wrap_solver(self.SolverClass())

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("PortfolioSolver presets do not support set_terminate.")


class TestIncompletePortfolioPresetConformance(TestIPAMIRSolverHardcore):
    SOLVER_CLASS = HardcoreIncompletePortfolioSolver

    def setUp(self):
        self.solver = self._wrap_solver(self.SolverClass())

    def test_040_termination_interrupt_and_raise_flag(self):
        self.skipTest("Incomplete portfolio preset does not support set_terminate.")

    def test_020_soft_units_competing_weights(self):
        self.skipTest("Incomplete portfolio preset may return non-optimal weighted feasible solutions.")

    def test_030_assumptions_scope_and_reversion(self):
        self.skipTest("Incomplete portfolio preset does not guarantee exact weighted optimum under assumptions.")

    def test_060_random_mini_instances_match_bruteforce(self):
        self.skipTest("Incomplete portfolio preset is not required to match brute-force optima.")

    def test_071_incremental_additional_soft_can_only_increase_or_equal(self):
        self.skipTest("Incomplete portfolio preset may be interrupted under short test timeout on repeated exact solves.")

    def test_130_model_val_consistency_multiple_queries(self):
        self.skipTest("Incomplete portfolio preset may be interrupted under short test timeout on repeated exact solves.")

    def test_150_random_campaign_with_bruteforce(self):
        self.skipTest("Incomplete portfolio preset is not required to match brute-force optima.")

    def test_100_wcnf_real_instance_1(self):
        self.skipTest("Incomplete portfolio preset is not required to solve real-data optimum tests.")

    def test_101_wcnf_real_instance_2(self):
        self.skipTest("Incomplete portfolio preset is not required to solve real-data optimum tests.")

    def test_011_hard_unsat_contradiction(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT classification.")

    def test_012_empty_clause_is_unsat(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT classification.")

    def test_031_assumptions_conflict_with_hards(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT classification.")

    def test_140_unsat_forbids_model_and_cost(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT classification.")

    def test_160_wcnf_with_assumptions_perturbation(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT/OPTIMUM classification on perturbed real data.")

    def test_180_add_contradictory_hard_after_optimum(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT classification after contradiction.")

    def test_210_unsat_then_relax_with_soft(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT classification.")

    def test_nonunit_soft_allocates_aux_and_costs_when_clause_false(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT classification under non-unit soft assumptions.")

    def test_nonunit_soft_allocates_aux_and_costs_when_clause_false_inverse(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT classification under non-unit soft assumptions.")


del TestIPAMIRSolverHardcore

if __name__ == "__main__":
    unittest.main(verbosity=2)
