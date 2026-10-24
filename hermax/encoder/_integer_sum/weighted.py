"""Weighted threshold PB encoding with bounded native output."""
from collections.abc import Sequence

from pysat.formula import CNFPlus

from hermax.internal import _integer_sum_native as native

STATE_LIMIT = 20_000
CLAUSE_LIMIT = 50_000
BudgetExceeded = native.EncodingBudgetExceeded


def encode_thresholds(
    chains: Sequence[Sequence[int]],
    coefficients: Sequence[int],
    bound: int,
    comparator: str,
    top_id: int,
) -> CNFPlus:
    terms = []
    for row, coefficient in zip(chains, coefficients):
        weight = abs(coefficient)
        terms.extend((lit if coefficient > 0 else -lit, weight) for lit in row)
        if coefficient < 0:
            bound += weight * len(row)
    clauses, top = native.encode_pb(
        wlits=terms,
        comparator={"<=": native.LEQ, ">=": native.GEQ, "==": native.BOTH}[comparator],
        bound=bound,
        top_id=top_id,
        pb_encoder=native.PB_BEST,
        conditionals=[],
        state_limit=STATE_LIMIT,
        clause_limit=CLAUSE_LIMIT,
    )
    result = CNFPlus()
    result.clauses, result.nv = clauses, max(top, top_id)
    return result
