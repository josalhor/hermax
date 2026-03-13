from __future__ import annotations

import random

import pytest

from tests.structuredpb_test_utils import assert_encoding_matches_oracle_and_baseline, case_id, partition_lits


GMTO_CASES = [
    {"name": "divisible-chain", "lits": [1, 2, 3, 4], "weights": [6, 12, 18, 24], "groups": [[1, 2], [3, 4]], "bound": 24},
    {"name": "mixed-radix-friendly", "lits": [1, 2, 3, 4, 5], "weights": [4, 8, 12, 20, 28], "groups": [[1, 2], [3], [4, 5]], "bound": 24},
    {"name": "digit-sharing-in-group", "lits": [1, 2, 3, 4], "weights": [5, 9, 13, 17], "groups": [[1, 2], [3, 4]], "bound": 18},
    {"name": "hugew-divisible", "lits": [1, 2, 3, 4], "weights": [960, 1920, 2880, 3840], "groups": [[1, 2], [3, 4]], "bound": 3840},
    {"name": "two-weight-digits", "lits": [1, 2, 3, 4, 5, 6], "weights": [9, 27, 9, 27, 9, 27], "groups": [[1, 2], [3, 4], [5, 6]], "bound": 36},
    {"name": "tight-small-groups", "lits": [1, 2, 3, 4, 5], "weights": [7, 11, 19, 23, 31], "groups": [[1], [2, 3], [4, 5]], "bound": 30},
    {"name": "loose-mid-groups", "lits": [1, 2, 3, 4, 5, 6], "weights": [10, 15, 20, 25, 30, 35], "groups": [[1, 2, 3], [4], [5, 6]], "bound": 60},
    {"name": "bound-zero-collapse", "lits": [1, 2, 3], "weights": [8, 16, 24], "groups": [[1, 2], [3]], "bound": 0},
]


@pytest.mark.parametrize("case", GMTO_CASES, ids=case_id)
def test_gmto_edge_cases(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str, case: dict[str, object]) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="gmto",
        lits=case["lits"],
        weights=case["weights"],
        groups=case["groups"],
        bound=case["bound"],
    )


def test_gmto_small_random_smoke(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    rng = random.Random(0x474D544F)
    for _ in range(6):
        n = rng.randint(3, 7)
        lits = list(range(1, n + 1))
        groups = partition_lits(rng, lits)
        weights = [rng.randint(2, 40) * rng.choice([1, 2, 3, 4]) for _ in range(n)]
        bound = rng.randint(0, sum(weights))
        assert_encoding_matches_oracle_and_baseline(
            structuredpb_module=structuredpb_module,
            pb_baseline=pb_baseline,
            card_baseline=card_baseline,
            sat_solver_name=sat_solver_name,
            encoding_name="gmto",
            lits=lits,
            weights=weights,
            groups=groups,
            bound=bound,
        )


def test_gmto_handles_high_top_id(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="gmto",
        lits=[1, 2, 3, 4, 5],
        weights=[12, 24, 36, 48, 60],
        groups=[[1, 2], [3], [4, 5]],
        bound=60,
        top_id=80,
    )
