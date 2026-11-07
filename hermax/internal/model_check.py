from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, List, Optional, Sequence, Tuple

from hermax.internal._clauses import satisfies


Clause = Sequence[int]
WeightedClause = Tuple[Sequence[int], int | float]


def _literal(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{context} literals must be integers.")
    if value == 0:
        raise ValueError(f"{context} literals cannot be 0.")
    return int(value)


def _weight(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("soft weights must be numeric.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("soft weights must be finite.")
    if value <= 0:
        raise ValueError("soft weights must be positive.")
    return value


def model_literal_set(model: Iterable[int]) -> set[int]:
    return {_literal(x, context="model") for x in model}


def model_is_consistent(model: Iterable[int]) -> bool:
    """Return whether a model contains only non-contradictory literals."""
    seen: set[int] = set()
    for raw_lit in model:
        try:
            lit = _literal(raw_lit, context="model")
        except (TypeError, ValueError):
            return False
        if abs(lit) in seen:
            return False
        seen.add(abs(lit))
    return True


def clause_satisfied(clause: Clause, model: Iterable[int]) -> bool:
    s = model_literal_set(model)
    return any(int(lit) in s for lit in clause)


def model_satisfies_hard_clauses(hards: Iterable[Clause], model: Iterable[int]) -> bool:
    return satisfies(hards, model)


def normalize_soft_units_last_wins(softs: Iterable[WeightedClause]) -> List[Tuple[List[int], int | float]]:
    """
    Soft clauses under Hermax/IPAMIR wrapper:

    - Unit soft clauses are deduplicated by literal (polarity-sensitive) using last-wins.
    - Non-unit soft clauses are preserved as a multiset.
    """
    last_unit: dict[int, int | float] = {}
    nonunits: list[tuple[list[int], int | float]] = []

    for clause, w in softs:
        cl = [_literal(x, context="soft clause") for x in clause]
        ww = _weight(w)
        if len(cl) == 1:
            last_unit[int(cl[0])] = ww
        else:
            nonunits.append((cl, ww))

    out = nonunits[:]
    out.extend(([lit], w) for lit, w in last_unit.items())
    return out


def maxsat_cost_of_model(model: Iterable[int], softs: Iterable[WeightedClause]) -> int | float:
    """
    Compute weighted partial MaxSAT cost for a model under soft.
    """
    s = model_literal_set(model)
    total = 0
    for clause, w in normalize_soft_units_last_wins(softs):
        if not any(_literal(lit, context="soft clause") in s for lit in clause):
            total += w
    return total


@dataclass(frozen=True)
class ModelCheckResult:
    hards_ok: bool
    recomputed_cost: int | float
    reported_cost_matches: Optional[bool]


def check_model(
    model: Iterable[int],
    hards: Iterable[Clause],
    softs: Iterable[WeightedClause],
    reported_cost: Optional[int | float] = None,
) -> ModelCheckResult:
    recomputed = maxsat_cost_of_model(model, softs)
    if reported_cost is not None and (isinstance(reported_cost, bool) or not isinstance(reported_cost, (int, float))):
        raise TypeError("reported_cost must be numeric or None.")
    if isinstance(reported_cost, float) and not math.isfinite(reported_cost):
        raise ValueError("reported_cost must be finite or None.")
    return ModelCheckResult(
        hards_ok=model_satisfies_hard_clauses(hards, model),
        recomputed_cost=recomputed,
        reported_cost_matches=(None if reported_cost is None else reported_cost == recomputed),
    )
