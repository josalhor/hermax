from __future__ import annotations

import random

import pytest

from tests.structuredpb_test_utils import assert_encoding_matches_oracle_and_baseline, case_id, partition_lits


GGPW_CASES = [
    {"name": "hugew-tight-balanced", "lits": [1, 2, 3, 4], "weights": [900, 1200, 1500, 1800], "groups": [[1, 2], [3, 4]], "bound": 1900},
    {"name": "hugew-loose-many-groups", "lits": [1, 2, 3, 4, 5], "weights": [400, 700, 900, 1100, 1300], "groups": [[1], [2], [3], [4], [5]], "bound": 2700},
    {"name": "repeated-hugew", "lits": [1, 2, 3, 4, 5, 6], "weights": [2000, 2000, 4000, 4000, 8000, 8000], "groups": [[1, 2], [3, 4], [5, 6]], "bound": 10000},
    {"name": "two-weight-hugew", "lits": [1, 2, 3, 4, 5, 6], "weights": [1024, 4096, 1024, 4096, 1024, 4096], "groups": [[1, 2], [3, 4], [5, 6]], "bound": 5120},
    {"name": "mid-k-digit-carry", "lits": [1, 2, 3, 4], "weights": [255, 511, 513, 1023], "groups": [[1, 2], [3, 4]], "bound": 1024},
    {"name": "small-n-large-coeffs", "lits": [1, 2, 3], "weights": [5000, 7000, 9000], "groups": [[1, 2], [3]], "bound": 9000},
    {"name": "mixed-hugew-tight", "lits": [1, 2, 3, 4, 5], "weights": [300, 1700, 2900, 4100, 5300], "groups": [[1, 2], [3], [4, 5]], "bound": 5600},
    {"name": "balanced-mid-hugew", "lits": [1, 2, 3, 4, 5, 6], "weights": [600, 900, 1500, 2100, 3300, 3900], "groups": [[1, 2], [3, 4], [5, 6]], "bound": 4200},
]


@pytest.mark.parametrize("case", GGPW_CASES, ids=case_id)
def test_ggpw_edge_cases(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str, case: dict[str, object]) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="ggpw",
        lits=case["lits"],
        weights=case["weights"],
        groups=case["groups"],
        bound=case["bound"],
    )


def test_ggpw_small_random_smoke(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    rng = random.Random(0x47475057)
    for _ in range(6):
        n = rng.randint(3, 7)
        lits = list(range(1, n + 1))
        groups = partition_lits(rng, lits)
        weights = [rng.randint(50, 5000) for _ in range(n)]
        bound = rng.randint(0, sum(weights))
        assert_encoding_matches_oracle_and_baseline(
            structuredpb_module=structuredpb_module,
            pb_baseline=pb_baseline,
            card_baseline=card_baseline,
            sat_solver_name=sat_solver_name,
            encoding_name="ggpw",
            lits=lits,
            weights=weights,
            groups=groups,
            bound=bound,
        )


def test_ggpw_handles_high_top_id(structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="ggpw",
        lits=[1, 2, 3, 4],
        weights=[700, 1100, 1300, 1700],
        groups=[[1, 2], [3, 4]],
        bound=1800,
        top_id=70,
    )
