from __future__ import annotations

import random

import pytest

from tests.structuredpb_test_utils import assert_encoding_matches_oracle_and_baseline, case_id, partition_lits


MDD_CASES = [
    {"name": "zero-bound-balanced", "lits": [1, 2, 3, 4], "weights": [2, 3, 4, 5], "groups": [[1, 2], [3, 4]], "bound": 0},
    {"name": "many-singletons-tight", "lits": [1, 2, 3, 4, 5], "weights": [1, 2, 2, 3, 4], "groups": [[1], [2], [3], [4], [5]], "bound": 4},
    {"name": "few-large-groups-loose", "lits": [1, 2, 3, 4, 5, 6], "weights": [4, 7, 5, 6, 2, 9], "groups": [[1, 2, 3], [4, 5, 6]], "bound": 13},
    {"name": "equal-weights-many-groups", "lits": [1, 2, 3, 4, 5, 6], "weights": [5, 5, 5, 5, 5, 5], "groups": [[1], [2, 3], [4], [5, 6]], "bound": 10},
    {"name": "two-weight-balanced", "lits": [1, 2, 3, 4, 5, 6], "weights": [3, 8, 3, 8, 3, 8], "groups": [[1, 2], [3, 4], [5, 6]], "bound": 11},
    {"name": "hugew-small-structured", "lits": [1, 2, 3, 4], "weights": [500, 1200, 900, 1500], "groups": [[1, 2], [3, 4]], "bound": 1700},
    {"name": "near-total-bound", "lits": [1, 2, 3, 4, 5], "weights": [2, 6, 7, 4, 5], "groups": [[1, 2], [3], [4, 5]], "bound": 18},
    {"name": "asymmetric-group-sizes", "lits": [1, 2, 3, 4, 5, 6, 7], "weights": [1, 9, 3, 8, 4, 7, 5], "groups": [[1, 2, 3, 4], [5], [6, 7]], "bound": 14},
]


@pytest.mark.parametrize("case", MDD_CASES, ids=case_id)
def test_mdd_edge_cases(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str, case: dict[str, object]) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="mdd",
        lits=case["lits"],
        weights=case["weights"],
        groups=case["groups"],
        bound=case["bound"],
    )


def test_mdd_small_random_smoke(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    rng = random.Random(0x4D44)
    for _ in range(6):
        n = rng.randint(3, 7)
        lits = list(range(1, n + 1))
        groups = partition_lits(rng, lits)
        weights = [rng.randint(1, 15) for _ in range(n)]
        bound = rng.randint(0, sum(weights))
        assert_encoding_matches_oracle_and_baseline(
            structuredpb_module=structuredpb_module,
            pb_baseline=pb_baseline,
            card_baseline=card_baseline,
            sat_solver_name=sat_solver_name,
            encoding_name="mdd",
            lits=lits,
            weights=weights,
            groups=groups,
            bound=bound,
        )


def test_mdd_respects_top_id(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="mdd",
        lits=[1, 2, 3, 4],
        weights=[3, 4, 8, 9],
        groups=[[1, 2], [3, 4]],
        bound=9,
        top_id=50,
    )
