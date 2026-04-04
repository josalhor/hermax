from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from hermax.core.ipamir_solver_interface import SolveStatus


_STATUS_RE = re.compile(r"^\s*s\s+(.+?)\s*$", re.IGNORECASE)
_OBJ_RE = re.compile(r"^\s*o\s+(-?\d+)\s*$")
_V_RE = re.compile(r"^\s*v\s+(.*)$")


def parse_maxsat_cli_output(
    out: str,
    *,
    num_vars: int,
) -> tuple[Optional[SolveStatus], Optional[int], Optional[List[int]]]:
    """
    Parse common MaxSAT CLI output.

    Supports:
    - `s ...` status lines
    - `o <int>` objective lines
    - `v ...` model lines as either:
      - DIMACS signed literals (e.g. `v 1 -2 3 -4 0`)
      - compact bitstring (e.g. `v 1010`)
    """
    last_status: Optional[SolveStatus] = None
    best_cost: Optional[int] = None
    lits: List[int] = []

    for line in out.splitlines():
        m = _STATUS_RE.match(line)
        if m:
            token = m.group(1).strip().upper()
            if "OPTIMUM" in token:
                last_status = SolveStatus.OPTIMUM
            elif "UNSAT" in token:
                last_status = SolveStatus.UNSAT
            elif "SAT" in token:
                last_status = SolveStatus.INTERRUPTED_SAT
            elif "UNKNOWN" in token:
                last_status = SolveStatus.INTERRUPTED if not lits else SolveStatus.INTERRUPTED_SAT
            continue

        m = _OBJ_RE.match(line)
        if m:
            best_cost = int(m.group(1))
            continue

        m = _V_RE.match(line)
        if not m:
            continue
        payload = m.group(1).strip()
        if not payload:
            continue

        toks = payload.split()
        # Compact bitstring format: "v 1010"
        if len(toks) == 1 and toks[0] and all(ch in "01" for ch in toks[0]):
            bitstr = toks[0]
            lits = [i if ch == "1" else -i for i, ch in enumerate(bitstr, start=1)]
            continue

        # DIMACS signed literals format: "v 1 -2 3 -4 0"
        for tok in toks:
            if tok == "0":
                continue
            try:
                lits.append(int(tok))
            except ValueError:
                pass

    model = None
    if lits:
        by_var: Dict[int, int] = {}
        for l in lits:
            if l != 0:
                by_var[abs(l)] = l
        model = [by_var.get(v, -v) for v in range(1, num_vars + 1)]

    return last_status, best_cost, model

