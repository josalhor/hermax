from hermax.internal import _encoding_policy as policy
import itertools
import pytest
from hermax.encoder import _weighted_sum as weighted


@pytest.mark.parametrize('weights',[(3,6,9,12),(7,11,13,17),(5,5,5,5)])
@pytest.mark.parametrize('groups',[(),((1,2),),((1,2,3,4),)])
def test_candidates_agree_with_independent_reachable_sums(weights,groups):
    expected=set()
    for values in itertools.product((False,True),repeat=4):
        if all(sum(values[i-1] for i in group)==1 for group in groups):
            expected.add(sum(w*v for w,v in zip(weights,values)))
    plans=weighted.plan_candidates([1,2,3,4],weights,sum(weights),groups)
    assert plans
    for plan in plans:
        assert weighted.reachable_values(plan)==tuple(sorted(expected))


def test_dense_reachability_decodes_across_byte_boundaries():
    weights=[1<<i for i in range(12)]
    plan=weighted.plan_candidates(list(range(1,13)),weights,sum(weights))[0]
    assert weighted.reachable_values(plan)==tuple(range(4096))


def test_growth_limits_are_inclusive(monkeypatch):
    plans = weighted.plan_candidates([1, 2], [2, 3], 5)
    # Prefix states: 1 + 2 + 4; transitions: 2 + 4.
    monkeypatch.setattr(policy, 'STATE_LIMIT', 7)
    monkeypatch.setattr(policy, 'CLAUSE_LIMIT', 53)
    accepted, values = weighted.bounded_candidates(plans)
    assert accepted == plans and values == (0, 2, 3, 5)
    monkeypatch.setattr(policy, 'STATE_LIMIT', 6)
    assert weighted.bounded_candidates(plans) == ((), ())
    monkeypatch.setattr(policy, 'STATE_LIMIT', 7)
    monkeypatch.setattr(policy, 'CLAUSE_LIMIT', 52)
    assert weighted.bounded_candidates(plans) == ((), ())
