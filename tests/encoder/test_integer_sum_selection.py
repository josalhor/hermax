"""Frozen calibration examples exercise every learned selector leaf."""
import pytest

from hermax.encoder._integer_sum import LEAF, assess, selection


@pytest.mark.parametrize(
    "widths,bound,cached,orientations,expected",
    [
        ([4] * 4, 1, [False] * 4, [1] * 4, "binary"),
        ([4] * 4, 8, [False] * 4, [-1] * 4, "whole"),
        ([4] * 4, 14, [False] * 4, [-1] * 4, "binary"),
        ([32] * 4, 12, [False] * 4, [1] * 4, "whole"),
        ([32] * 4, 12, [True] * 4, [1] * 4, "binary"),
        ([32] * 4, 115, [False] * 4, [1, -1, 1, -1], "binary"),
        ([32] * 8, 25, [False] * 8, [1] * 8, "whole"),
        (
            [32] * 16,
            460,
            [True] * 16,
            [-1, 1, -1, -1, 1, -1, -1, -1, 1, 1, -1, 1, 1, -1, 1, -1],
            "whole",
        ),
        ([480] * 16, 768, [False] * 16, [1] * 16, "whole"),
        (
            [480] * 16,
            6912,
            [False] * 16,
            [1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1, -1, -1, -1, -1, 1],
            "binary",
        ),
        (
            [1, 1, 1, 1, 1, 1, 4, 1],
            5,
            [True, True, True, True, True, True, False, True],
            [-1] * 8,
            "binary",
        ),
    ],
)
def test_calibrated_decisions(widths, bound, cached, orientations, expected):
    costs = assess(widths, bound)
    for _ in range(2):
        assert (
            selection.choose(widths, bound, costs, cached, orientations=orientations)
            == expected
        )


@pytest.mark.parametrize(
    "widths,bound", [([3, 4, 5, 6], 0), ([3, 4, 5, 6], 17), ([8], 3), ([1, 1, 1, 1], 2)]
)
def test_direct_or_boolean_cases_use_leaf(widths, bound):
    assert selection.choose(widths, bound, assess(widths, bound)) == LEAF
