"""Frozen grouping decisions from before the preprocessing refactor."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest


BASELINE = Path(__file__).parent / "data" / "pbamo_partition_baseline.jsonl"
CASES = [json.loads(line) for line in BASELINE.read_text().splitlines()]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_partition_decisions_are_unchanged(pbamo_module, case):
    kwargs = deepcopy(case["input"])
    before = deepcopy(kwargs)

    actual = pbamo_module.choose_overlap_partition(**kwargs)

    assert actual == case["partition"]  # Includes group order and tie-breaking.
    assert kwargs == before


def test_partition_preparation_does_not_keep_stale_results(pbamo_module):
    # Reuse caller-owned containers across different weights, candidates,
    # policies, and signed literal sets. Also mutate the previous result.
    # A process-wide cache keyed by object identity would be incorrect.
    shared = {}
    for case in [*CASES, *reversed(CASES)]:
        for key, value in case["input"].items():
            if isinstance(value, list) and isinstance(shared.get(key), list):
                shared[key][:] = deepcopy(value)
            else:
                shared[key] = deepcopy(value)
        actual = pbamo_module.choose_overlap_partition(**shared)
        assert actual == case["partition"]
        if actual:
            actual[0].append(999999)
