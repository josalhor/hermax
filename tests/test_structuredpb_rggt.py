from __future__ import annotations

import random

import pytest

from tests.structuredpb_test_utils import assert_encoding_matches_oracle_and_baseline, case_id, partition_lits


RGGT_CASES = [
    {"name": "close-coefficients", "lits": [1, 2, 3, 4], "weights": [20, 30, 20, 40], "groups": [[1, 2], [3, 4]], "bound": 55},
    {"name": "irrelevant-small-term", "lits": [1, 2, 3, 4, 5], "weights": [20, 30, 20, 40, 1], "groups": [[1, 2], [3, 4], [5]], "bound": 55},
    {"name": "many-nearby-values", "lits": [1, 2, 3, 4, 5, 6], "weights": [9, 10, 11, 12, 13, 14], "groups": [[1, 2], [3, 4], [5, 6]], "bound": 24},
    {"name": "repeated-values-across-groups", "lits": [1, 2, 3, 4, 5, 6], "weights": [6, 10, 6, 10, 6, 10], "groups": [[1, 2], [3, 4], [5, 6]], "bound": 18},
    {"name": "few-groups-loose", "lits": [1, 2, 3, 4, 5, 6], "weights": [8, 12, 16, 20, 24, 28], "groups": [[1, 2, 3], [4, 5, 6]], "bound": 36},
    {"name": "tight-asymmetric", "lits": [1, 2, 3, 4, 5], "weights": [4, 11, 18, 19, 27], "groups": [[1, 2, 3], [4], [5]], "bound": 22},
    {"name": "zero-bound", "lits": [1, 2, 3, 4], "weights": [3, 5, 7, 9], "groups": [[1, 2], [3, 4]], "bound": 0},
    {"name": "small-hugew-close", "lits": [1, 2, 3, 4], "weights": [1000, 1010, 1020, 1030], "groups": [[1, 2], [3, 4]], "bound": 2020},
]


@pytest.mark.parametrize("case", RGGT_CASES, ids=case_id)
def test_rggt_edge_cases(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str, case: dict[str, object]) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="rggt",
        lits=case["lits"],
        weights=case["weights"],
        groups=case["groups"],
        bound=case["bound"],
    )


def test_rggt_small_random_smoke(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    rng = random.Random(0x52474754)
    for _ in range(6):
        n = rng.randint(3, 7)
        lits = list(range(1, n + 1))
        groups = partition_lits(rng, lits)
        base = rng.randint(2, 10)
        weights = [base + rng.randint(0, 4) for _ in range(n)]
        bound = rng.randint(0, sum(weights))
        assert_encoding_matches_oracle_and_baseline(
            structuredpb_module=structuredpb_module,
            pb_baseline=pb_baseline,
            card_baseline=card_baseline,
            sat_solver_name=sat_solver_name,
            encoding_name="rggt",
            lits=lits,
            weights=weights,
            groups=groups,
            bound=bound,
        )


def test_rggt_handles_high_top_id(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="rggt",
        lits=[1, 2, 3, 4, 5],
        weights=[10, 20, 21, 31, 32],
        groups=[[1, 2], [3, 4], [5]],
        bound=41,
        top_id=90,
    )
