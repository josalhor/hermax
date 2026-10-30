from unittest.mock import patch

import pytest

from hermax.encoder import _weighted_sum
from hermax.encoder._integer_sum import weighted
from hermax.internal import _encoding_policy as policy
from hermax.internal import _integer_sum_native as native
from hermax.model import _integer_sum


@pytest.mark.parametrize("clauses,states,exceeds", [(40000, 20000, False), (40001, 0, True), (0, 20001, True)])
def test_shared_defaults_are_inclusive(clauses, states, exceeds):
    assert policy.exceeds_limits(clauses=clauses, states=states) == exceeds


def test_zero_disables_each_limit_independently(monkeypatch):
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 0)
    assert not policy.exceeds_limits(clauses=1000000)
    assert policy.exceeds_limits(states=20001)
    monkeypatch.setattr(policy, "STATE_LIMIT", 0)
    assert not policy.exceeds_limits(clauses=1000000, states=1000000)


def test_policy_changes_reach_estimators_and_native_encoder(monkeypatch):
    monkeypatch.setattr(policy, "STATE_LIMIT", 7)
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 53)
    plans = _weighted_sum.plan_candidates([1, 2], [2, 3], 5)
    assert _weighted_sum.bounded_candidates(plans)[0] == plans
    assert _integer_sum.addition_encoding(1, 1, 2, 0, equality=True) == "merge"
    with patch.object(native, "_encode_pb_packed", wraps=native._encode_pb_packed) as encode:
        weighted.encode_thresholds([[1], [2]], [2, 3], 3, "<=", 2, _packed=True)
        assert encode.call_args.kwargs["state_limit"] == 7
        assert encode.call_args.kwargs["clause_limit"] == 53
    monkeypatch.setattr(policy, "CLAUSE_LIMIT", 13)
    assert _weighted_sum.bounded_candidates(plans) == ((), ())
    assert _integer_sum.addition_encoding(1, 1, 2, 0, equality=True) == "general"
