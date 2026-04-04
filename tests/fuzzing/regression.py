from __future__ import annotations

from .model import WeightedCNF


def regression_cases() -> list[tuple[str, WeightedCNF]]:
    max63 = (2**63) - 1
    near64sum_w1 = (2**63) - 1
    near64sum_w2 = (2**63) - 1

    cases: list[tuple[str, WeightedCNF]] = []

    # 1) Empty instance
    cases.append(("empty_instance", WeightedCNF(hard=[], soft=[], nvars=1)))

    # 2) Empty hard clause (UNSAT)
    cases.append(("empty_hard_clause", WeightedCNF(hard=[[]], soft=[], nvars=1)))

    # 3) Empty soft clause
    cases.append(("empty_soft_clause", WeightedCNF(hard=[[1]], soft=[([], 1)], nvars=1)))

    # 4) Tautologies
    cases.append((
        "tautologies",
        WeightedCNF(hard=[[1, -1], [2, -2, 3], [-3, 3]], soft=[([1, -1], 7), ([-2, 2], 5)], nvars=3),
    ))

    # 5) Boundary weights
    cases.append((
        "boundary_weights",
        WeightedCNF(
            hard=[[1], [2]],
            soft=[([-1], max63), ([-2], near64sum_w1), ([1, -2], near64sum_w2)],
            nvars=2,
        ),
    ))

    return cases

