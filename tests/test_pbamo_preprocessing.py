"""Behavior and work budgets for structured PB preprocessing.

Count operations rather than depending on machine-specific timings.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pysat.solvers import Solver


DATA = Path(__file__).parent / "data"


def _records(filename):
    return [json.loads(line) for line in (DATA / filename).read_text().splitlines()]


def _overlap_input(unit_weights=False):
    return dict(
        lits=list(range(1, 13)),
        weights=[1] * 12 if unit_weights else [3, 7, 4, 8, 5, 9, 6, 10, 7, 11, 8, 12],
        bound=3 if unit_weights else 35,
        amo_groups=[[1, 2, 3], [2, 3, 4], [5, 6], [6, 7, 8]],
        eo_groups=[[9, 10, 11, 12]],
        top_id=40,
    )


@pytest.mark.parametrize("operation", ["auto_leq", "auto_eq"])
@pytest.mark.parametrize("unit_weights", [False, True])
def test_one_partition_preparation_per_encoding(monkeypatch, pbamo_module, operation, unit_weights):
    spy = Mock(wraps=pbamo_module.choose_overlap_partition)
    monkeypatch.setattr(pbamo_module, "choose_overlap_partition", spy)

    getattr(pbamo_module.PBAMOEnc, operation)(**_overlap_input(unit_weights))

    assert spy.call_count == 1, "Reuse the prepared partition within this encoding call."


@pytest.mark.parametrize("operation", ["auto_leq", "auto_eq"])
def test_explicit_partition_never_runs_overlap_search(monkeypatch, pbamo_module, operation):
    spy = Mock(wraps=pbamo_module.choose_overlap_partition)
    monkeypatch.setattr(pbamo_module, "choose_overlap_partition", spy)
    kwargs = _overlap_input()
    kwargs.pop("amo_groups")
    kwargs.pop("eo_groups")
    kwargs["groups"] = [list(range(i, i + 3)) for i in range(1, 13, 3)]

    getattr(pbamo_module.PBAMOEnc, operation)(**kwargs)

    spy.assert_not_called()


@pytest.mark.parametrize("size", [12, 24])
def test_static_pair_scores_are_not_recomputed_cubically(monkeypatch, pbamo_module, size):
    spy = Mock(wraps=pbamo_module._pair_score)
    monkeypatch.setattr(pbamo_module, "_pair_score", spy)

    pbamo_module.choose_overlap_partition(list(range(1, size + 1)), [2] * size)

    # No edges: dynamic group scoring cannot account for cubic pair-score work.
    assert spy.call_count <= 8 * size * size, "Compute fixed support degrees once."


@pytest.mark.parametrize("policy", ["baseline_paper", "paper_best_fit_dynamic_future"])
def test_isolated_literals_skip_impossible_group_searches(monkeypatch, pbamo_module, policy):
    original = pbamo_module._group_is_compatible
    isolated_attempts = []

    def checked(neighbors, lit, group):
        if not neighbors.get(lit) and group:
            isolated_attempts.append((lit, tuple(group)))
        return original(neighbors, lit, group)

    monkeypatch.setattr(pbamo_module, "_group_is_compatible", checked)
    pbamo_module.choose_overlap_partition(
        list(range(1, 13)), [2] * 12, amo_groups=[[1, 2, 3]], policy=policy,
    )

    assert isolated_attempts == [], "A literal with no mutex neighbors must stay alone."


@pytest.mark.parametrize("operation", ["auto_leq", "auto_eq"])
@pytest.mark.parametrize("unit_weights", [False, True])
def test_encoding_does_not_mutate_caller_inputs(pbamo_module, operation, unit_weights):
    kwargs = _overlap_input(unit_weights)
    before = deepcopy(kwargs)

    getattr(pbamo_module.PBAMOEnc, operation)(**kwargs)

    assert kwargs == before


@pytest.mark.parametrize(
    "record", _records("pbamo_preprocessing_cnf.jsonl"), ids=lambda row: row["name"],
)
def test_preprocessing_preserves_exact_existing_cnf(pbamo_module, record):
    # These snapshots test preprocessing with the original RGGT backend,
    # independently of changes to the automatic encoder selector.
    cnf = getattr(pbamo_module.PBAMOEnc, record["operation"])(
        **record["input"], structured_encoding=pbamo_module.EncType.rggt,
    )
    serialized = json.dumps(cnf.clauses, separators=(",", ":")).encode()

    assert cnf.nv == record["variables"]
    assert len(cnf.clauses) == record["clauses"]
    assert hashlib.sha256(serialized).hexdigest() == record["sha256"]


@pytest.mark.parametrize("operation", ["auto_leq", "auto_eq"])
@pytest.mark.parametrize("unit_weights", [False, True])
@pytest.mark.parametrize("signed", [False, True])
def test_original_group_constraints_survive_partition_reuse(
    pbamo_module, sat_solver_name, operation, unit_weights, signed,
):
    # These overlapping candidates cannot all be retained in one partition.
    # Both AMO and EO must still be enforced, and EO must not be reused on
    # the equality's negated lower side.
    lits = [1, -2, 3, -4, 5] if signed else [1, 2, 3, 4, 5]
    weights = [1] * 5 if unit_weights else [0, 2, 3, 4, 5]
    amo = [[lits[0], lits[1], lits[2]], [lits[2], lits[3]]]
    eo = [[lits[1], lits[3], lits[4]]]
    bound = 1 if unit_weights else 5
    cnf = getattr(pbamo_module.PBAMOEnc, operation)(
        lits=lits, weights=weights, bound=bound, amo_groups=amo, eo_groups=eo,
        top_id=20,
    )

    feasible = 0
    with Solver(name=sat_solver_name, bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product((False, True), repeat=len(lits)):
            true = {lit for lit, value in zip(lits, values) if value}
            total = sum(w for w, value in zip(weights, values) if value)
            relation = total == bound if operation == "auto_eq" else total <= bound
            expected = (
                relation
                and all(sum(lit in true for lit in group) <= 1 for group in amo)
                and all(sum(lit in true for lit in group) == 1 for group in eo)
            )
            assumptions = [lit if value else -lit for lit, value in zip(lits, values)]
            assert solver.solve(assumptions=assumptions) == expected, values
            feasible += expected
    assert feasible, "The test must exercise satisfying assignments too."
