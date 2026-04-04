#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ipamirextenf.py — Python port of the C++ IPAMIR/IPASIR MaxSAT app.

Sources mirrored:
- ipamirextenf.cpp (driver & loop)         [C++]  (translated)  :contentReference[oaicite:5]{index=5}
- Encoding.h / Encoding.cc (encoders)      [C++]  (translated)  :contentReference[oaicite:6]{index=6} :contentReference[oaicite:7]{index=7}
- Instance.h / Instance.cc (AF structure)  [C++]  (translated)  :contentReference[oaicite:8]{index=8} :contentReference[oaicite:9]{index=9}

Notes:
- IPAMIR side expects your Python interface (solve(), add_clause(), get_cost(), val(), etc.).
- SAT side uses PySAT (install: `pip install python-sat[pblib,aiger]`).
- The StaticAFEncoder "completeness" part intentionally matches the C++ source, which constructs
  a clause but (likely a bug) does not add it to the formula; this port preserves that behavior.  :contentReference[oaicite:10]{index=10}
"""

from __future__ import annotations
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set, Type

# --- Load the IPAMIR interface and a concrete solver class ---
# Your interface (with SolveStatus, IPAMIRSolver, etc.)
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus

# SAT side uses PySAT
from pysat.solvers import Solver as SatSolver


from typing import List, Tuple
import hashlib

# === Model interpretation helpers (drop-in) ===
from typing import Iterable, Dict, Set, Tuple, List

def build_var_truth_map(model: Iterable[int]) -> Dict[int, bool]:
    """
    Convert a solver model (arbitrary-ordered signed literals, one per var)
    into a map: var_id -> True/False.
    """
    vt: Dict[int, bool] = {}
    for x in model or []:
        v = abs(x)
        vt[v] = (x > 0)
    return vt

def lit_is_true(vt: Dict[int, bool], lit: int) -> bool:
    """
    Is literal 'lit' true under 'vt'?
    """
    v = abs(lit)
    t = vt.get(v)
    if t is None:
        # Variable not present: treat as False (or raise)
        return False
    return t if lit > 0 else (not t)


def fnv1a64_int(x: int) -> int:
    h = 0xcbf29ce484222325
    x &= (1 << 64) - 1
    for _ in range(8):
        h ^= (x & 0xff)
        h = (h * 0x100000001b3) & ((1 << 64) - 1)
        x >>= 8
    return h

def hash_hard(hard: List[List[int]]) -> int:
    h = 0xcbf29ce484222325
    for cls in hard:
        ch = 0xcbf29ce484222325
        for lit in cls:
            ch ^= fnv1a64_int(lit)
            ch = (ch * 0x100000001b3) & ((1 << 64) - 1)
        h ^= ch
        h = (h * 0x100000001b3) & ((1 << 64) - 1)
    return h

def hash_soft(soft: List[Tuple[int,int]]) -> int:
    h = 0xcbf29ce484222325
    for lit, w in soft:
        x = (lit & 0xffffffff) | ((w & 0xffffffff) << 32)
        h ^= fnv1a64_int(x)
        h = (h * 0x100000001b3) & ((1 << 64) - 1)
    return h

def lit_true_from_model(model: List[int], lit: int) -> bool:
    var = abs(lit)
    x = model[var - 1]
    assert abs(x) == var, f"model var mismatch for var {var}, got {x}"
    return (x > 0) if lit > 0 else (x < 0)

def eval_soft_cost_from_model(model: List[int], soft: List[Tuple[int,int]]) -> int:
    cost = 0
    for lit, w in soft:
        # cost when literal is TRUE (C++ ipamir_add_soft_lit semantics)
        if lit_true_from_model(model, lit):
            cost += w
    return cost

def hash_attacks(edges: List[Tuple[int,int]]) -> int:
    h = 0xcbf29ce484222325
    for i, j in edges:
        x = ((i & 0xffffffff) << 32) | (j & 0xffffffff)
        h ^= fnv1a64_int(x)
        h = (h * 0x100000001b3) & ((1 << 64) - 1)
    return h
# ==== DIAG HELPERS END ====

# --------------------------------------------------------------------------------------
# AF instance (Instance.h/cc in C++)                                                   #
# --------------------------------------------------------------------------------------

class AF:
    def __init__(self) -> None:
        self.args: List[str] = []
        self.atts: List[Tuple[int, int]] = []
        self.enfs: List[int] = []
        self.attackers: Dict[int, List[int]] = {}
        self.att_exists: Dict[Tuple[int, int], bool] = {}
        self.arg_to_int: Dict[str, int] = {}
        self.enforce: Dict[int, bool] = {}

    def addArgument(self, arg: str) -> None:
        self.arg_to_int[arg] = len(self.args)
        self.args.append(arg)

    def addAttack(self, att: Tuple[str, str]) -> None:
        src = self.arg_to_int[att[0]]
        dst = self.arg_to_int[att[1]]
        self.attackers.setdefault(dst, []).append(src)
        self.atts.append((src, dst))
        self.att_exists[(src, dst)] = True

    def addEnforcement(self, arg: str) -> None:
        v = self.arg_to_int[arg]
        self.enfs.append(v)
        self.enforce[v] = True

    def numberOfConflicts(self) -> int:
        conflicts = 0
        for (i, j) in self.atts:
            if self.enforce.get(i, False) and self.enforce.get(j, False):
                conflicts += 1
        return conflicts

    def print(self) -> None:
        for i, a in enumerate(self.args):
            print(f"arg({a}).")
        for (s, t) in self.atts:
            print(f"att({self.args[s]},{self.args[t]}).")


# --------------------------------------------------------------------------------------
# MaxSATFormula & Encoders (Encoding.h/cc in C++)                                      #
# --------------------------------------------------------------------------------------

@dataclass
class MaxSATFormula:
    hard_clauses: List[List[int]]
    soft_literals: List[Tuple[int, int]]

    def __init__(self) -> None:
        self.hard_clauses = []
        self.soft_literals = []

    # helpers mirroring C++ convenience overloads
    def addHardClause(self, *args) -> None:
        if len(args) == 1 and isinstance(args[0], list):
            self.hard_clauses.append(list(args[0]))
        else:
            self.hard_clauses.append(list(args))

    def addSoftLiteral(self, lit: int, w: int) -> None:
        self.soft_literals.append((lit, int(w)))


class DynamicAFEncoder:
    # Variables:
    # - att_var[(i,j)] exists if NOT (enforce[i] AND enforce[j])
    # - no_counter_var[(i,j)] exists if NOT enforce[i] AND NOT enforce[j]
    def __init__(self, af: AF) -> None:
        self.instance = af
        self.count: int = 0
        self.formula = MaxSATFormula()
        self.att_var: Dict[Tuple[int, int], int] = {}
        self._no_counter_var: Dict[Tuple[int, int], int] = {}

        n = len(self.instance.args)
        for i in range(n):
            for j in range(n):
                if not (self.instance.enforce.get(i, False) and self.instance.enforce.get(j, False)):
                    self.count += 1
                    self.att_var[(i, j)] = self.count
        for i in range(n):
            if not self.instance.enforce.get(i, False):
                for j in range(n):
                    if not self.instance.enforce.get(j, False):
                        self.count += 1
                        self._no_counter_var[(i, j)] = self.count

    def n_vars(self) -> int:
        return self.count

    def generate_encoding(self) -> None:
        af = self.instance
        n = len(af.args)

        # admissibility
        for i in range(n):
            if af.enforce.get(i, False):
                for j in range(n):
                    if not af.enforce.get(j, False):
                        clause = [-self.att_var[(j, i)]]
                        for k in range(n):
                            if af.enforce.get(k, False):
                                clause.append(self.att_var[(k, j)])
                        self.formula.addHardClause(clause)

        # define no counter
        for i in range(n):
            if not af.enforce.get(i, False):
                for j in range(n):
                    if not af.enforce.get(j, False):
                        nc = self._no_counter_var[(i, j)]
                        aij = self.att_var[(i, j)]
                        clause = [nc, -aij]
                        # binary clauses
                        self.formula.addHardClause(-nc, aij)
                        for k in range(n):
                            if af.enforce.get(k, False):
                                clause.append(self.att_var[(k, i)])
                                self.formula.addHardClause(-nc, -self.att_var[(k, i)])
                        self.formula.addHardClause(clause)

        # completeness
        for i in range(n):
            if not af.enforce.get(i, False):
                clause: List[int] = []
                for j in range(n):
                    if af.enforce.get(j, False):
                        clause.append(self.att_var[(j, i)])
                    else:
                        clause.append(self._no_counter_var[(j, i)])
                self.formula.addHardClause(clause)

        # minimize changes (Hamming distance to original)
        for i in range(n):
            for j in range(n):
                if not (af.enforce.get(i, False) and af.enforce.get(j, False)):
                    lit = -self.att_var[(i, j)] if af.att_exists.get((i, j), False) else self.att_var[(i, j)]
                    self.formula.addSoftLiteral(lit, 1)


class StaticAFEncoder:
    # Variables:
    # - arg_accepted_var[i], arg_rejected_var[i]
    def __init__(self, af: AF) -> None:
        self.instance = af
        self.count: int = 0
        self.formula = MaxSATFormula()
        self.arg_accepted_var: Dict[int, int] = {}
        self.arg_rejected_var: Dict[int, int] = {}

        n = len(self.instance.args)
        for i in range(n):
            self.count += 1
            self.arg_accepted_var[i] = self.count
        for i in range(n):
            self.count += 1
            self.arg_rejected_var[i] = self.count

    def n_vars(self) -> int:
        return self.count

    def generate_encoding(self) -> None:
        af = self.instance
        n = len(af.args)

        # conflict-freeness: ¬acc(i) ∨ ¬acc(attacker)
        for i in range(n):
            for a in af.attackers.get(i, []):
                self.formula.addHardClause(-self.arg_accepted_var[i], -self.arg_accepted_var[a])

        # define rejected:
        #   (¬rej(i) ∨ acc(attacker1) ∨ ... )
        #   (rej(i) ∨ ¬acc(attacker)) for each attacker
        for i in range(n):
            clause = [-self.arg_rejected_var[i]]
            for a in af.attackers.get(i, []):
                clause.append(self.arg_accepted_var[a])
                self.formula.addHardClause(self.arg_rejected_var[i], -self.arg_accepted_var[a])
            self.formula.addHardClause(clause)

        # completeness (as in C++ source):
        # Builds clause [acc(i), ¬rej(attacker1), ...] and adds
        #   (¬acc(i) ∨ rej(attacker)) binaries — the C++ code does not
        # actually add the big clause to the formula; we preserve this.
        for i in range(n):
            clause = [self.arg_accepted_var[i]]
            for a in af.attackers.get(i, []):
                clause.append(-self.arg_rejected_var[a])
                self.formula.addHardClause(-self.arg_accepted_var[i], self.arg_rejected_var[a])
            # Intentionally NOT adding 'clause' to hard_clauses (matches C++).  :contentReference[oaicite:11]{index=11}


# --------------------------------------------------------------------------------------
# File parsing (APX style, like ipamirextenf.cpp)                                      #
# --------------------------------------------------------------------------------------

def parse_apx(path: str) -> AF:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    af = AF()
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = "".join(ch for ch in raw if not ch.isspace())
            if not line or line[0] in ("/", "%"):
                continue
            if len(line) < 6:
                print(f"WARNING: Cannot parse line: {line.strip()}")
                continue
            op = line[:3]
            if op == "arg":
                if line[3] == "(" and ")" in line:
                    arg = line[4:line.find(")")]
                    af.addArgument(arg)
                else:
                    print(f"WARNING: Cannot parse line: {line.strip()}")
            elif op == "att":
                if line[3] == "(" and "," in line and ")" in line:
                    src = line[4:line.find(",")]
                    tgt = line[line.find(",") + 1: line.find(")")]
                    af.addAttack((src, tgt))
                else:
                    print(f"WARNING: Cannot parse line: {line.strip()}")
            elif op == "enf":
                if line[3] == "(" and ")" in line:
                    arg = line[4:line.find(")")]
                    af.addEnforcement(arg)
                else:
                    print(f"WARNING: Cannot parse line: {line.strip()}")
    return af


# --------------------------------------------------------------------------------------
# Driver (translated from ipamirextenf.cpp main)                                       #
# --------------------------------------------------------------------------------------

def _load_ipamir_solver_class():
    spec = os.environ.get("IPAMIR_SOLVER", "hermax.core:RC2Reentrant")
    # spec = os.environ.get("IPAMIR_SOLVER", "urmaxsat_solver:UWrMaxSATSolver")
    tried = []
    def load(spec_str: str):
        mod, cls = spec_str.split(":")
        import importlib
        return getattr(importlib.import_module(mod), cls)
    return load(spec)


def run(ipamir: IPAMIRSolver, sat: SatSolver, af: AF) -> int:
    print(f"c Number of arguments: {len(af.args)}")
    print(f"c Number of attacks:   {len(af.atts)}")
    print(f"c Number of targets:   {len(af.enfs)}")
    print(f"c Number of conflicts: {af.numberOfConflicts()}")

    # Build dynamic MaxSAT encoding
    dyn = DynamicAFEncoder(af)
    dyn.generate_encoding()
    # print("c DIAG hard_count", len(dyn.formula.hard_clauses),
    #   "soft_count", len(dyn.formula.soft_literals))
    # print("c DIAG hard_hash 0x%016x" % hash_hard(dyn.formula.hard_clauses))
    # print("c DIAG soft_hash 0x%016x" % hash_soft(dyn.formula.soft_literals))
    # for i, (lit, w) in enumerate(dyn.formula.soft_literals[:8]):
    #     print(f"c DIAG soft[{i}] lit {lit} w {w}")

    # Feed MaxSAT hard clauses
    for cl in dyn.formula.hard_clauses:
        ipamir.add_clause(cl)

    # Feed MaxSAT soft unit literals as [-lit] so cost is paid when 'lit' is True,
    # which emulates ipamir_add_soft_lit(lit, w) from the C++ implementation.
    for lit, w in dyn.formula.soft_literals:
        ipamir.add_soft_unit(-lit, w)

    # print("c DIAG added_hard", len(dyn.formula.hard_clauses),
    #   "added_soft", len(dyn.formula.soft_literals))

    # Main loop
    while True:
        # print('solve incr max')
        # input('solve incr max')
        feas = ipamir.solve()
        # print(f"c o {ipamir.get_cost()}")
        code = ipamir.get_status().value
        # print(f"c code {code}")
        if code != 30:  # expect OPTIMUM (30) at each MaxSAT step per original app
            print(f"ERROR: ipamir_solve returned {code}. Terminating.")
            return code

        model = ipamir.get_model()
        # vt = build_var_truth_map(model)
        # cost_true  = sum(w for lit, w in dyn.formula.soft_literals if lit_is_true(vt, lit))
        # cost_false = sum(w for lit, w in dyn.formula.soft_literals if not lit_is_true(vt, lit))
        # print("c DIAG costs solver", ipamir.get_cost(), "true(lit)", cost_true, "false(lit)", cost_false)

        # Build candidate AF from MaxSAT model

        # for i, (lit, w) in enumerate(dyn.formula.soft_literals[:12]):
        #     lit_true = lit_is_true(vt, lit)
        #     unit = [-lit]                           # what you actually fed
        #     unit_sat = (not lit_true)               # [-lit] is satisfied iff lit is False
        #     print(f"c DIAG soft[{i}] lit {lit:+d} true={lit_true} unit[-lit]_sat={unit_sat}")

        cand = AF()
        for a in af.args:
            cand.addArgument(a)

        # model = set(ipamir.get_model() or [])
        # for i in range(n):
        #     for j in range(n):
        #         if not (af.enforce.get(i, False) and af.enforce.get(j, False)):
        #             if dyn.att_var[(i, j)] in model:
        #                 cand.addAttack((af.args[i], af.args[j]))
        
        # cost_true  = sum(w for lit, w in dyn.formula.soft_literals if lit_is_true(vt, lit))
        # cost_false = sum(w for lit, w in dyn.formula.soft_literals if not lit_is_true(vt, lit))
        # solver_cost = ipamir.get_cost()

        # print("c DIAG costs solver", solver_cost, "true(lit)", cost_true, "false(lit)", cost_false)

        # Evaluate MaxSAT literal semantics: cost if literal itself is TRUE
        # inc_cost_diag = 0
        # for lit, w in dyn.formula.soft_literals:  # or whatever you store; keep the same source you used to feed MaxSAT
        #     if lit_is_true(vt, lit):
        #         inc_cost_diag += w
        # print("c DIAG model_soft_cost", inc_cost_diag)

        # If you want to see which soft literals are true:
        # soft_true = []
        # for lit, w in dyn.formula.soft_literals:
        #     if lit_is_true(vt, lit):
        #         v = abs(lit)
        #         ij = rev_att.get(v, None)  # your existing reverse map
        #         soft_true.append((ij, 1 if lit > 0 else -1))
        # print("c DIAG soft_true_cnt", len(soft_true))
        # for x in soft_true[:10]:
        #     print("c DIAG soft_true", x)

        # ==== DIAG SOFT TRUE SET END ====
        n = len(af.args)
        for i in range(n):
            for j in range(n):
                if af.enforce.get(i, False) and af.enforce.get(j, False):
                    continue
                # cost when literal is True uses the literal itself (not the var)
                v = dyn.att_var[(i, j)]
                # ask the solver for the truth value of the **literal v**
                # is_true = ipamir.get_value(v)  # True/False/None
                is_true = model[abs(v) - 1] > 0
                # assert is_true == lit_is_true(vt, v)
                assert abs(model[abs(v) - 1]) == abs(v)
                if is_true is True:
                    cand.addAttack((af.args[i], af.args[j]))

        # edges = sorted([(i, j) for (i, j) in cand.atts])
        # print("c DIAG cand_attacks", len(edges),
        #     "cand_hash 0x%016x" % hash_attacks(edges))
        # for e in edges[:10]:
        #     print("c DIAG cand_edge", e)

        # Static SAT encoding for candidate
        sta = StaticAFEncoder(cand)
        sta.generate_encoding()

        sat.delete()
        sat = SatSolver(name="glucose4")  # new SAT solver per loop (mirrors ipasir_init per iteration)

        for cl in sta.formula.hard_clauses:
            sat.add_clause(cl)

        # Enforce all enforced arguments to be accepted
        for i in range(n):
            if af.enforce.get(i, False):
                sat.add_clause([sta.arg_accepted_var[i]])

        # Big clause: at least one non-enforced argument is accepted
        big = [sta.arg_accepted_var[i] for i in range(n) if not af.enforce.get(i, False)]
        # print("c DIAG big_clause_size", len(big))
        assert big
        if big:
            sat.add_clause(big)

        sat_code = 10 if sat.solve() else 20  # PySAT: True→SAT(10), False→UNSAT(20)

        if sat_code == 10:
            labeling = [0] * n
            sat_model = set(sat.get_model() or [])
            for i in range(n):
                if sta.arg_accepted_var[i] in sat_model:
                    labeling[i] = 1
                elif sta.arg_rejected_var[i] in sat_model:
                    labeling[i] = -1
                # else keep 0

            # Add excluding constraints to MaxSAT as hard clauses
            # Matches C++: for each (i,j)
            excl = []

            for i in range(n):
                for j in range(n):
                    if cand.att_exists.get((i, j), False):
                        if labeling[i] == 1 and labeling[j] == -1:
                            excl.append(-dyn.att_var[(i, j)])
                    else:
                        if ((labeling[i] == 1 and labeling[j] == 1) or
                            (labeling[i] == 0 and labeling[j] == 1)):
                            if not (af.enforce.get(i, False) and af.enforce.get(j, False)):
                                excl.append(+dyn.att_var[(i, j)])

            # Add exactly one clause, even if empty (empty => immediate UNSAT, same as C++)
            ipamir.add_clause(excl)   # one big hard clause
            # Loop continues
        elif sat_code == 20:
            print("s OPTIMUM FOUND")
            print(f"o {ipamir.get_cost()}")
            # cand.print()
            return 0
        else:
            print(f"ERROR: ipasir_solve returned {sat_code}. Terminating.")
            return sat_code


def main(argv: List[str], solver_cls: Type[IPAMIRSolver] = None) -> int:
    if len(argv) < 2:
        print("USAGE: ipamirextenf.py <input_file_name>\n")
        print("where <input_file_name> is an AF in APX format.")
        return 1

    # Load AF
    try:
        af = parse_apx(argv[1])
    except Exception as e:
        print(f"ERROR: failed to read input: {e}")
        return 1

    # Instantiate solvers
    if solver_cls is not None:
        IPAMIR = solver_cls
    else:
        IPAMIR = _load_ipamir_solver_class()
    inc = IPAMIR()
    sig = "<unknown>"
    try:
        sig = inc.signature()
    except Exception:
        pass
    sat = SatSolver(name="glucose4")

    # print(f"c Solving with solver: {sig}")
    # print(f"c (SAT solver for application: {sat.name()})")

    try:
        rc = run(inc, sat, af)
        return rc
    finally:
        try:
            inc.close()
        except Exception:
            pass
        try:
            sat.delete()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv))
