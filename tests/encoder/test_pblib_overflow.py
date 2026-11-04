import pytest

from hermax.encoder.pb_enc import PBEnc, EncType
from hermax.encoder._packed import PBEnc as PackedPBEnc
from hermax.internal import _pblib


@pytest.mark.parametrize("encoder", [PBEnc, PackedPBEnc])
def test_coefficient_overflow_is_rejected(encoder):
    w = 2**62
    for method in (encoder.leq, encoder.geq, encoder.equals):
        with pytest.raises(OverflowError):
            method([1, 2], [w, w + 1], bound=w + 1, encoding=EncType.bdd)
    with pytest.raises(OverflowError):
        encoder.leq([1, 1], [w, w], bound=w, encoding=EncType.bdd)


@pytest.mark.parametrize("encoder", [PBEnc, PackedPBEnc])
def test_auxiliary_variable_exhaustion_is_rejected(encoder):
    with pytest.raises(OverflowError):
        encoder.leq([1, 2, 3], [2, 3, 4], bound=4,
                    top_id=2**31 - 1, encoding=EncType.bdd)
    # A constraint that requires no auxiliaries is still valid at the limit.
    cnf = encoder.leq([1], [1], bound=1, top_id=2**31 - 1)
    assert cnf.nv == 2**31 - 1
    assert not cnf.clauses


def test_native_literal_ids_are_checked_before_narrowing():
    kwargs = dict(wlits=[(1, 2), (2, 3)], comparator=_pblib.LEQ,
                  bound=3, top_id=2, pb_encoder=_pblib.PB_BDD, conditionals=[])
    with pytest.raises(ValueError):
        _pblib.encode_pb(**{**kwargs, "wlits": [(2**32 + 1, 2), (2, 3)]})
    with pytest.raises(ValueError):
        _pblib.encode_pb(**{**kwargs, "conditionals": [2**32 + 1]})
