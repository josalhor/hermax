import pytest

from hermax.encoder.card import CardEnc, ITotalizer
from hermax.encoder.pb_enc import EncType as PBEncType, PBEnc


def test_cardinality_encoder_rejects_boolean_literals():
    with pytest.raises((TypeError, ValueError)):
        CardEnc.atmost([True], bound=1)


def test_cardinality_encoder_rejects_boolean_bounds():
    with pytest.raises((TypeError, ValueError)):
        CardEnc.atmost([], bound=True)


def test_pb_encoder_rejects_boolean_literals():
    with pytest.raises((TypeError, ValueError)):
        PBEnc.leq([True], weights=[1], bound=1)


def test_pb_encoder_rejects_boolean_weights_and_bounds():
    with pytest.raises((TypeError, ValueError)):
        PBEnc.leq([1], weights=[True], bound=True)


def test_pb_encoder_rejects_zero_literals():
    with pytest.raises((TypeError, ValueError)):
        PBEnc.leq([0], weights=[1], bound=1)


def test_pb_encoder_rejects_negative_weights():
    with pytest.raises((TypeError, ValueError)):
        PBEnc.leq([1], weights=[-1], bound=0)


def test_native_pb_encoder_does_not_ignore_conditionals():
    with pytest.raises((TypeError, ValueError, NotImplementedError)):
        PBEnc.leq(
            [1],
            weights=[1],
            bound=0,
            encoding=PBEncType.native,
            conditionals=[2],
        )


def test_pb_encoder_accepts_weighted_literal_pairs_without_separate_weights():
    cnf = PBEnc.leq([(1, 2), (2, 3)], bound=3)
    assert cnf.clauses or cnf.atmosts


def test_cardinality_encoder_accepts_one_shot_literal_iterables():
    cnf = CardEnc.atmost(
        (literal for literal in [1, 2, 3, 4]),
        bound=2,
        encoding=1,
    )
    assert cnf.clauses or cnf.atmosts


def test_pb_encoder_accepts_one_shot_literal_and_weight_iterables():
    cnf = PBEnc.leq(
        (literal for literal in [1, 2, 3]),
        weights=(weight for weight in [1, 2, 3]),
        bound=2,
    )
    assert cnf.clauses or cnf.atmosts


def test_itotalizer_rejects_boolean_literals():
    with pytest.raises((TypeError, ValueError)):
        ITotalizer(lits=[True], ubound=1)


@pytest.mark.parametrize("ubound", [True, -1])
def test_itotalizer_rejects_invalid_upper_bounds(ubound):
    with pytest.raises((TypeError, ValueError)):
        ITotalizer(lits=[1], ubound=ubound)
