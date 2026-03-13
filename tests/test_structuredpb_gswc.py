from __future__ import annotations

import random

import pytest

from tests.structuredpb_test_utils import assert_encoding_matches_oracle_and_baseline, case_id, partition_lits


GSWC_CASES = [
    {"name": "zero-bound-many-groups", "lits": [1, 2, 3, 4, 5], "weights": [1, 2, 3, 4, 5], "groups": [[1], [2], [3], [4], [5]], "bound": 0},
    {"name": "single-heavy-group", "lits": [1, 2, 3, 4], "weights": [3, 9, 6, 2], "groups": [[1, 2, 3], [4]], "bound": 8},
    {"name": "balanced-mid-k", "lits": [1, 2, 3, 4, 5, 6], "weights": [2, 7, 5, 6, 3, 4], "groups": [[1, 2], [3, 4], [5, 6]], "bound": 11},
    {"name": "equal-weights", "lits": [1, 2, 3, 4, 5, 6], "weights": [4, 4, 4, 4, 4, 4], "groups": [[1, 2], [3], [4, 5], [6]], "bound": 8},
    {"name": "two-weight-tight", "lits": [1, 2, 3, 4, 5, 6], "weights": [2, 9, 2, 9, 2, 9], "groups": [[1, 2], [3, 4], [5, 6]], "bound": 10},
    {"name": "loose-bound", "lits": [1, 2, 3, 4, 5], "weights": [5, 6, 7, 8, 9], "groups": [[1, 2], [3], [4, 5]], "bound": 20},
    {"name": "asymmetric", "lits": [1, 2, 3, 4, 5, 6, 7], "weights": [8, 1, 5, 2, 6, 3, 7], "groups": [[1], [2, 3, 4], [5, 6], [7]], "bound": 13},
    {"name": "small-hugew", "lits": [1, 2, 3, 4], "weights": [500, 700, 900, 1100], "groups": [[1, 2], [3, 4]], "bound": 1400},
]


@pytest.mark.parametrize("case", GSWC_CASES, ids=case_id)
def test_gswc_edge_cases(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str, case: dict[str, object]) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="gswc",
        lits=case["lits"],
        weights=case["weights"],
        groups=case["groups"],
        bound=case["bound"],
    )


def test_gswc_small_random_smoke(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    rng = random.Random(0x47535743)
    for _ in range(6):
        n = rng.randint(3, 7)
        lits = list(range(1, n + 1))
        groups = partition_lits(rng, lits)
        weights = [rng.randint(1, 12) for _ in range(n)]
        bound = rng.randint(0, sum(weights))
        assert_encoding_matches_oracle_and_baseline(
            structuredpb_module=structuredpb_module,
            pb_baseline=pb_baseline,
            card_baseline=card_baseline,
            sat_solver_name=sat_solver_name,
            encoding_name="gswc",
            lits=lits,
            weights=weights,
            groups=groups,
            bound=bound,
        )


def test_gswc_handles_high_top_id(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="gswc",
        lits=[1, 2, 3, 4, 5],
        weights=[2, 4, 6, 8, 10],
        groups=[[1, 2], [3], [4, 5]],
        bound=12,
        top_id=60,
    )
