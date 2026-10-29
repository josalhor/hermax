"""Weighted threshold PB encoding with bounded native output."""
from collections.abc import Sequence

from pysat.formula import CNFPlus

from hermax.internal import _integer_sum_native as native
from hermax.internal._clause_storage import ClauseStorage
from hermax.encoder._packed import _EncodedCNF

STATE_LIMIT = 20_000
CLAUSE_LIMIT = 50_000
BudgetExceeded = native.EncodingBudgetExceeded


def encode_thresholds(
    chains: Sequence[Sequence[int]],
    coefficients: Sequence[int],
    bound: int,
    comparator: str,
    top_id: int,
    *,
    _packed: bool = False,
) -> CNFPlus | _EncodedCNF:
    if len(chains) != len(coefficients):
        raise ValueError("one coefficient per chain is required")
    totals = {}
    for row, coefficient in zip(chains, coefficients):
        for literal in row:
            if literal < 0:
                bound -= coefficient
                literal, contribution = -literal, -coefficient
            else:
                contribution = coefficient
            totals[literal] = totals.get(literal, 0) + contribution
    terms = []
    for literal, coefficient in totals.items():
        if coefficient < 0:
            bound -= coefficient
            terms.append((-literal, -coefficient))
        elif coefficient > 0:
            terms.append((literal, coefficient))
    encode = native._encode_pb_packed if _packed else native.encode_pb
    clauses, top = encode(
        wlits=terms,
        comparator={"<=": native.LEQ, ">=": native.GEQ, "==": native.BOTH}[comparator],
        bound=bound,
        top_id=top_id,
        pb_encoder=native.PB_BEST,
        conditionals=[],
        state_limit=STATE_LIMIT,
        clause_limit=CLAUSE_LIMIT,
    )
    result = _EncodedCNF() if _packed else CNFPlus()
    result.clauses = ClauseStorage._wrap(clauses) if _packed else clauses
    result.nv = max(top, top_id)
    return result
