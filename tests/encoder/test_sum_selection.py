"""Selection compares actual CNFs, with deterministic ties and private IDs."""
from unittest.mock import patch

import pytest

from hermax.encoder._weighted_sum.common import CNFBuilder
from hermax.encoder._weighted_sum import encode_best, plan_candidates, encode_candidate


@pytest.mark.parametrize('left,right,expected', [
    (CNFBuilder([(1,)], 20), CNFBuilder([(1,), (2,)], 10), 0),
    (CNFBuilder([(1,), (2,)], 10), CNFBuilder([(1,)], 20), 1),
    (CNFBuilder([(1,)], 20), CNFBuilder([(1,)], 10), 1),
    (CNFBuilder([(1,)], 10), CNFBuilder([(2,)], 10), 0),
])
def test_actual_clause_counts_then_variables_then_candidate_order(left, right, expected):
    candidates = (left, right)
    with patch('hermax.encoder._weighted_sum.encode_candidate', side_effect=candidates) as encode:
        assert encode_best(('original', 'grouped'), [1, 2], 5) is candidates[expected]
    assert encode.call_args_list[0].args[2] == encode.call_args_list[1].args[2] == 5


@pytest.mark.parametrize('weights', [(1, 2)*4, (2,)*8, (3, 5, 7), (2, 3, 2, 3, 2)])
def test_selection_matches_independent_construction(weights):
    inputs = list(range(1, len(weights)+1))
    thresholds = list(range(len(inputs)+1, len(inputs)+sum(weights)+1))
    plans = plan_candidates(inputs, weights, sum(weights))
    candidates = [encode_candidate(plan, thresholds, thresholds[-1]) for plan in plans]
    expected = min(candidates, key=lambda cnf: (len(cnf.clauses), cnf.nv))
    assert encode_best(plans, thresholds, thresholds[-1]) == expected


def test_no_candidates_is_read_only():
    assert encode_best((), [1, 2], 2) is None
