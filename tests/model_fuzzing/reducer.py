"""Small deterministic reducer for semantic-fuzzer failures."""

from __future__ import annotations

from .ast import Case
from .oracle import Mismatch, check_case


def reduce_case(case: Case, target: Mismatch) -> tuple[Case, Mismatch]:
    """Greedily delete conjuncts while preserving the same failing assignment/kind."""
    current = case
    changed = True
    while changed and len(current.constraints) > 1:
        changed = False
        for index in range(len(current.constraints)):
            candidate = Case(current.bool_count, current.int_domains, current.constraints[:index] + current.constraints[index + 1 :])
            mismatch = check_case(candidate)
            if mismatch is not None and mismatch.kind == target.kind and mismatch.environment == target.environment:
                current = candidate
                target = mismatch
                changed = True
                break
    return current, target
