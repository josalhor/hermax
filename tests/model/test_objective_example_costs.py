"""Small example optima checked independently of objective lowering."""
from pathlib import Path
import re
import os
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "example,field,expected",
    [
        ("01_toy_soft_clauses.py", "cost", 0),
        ("02_knapsack_pb.py", "cost", 15),
        ("03_set_cover.py", "cost", 4),
        ("04_vertex_cover.py", "cost", 4),
        ("05_job_assignment.py", "cost", 5),
        ("06_enum_subset_shift.py", "cost", 1),
        ("11_int_objective.py", "cost", 12),
        ("12_wifi_nullable_enum.py", "cost", 4),
        ("17_big_m_indicator_capacity.py", "load =", 12),
        ("23_optional_assignment.py", "cost", 4),
        ("24_facility_location.py", "cost", 10),
        ("27_bin_packing.py", "bins_used", 2),
        ("28_maximum_clique.py", "size", 4),
        ("29_float_objective_budgeting.py", "missed_roi_usd_millions", 3.35),
    ],
)
def test_example_retains_its_intended_cost(example, field, expected):
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "model" / example)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=8,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
        },
    )
    assert result.returncode == 0, result.stderr
    separator = "" if field.endswith("=") else ":"
    match = re.search(
        r"^" + re.escape(field + separator) + r"\s*(-?\d+(?:\.\d+)?)",
        result.stdout,
        re.MULTILINE,
    )
    assert match, result.stdout
    assert float(match.group(1)) == pytest.approx(expected)
    if example == "06_enum_subset_shift.py":
        assert re.search(r"^shift:\s*day$", result.stdout, re.MULTILINE)
