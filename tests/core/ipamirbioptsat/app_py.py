#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python translation of the bi-objective IPAMIR+IPASIR app.

Original C++ sources:
- ipamirbioptsat.cpp  :contentReference[oaicite:0]{index=0}
- totalizer.hpp / totalizer.cpp  :contentReference[oaicite:1]{index=1} :contentReference[oaicite:2]{index=2}

Format of the input file (as in the original):
- Lines starting with 'h' are hard clauses:       "h <lit> <lit> ... 0"
- Lines starting with '1' belong to objective #1:  "1 <weight> <lit> 0"
  These are modeled as soft LITERALS for the MaxSAT solver (increasing objective).
- Lines starting with '2' belong to objective #2:  "2 <weight> <lit> 0"
  These are counted in the SAT side (decreasing objective).

Behavior:
- Solve MaxSAT (IPAMIR) to optimal w.r.t. objective #1.
- Fix that objective’s value (via a totalizer + SAT assumptions).
- Improve objective #2 with a SAT–UNSAT search (tighten an at-most bound using a totalizer).
- Record a Pareto point. Forbid equal-or-worse #2 on the MaxSAT side by adding a hard clause.
- Repeat until the MaxSAT call becomes UNSAT or the decreasing objective reaches 0.

Requires:
- Your Python IPAMIR solver that implements the given interface (solve/val/get_cost/etc.).
- PySAT for the SAT side: `pip install python-sat[pblib,aiger]`
"""

from __future__ import annotations

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Iterable, Set, Dict, Callable, Type

# --- Load the IPAMIR interface and a concrete solver class ---
# Your interface (with SolveStatus, IPAMIRSolver, etc.)
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus

# SAT side uses PySAT
from pysat.solvers import Solver



# --------- Utility to dynamically load the IPAMIR solver class ----------
def _load_ipamir_solver_class() -> type:
    # spec = os.environ.get("IPAMIR_SOLVER", "rc2_reentrant:RC2Reentrant")
    spec = os.environ.get("IPAMIR_SOLVER", "urmaxsat_solver:UWrMaxSATSolver")
    
    # fallbacks allowed: urmaxsat_solver:UWrMaxSATSolver
    tried = []
    def load(spec_str: str):
        mod_name, cls_name = spec_str.split(":")
        import importlib
        mod = importlib.import_module(mod_name)
        return getattr(mod, cls_name)

    try:
        return load(spec)
    except Exception as e:
        tried.append((spec, str(e)))
        for fallback in ("urmaxsat_solver:UWrMaxSATSolver",):
            try:
                return load(fallback)
            except Exception as e2:
                tried.append((fallback, str(e2)))
        msg = "Failed to import any IPAMIR solver class:\n" + "\n".join(f"  {s}: {err}" for s, err in tried)
        raise ImportError(msg)


# --------- Totalizer encoding translated from totalizer.hpp/.cpp ----------
@dataclass
class VarCounter:
    n: int  # 1-based var ids; this counter will be incremented to allocate new vars
from pysat.card import ITotalizer
def _max_var(clauses: List[List[int]], lits: List[int]) -> int:
    m = 0
    for c in clauses:
        for lit in c:
            v = abs(lit)
            if v > m:
                m = v
    for lit in lits:
        v = abs(lit)
        if v > m:
            m = v
    return m

class Totalizer:
    """
    Wrapper around pysat.card.ITotalizer preserving:
    - out_lits[k] ≡ "at least k+1 inputs are true"
    - enforce AtMost B with unit [-out_lits[B]]
    """

    def __init__(self, solver_sat, solver_ipamir, mode: str, vcounter):
        assert mode in ("SAT", "MAXSAT")
        self.mode = mode
        self.sat = solver_sat
        self.maxsat = solver_ipamir
        self.vc = vcounter

        self.upper: int = 0
        self.out_lits: List[int] = []
        self._t: Optional[ITotalizer] = None
        self._n_inputs: int = 0

    # ---- public API ----
    def build(self, in_lits: List[int], upper: int) -> None:
        assert len(in_lits) >= 1
        self._n_inputs = len(in_lits)
        self.upper = min(upper, self._n_inputs - 1)

        # Build with current top to keep numbering consistent with the rest of your CNF
        self._t = ITotalizer(lits=list(in_lits), ubound=self.upper, top_id=int(self.vc.n))

        # Emit base clauses
        self._emit_many(self._t.cnf.clauses)

        # Start with currently available rhs
        self.out_lits = list(self._t.rhs)

        # Keep VarCounter in sync
        self.vc.n = max(self.vc.n, _max_var(self._t.cnf.clauses, self.out_lits))

    def update_upper(self, upper: int) -> None:
        """Increase the at-most bound. No shrink."""
        if self._t is None:
            return
        if upper <= self.upper:
            return
        target = min(upper, self._n_inputs - 1)

        self._t.increase(ubound=target, top_id=self.vc.n)
        if getattr(self._t, "nof_new", 0) > 0:
            self._emit_many(self._t.cnf.clauses[-self._t.nof_new:])

        self.out_lits = list(self._t.rhs)
        self.upper = target
        self.vc.n = max(self.vc.n, _max_var(self._t.cnf.clauses, self.out_lits))

    def get_out_lit(self, bound: int) -> int:
        """
        Provide an out literal for any 0 <= bound < n_inputs.
        Auto-grows the totalizer if bound exceeds current rhs length.
        """
        assert 0 <= bound < self._n_inputs, "bound out of range w.r.t. inputs"
        if self._t is None:
            raise RuntimeError("build() first")

        if bound >= len(self.out_lits):
            # Grow rhs to include this index
            self._t.increase(ubound=bound, top_id=self.vc.n)
            if getattr(self._t, "nof_new", 0) > 0:
                self._emit_many(self._t.cnf.clauses[-self._t.nof_new:])
            self.out_lits = list(self._t.rhs)
            self.vc.n = max(self.vc.n, _max_var(self._t.cnf.clauses, self.out_lits))

        return self.out_lits[bound]

    # ---- internal ----
    def _emit_many(self, clauses: List[List[int]]) -> None:
        if self.mode == "SAT":
            assert self.sat is not None
            for c in clauses:
                self.sat.add_clause(c)
        else:
            assert self.maxsat is not None
            for c in clauses:
                self.maxsat.add_clause(c)

# --------- Parser and algorithm (translated from ipamirbioptsat.cpp) ---------
def _parse_bicnf(path: str,
                 inc_solver: IPAMIRSolver,
                 sat_solver: Solver) -> Tuple[int, List[int], List[int]]:
    """
    Reads the custom bicnf-like file:
      h <lits...> 0
      1 <w> <lit> 0
      2 <w> <lit> 0

    Returns:
      n_vars, increasing_literals_repeated_by_weight, decreasing_literals_repeated_by_weight
    """
    n_vars = 0
    increasing: List[int] = []
    decreasing: List[int] = []

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line[0] == 'c':
                continue
            toks = line.split()
            tag = toks[0]
            if tag == 'h':
                # collect until 0 terminator
                lits: List[int] = []
                for t in toks[1:]:
                    v = int(t)
                    if v == 0:
                        break
                    n_vars = max(n_vars, abs(v))
                    lits.append(v)
                # add to both solvers
                if lits:
                    inc_solver.add_clause(lits)
                    sat_solver.add_clause(lits)
                else:
                    # empty hard clause => UNSAT
                    inc_solver.add_clause([])
                    sat_solver.add_clause([1, -1])  # force UNSAT via contradiction
            elif tag == '1':
                # format: 1 w lit 0
                if len(toks) != 4 or toks[-1] != '0':
                    raise ValueError(f"Bad line: {line}")
                w = int(toks[1])
                l = int(toks[2])
                n_vars = max(n_vars, abs(l))
                # normalized soft literal [-l] with weight w
                inc_solver.add_soft_unit(-l, w)
                # expand for counting in SAT-side totalizers
                increasing.extend([l] * w)
            elif tag == '2':
                # format: 2 w lit 0
                if len(toks) != 4 or toks[-1] != '0':
                    raise ValueError(f"Bad line: {line}")
                w = int(toks[1])
                l = int(toks[2])
                n_vars = max(n_vars, abs(l))
                decreasing.extend([l] * w)
            else:
                print("c ERROR: Encountered unexpected line", file=sys.stderr)
                raise ValueError(f"Unknown line tag: {tag}")
    return n_vars, increasing, decreasing


def _count_true(model_set: Set[int], lits: Iterable[int]) -> int:
    return sum(1 for l in lits if l in model_set)


def bioptsat(inc_solver: IPAMIRSolver,
             sat_solver: Solver,
             n_vars: int,
             increasing: List[int],
             decreasing: List[int]) -> bool:
    """
    Port of bioptsat(...) from C++ to Python.  :contentReference[oaicite:5]{index=5}
    """
    inc_tot: Optional[Totalizer] = None
    dec_bound_tot: Optional[Totalizer] = None
    dec_opt_tot: Optional[Totalizer] = None

    n_inc_vars = n_vars
    n_dec_vars = n_vars

    while True:
        # Increasing objective: solve MaxSAT
        print('c Incremental call')
        ok = inc_solver.solve()
        print('c Incremental call done')
        st = inc_solver.get_status()
        # print('a')
        if st == SolveStatus.UNSAT:
            print("c INFO: there are no more pareto-optimal solutions (incSolver call UNSAT)")
            return True
        if st not in (SolveStatus.OPTIMUM, SolveStatus.INTERRUPTED_SAT):
            print("c ERROR: increasing objective call should always get UNSAT or OPTIMAL")
            return False
        
        # print('b')
        # IPAMIR obj value = sum of weights of soft literals set to TRUE
        inc_bound = int(inc_solver.get_cost())
        # print('c')

        # Evaluate decreasing objective on the MaxSAT model
        ms_model = set(inc_solver.get_model() or [])
        # print('d')
        dec_bound = _count_true(ms_model, decreasing)
        # print('e')

        if dec_bound <= 0:
            print(f"c SOLUTION: pareto-optimal solution found for objective values inc={inc_bound}, and dec={dec_bound}")
            print("c INFO: there are no more pareto-optimal solutions (dec=0)")
            return True

        # Build (once) an optimizer totalizer for decreasing objective in SAT
        if dec_opt_tot is None:
            dec_opt_tot = Totalizer(
                solver_sat=sat_solver,
                solver_ipamir=None,
                mode="SAT",
                vcounter=VarCounter(n_dec_vars),
            )
            dec_opt_tot.build(decreasing, dec_bound)
            n_dec_vars = dec_opt_tot.vc.n

        # Enforce dec ≤ dec_bound - 1 by adding unit clause
        sat_solver.add_clause([-dec_opt_tot.get_out_lit(dec_bound - 1)])

        # Build/update a totalizer to bound the increasing objective in SAT
        if inc_tot is None:
            inc_tot = Totalizer(
                solver_sat=sat_solver,
                solver_ipamir=None,
                mode="SAT",
                vcounter=VarCounter(n_dec_vars),
            )
            inc_tot.build(increasing, inc_bound)
            n_dec_vars = inc_tot.vc.n
        else:
            inc_tot.update_upper(inc_bound)

        # If inc_bound is not the theoretical max, add an assumption to keep it ≤ inc_bound
        sat_assumptions: List[int] = []
        if inc_bound < len(increasing):
            sat_assumptions.append(-inc_tot.get_out_lit(inc_bound))

        # SAT–UNSAT search to lower dec_bound
        while sat_solver.solve(assumptions=sat_assumptions):
            # print('inner',flush=True)
            sat_model = set(sat_solver.get_model() or [])

            # Check increasing objective still equals inc_bound (infeasible otherwise)
            inc_val = _count_true(sat_model, increasing)
            assert inc_val == inc_bound, "Internal error: SAT solution reduced increasing objective"

            # Tighten dec_bound based on current model
            while dec_bound > 0:
                out_lit = dec_opt_tot.get_out_lit(dec_bound - 1)
                if -out_lit in sat_model:
                    dec_bound -= 1
                else:
                    break

            if dec_bound <= 0:
                break

            # Enforce dec ≤ dec_bound - 1 (stronger bound) and try again
            sat_solver.add_clause([-dec_opt_tot.get_out_lit(dec_bound - 1)])
            # Re-apply increasing bound assumption
            sat_assumptions = []
            if inc_bound < len(increasing):
                sat_assumptions.append(-inc_tot.get_out_lit(inc_bound))

        # Report Pareto point
        print(f"c SOLUTION: pareto-optimal solution found for objective values inc={inc_bound}, and dec={dec_bound}")

        if dec_bound <= 0:
            print("c INFO: there are no more pareto-optimal solutions (dec=0)")
            return True

        # Now forbid dec ≥ current dec_bound on the MaxSAT side (add a hard unit clause)
        if dec_bound_tot is None:
            dec_bound_tot = Totalizer(
                solver_sat=None,
                solver_ipamir=inc_solver,
                mode="MAXSAT",
                vcounter=VarCounter(n_inc_vars),
            )
            dec_bound_tot.build(decreasing, dec_bound)
            n_inc_vars = dec_bound_tot.vc.n
        # Hard clause: ¬out(dec_bound - 1), i.e., dec ≤ dec_bound - 1 for all next MaxSAT solves
        inc_solver.add_clause([-dec_bound_tot.get_out_lit(dec_bound - 1)])
        # loop to find next Pareto point


# ---------------- CLI ----------------
def main(argv: List[str], solver_cls: Type[IPAMIRSolver] = None) -> int:
    if len(argv) < 2:
        print("USAGE: ipamirbioptsat.py <input_file_name>\n")
        print("where <input_file_name> is a DIMACS bicnf instance as in the original app.")
        return 1

    # Instantiate solvers
    if solver_cls is not None:
        IPAMIR = solver_cls
    else:
        IPAMIR = _load_ipamir_solver_class()
    inc = IPAMIR()  # IPAMIR MaxSAT solver


    # PySAT SAT solver
    sat = Solver(name="Glucose42")

    # Diagnostics similar to the C++ app
    sig = inc.signature()
    print(f"c Solving with solver: {sig}")
    # print(f"c (SAT solver for application: {sat.name()})")

    # Initialize from file
    try:
        n_vars, increasing, decreasing = _parse_bicnf(argv[1], inc, sat)
    except Exception as e:
        print(f"c ERROR: error while initializing: {e}")
        return 1

    # Run
    ok = bioptsat(inc, sat, n_vars, increasing, decreasing)
    if not ok:
        print("c ERROR: error while solving; terminating!")
        return 1

    # Cleanup
    try:
        inc.close()
    except Exception:
        pass
    try:
        sat.delete()
    except Exception:
        pass
    return 0


# if __name__ == "__main__":
#     sys.exit(main(sys.argv))

import cProfile, pstats, sys

if __name__ == "__main__":
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        print("\nInterrupted, dumping profile…")
    finally:
        profiler.disable()
        stats = pstats.Stats(profiler)
        stats.strip_dirs().sort_stats("cumulative").print_stats(30)