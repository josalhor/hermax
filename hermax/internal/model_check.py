from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


Clause = Sequence[int]
WeightedClause = Tuple[Sequence[int], int]


def model_literal_set(model: Iterable[int]) -> set[int]:
    return {int(x) for x in model}


def clause_satisfied(clause: Clause, model: Iterable[int]) -> bool:
    s = model_literal_set(model)
    return any(int(lit) in s for lit in clause)


def model_satisfies_hard_clauses(hards: Iterable[Clause], model: Iterable[int]) -> bool:
    s = model_literal_set(model)
    return all(any(int(lit) in s for lit in cl) for cl in hards)


def normalize_soft_units_last_wins(softs: Iterable[WeightedClause]) -> List[Tuple[List[int], int]]:
    """
    Canonicalize soft clauses under Hermax/IPAMIR wrapper semantics.

    - Unit soft clauses are deduplicated by literal (polarity-sensitive) using last-wins.
    - Non-unit soft clauses are preserved as a multiset.
    """
    last_unit: dict[int, int] = {}
    nonunits: list[tuple[list[int], int]] = []

    for clause, w in softs:
        cl = [int(x) for x in clause]
        ww = int(w)
        if len(cl) == 1:
            last_unit[int(cl[0])] = ww
        else:
            nonunits.append((cl, ww))

    out = nonunits[:]
    out.extend(([lit], w) for lit, w in last_unit.items())
    return out


def maxsat_cost_of_model(model: Iterable[int], softs: Iterable[WeightedClause]) -> int:
    """
    Compute weighted partial MaxSAT cost for a model under canonical soft semantics.
    """
    s = model_literal_set(model)
    total = 0
    for clause, w in normalize_soft_units_last_wins(softs):
        if not any(int(lit) in s for lit in clause):
            total += int(w)
    return total


@dataclass(frozen=True)
class ModelCheckResult:
    hards_ok: bool
    recomputed_cost: int
    reported_cost_matches: Optional[bool]


def check_model(
    model: Iterable[int],
    hards: Iterable[Clause],
    softs: Iterable[WeightedClause],
    reported_cost: Optional[int] = None,
) -> ModelCheckResult:
    recomputed = maxsat_cost_of_model(model, softs)
    return ModelCheckResult(
        hards_ok=model_satisfies_hard_clauses(hards, model),
        recomputed_cost=recomputed,
        reported_cost_matches=(None if reported_cost is None else int(reported_cost) == recomputed),
    )
