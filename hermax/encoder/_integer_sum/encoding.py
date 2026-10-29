"""Private CNF building blocks for sums over existing integer thresholds."""
from collections.abc import Sequence
from dataclasses import dataclass

from pysat.formula import CNFPlus

from hermax.internal import _integer_sum_native as native
from hermax.internal._clause_storage import ClauseStorage
from hermax.encoder._packed import PBEnc, _EncodedCNF

LEAF = "leaf"
WHOLE = "whole"
BINARY = "binary"


@dataclass(frozen=True, slots=True)
class Size:
    variables: int
    clauses: int


@dataclass(frozen=True, slots=True)
class Costs:
    leaf: Size
    whole: Size
    modulus: int


def assess(widths: Sequence[int], bound: int) -> Costs:
    raw = native.assess_order_sum(list(widths), bound)
    return Costs(
        Size(raw["leaf_variables"], raw["leaf_clauses"]),
        Size(raw["whole_variables"], raw["whole_clauses"]),
        raw["modulus"],
    )


def encode_order(
    chains: Sequence[Sequence[int]],
    bound: int,
    top_id: int,
    kind: str,
    modulus: int = 0,
    *,
    _packed: bool = False,
) -> CNFPlus | _EncodedCNF:
    if kind not in (LEAF, WHOLE):
        raise ValueError("expected an order-sum encoder")
    encode = native._encode_order_sum_packed if _packed else native.encode_order_sum
    clauses, nv = encode(
        chains, bound, top_id, int(kind == WHOLE), modulus
    )
    cnf = _EncodedCNF() if _packed else CNFPlus()
    cnf.clauses = ClauseStorage._wrap(clauses) if _packed else clauses
    cnf.nv = nv
    return cnf


def channel_cost(width: int) -> int:
    """Exact clause count for a new binary view (width one needs no view)."""
    if width <= 1:
        return 0
    return sum(width // (1 << j) + 1 for j in range(width.bit_length()))


def bit_channels(chain: Sequence[int], bits: Sequence[int]):
    """Define each bit over maximal constant-bit intervals."""
    width = len(chain)
    if len(bits) != width.bit_length():
        raise ValueError("binary view has the wrong width")
    for j, bit in enumerate(bits):
        step = 1 << j
        clauses = []
        for block, lo in enumerate(range(0, width + 1, step)):
            hi = min(width, lo + step - 1)
            clause = []
            if lo:
                clause.append(-chain[lo - 1])
            if hi < width:
                clause.append(chain[hi])
            clause.append(bit if block % 2 else -bit)
            clauses.append(clause)
        yield bit, clauses


def binary_pb(
    views: Sequence[Sequence[int]],
    coefficients: Sequence[int],
    bound: int,
    comparator: str,
    top_id: int,
) -> CNFPlus:
    """Encode arithmetic over cached views; definitions are owned by callers."""
    if len(views) != len(coefficients):
        raise ValueError("one coefficient per binary view is required")
    lits, weights = [], []
    for bits, coefficient in zip(views, coefficients):
        if not isinstance(coefficient, int):
            raise ValueError("integer-sum coefficients must be integers")
        if not coefficient:
            continue
        for j, bit in enumerate(bits):
            weight = abs(coefficient) << j
            if coefficient < 0:
                bit = -bit
                bound += weight
            lits.append(bit)
            weights.append(weight)
    if comparator not in ("<=", ">=", "=="):
        raise ValueError("unsupported integer-sum comparison")
    total = sum(weights)
    satisfied = (comparator == "<=" and bound >= total) or (
        comparator == ">=" and bound <= 0
    )
    impossible = (
        (comparator == "<=" and bound < 0)
        or (comparator == ">=" and bound > total)
        or (comparator == "==" and not 0 <= bound <= total)
    )
    if satisfied or impossible:
        cnf = _EncodedCNF()
        cnf.nv = top_id
        if impossible:
            cnf.clauses.append([])
        return cnf
    fn = {"<=": PBEnc.leq, ">=": PBEnc.geq, "==": PBEnc.equals}[comparator]
    return fn(lits, weights=weights, bound=bound, top_id=top_id)


def encode_binary(
    chains: Sequence[Sequence[int]],
    bound: int,
    top_id: int,
    comparator: str = "<=",
    coefficients: Sequence[int] | None = None,
) -> CNFPlus:
    """Stateless internal encoder used for differential tests and measurements."""
    coefficients = list(coefficients) if coefficients is not None else [1] * len(chains)
    if len(coefficients) != len(chains):
        raise ValueError("one coefficient per chain is required")
    top_id = max([top_id] + [abs(l) for row in chains for l in row])
    channels, views = [], []
    for row in chains:
        if len(row) <= 1:
            views.append(list(row))
            continue
        bits = list(range(top_id + 1, top_id + 1 + len(row).bit_length()))
        top_id += len(bits)
        for _, clauses in bit_channels(row, bits):
            channels.extend(clauses)
        views.append(bits)
    arithmetic = binary_pb(views, coefficients, bound, comparator, top_id)
    result = CNFPlus()
    result.nv = arithmetic.nv
    result.clauses = channels + arithmetic.clauses.to_lists()
    return result
