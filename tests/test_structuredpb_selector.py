from __future__ import annotations

from tests.structuredpb_test_utils import assert_encoding_matches_oracle_and_baseline


def test_structuredpb_best_uses_hardcoded_stage2_rule(structuredpb_module) -> None:
    assert structuredpb_module.choose_encoding([1, 2, 3], [5, 7, 9], [[1, 2], [3]], 20) == structuredpb_module.EncType.mdd
    assert structuredpb_module.choose_encoding([1, 2, 3], [5, 70, 9], [[1, 2], [3]], 10) == structuredpb_module.EncType.rggt
    assert (
        structuredpb_module.choose_encoding(
            list(range(1, 30)),
            [100] * 29,
            [[1, 2], *[[i] for i in range(3, 30)]],
            1000,
        )
        == structuredpb_module.EncType.ggpw
    )


def test_structuredpb_available_encoders_include_new_ones(structuredpb_module) -> None:
    names = set(structuredpb_module.available_encoders())
    assert {"best", "mdd", "gswc", "ggpw", "gmto", "rggt"} <= names


def test_structuredpb_best_smoke_matches_baseline(
    structuredpb_module, pb_baseline, card_baseline, sat_solver_name: str
) -> None:
    assert_encoding_matches_oracle_and_baseline(
        structuredpb_module=structuredpb_module,
        pb_baseline=pb_baseline,
        card_baseline=card_baseline,
        sat_solver_name=sat_solver_name,
        encoding_name="best",
        lits=[1, 2, 3, 4],
        weights=[2, 9, 3, 7],
        groups=[[1, 2], [3], [4]],
        bound=10,
    )
