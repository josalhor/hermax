import pytest

from hermax.encoder.pbamo import PBAMOEnc
from hermax.internal.kmerge import PBConstraintStub


@pytest.mark.parametrize(
    ("lits", "weights", "groups"),
    [
        ([1, 2], [1, 1], [[1, 3]]),  # references a literal outside the PB terms
        ([1, 2], [1, 1], [[0, 1]]),  # contains an invalid DIMACS literal
        ([1, 2], [1, 1], [[1, 1]]),  # does not form a partition
        ([1, 2], [1, 1], [[]]),  # empty group
    ],
)
def test_pbamo_rejects_malformed_group_partitions(lits, weights, groups):
    with pytest.raises((TypeError, ValueError), match="group|partition|literal"):
        PBAMOEnc.leq(
            lits=lits,
            weights=weights,
            groups=groups,
            bound=1,
            encoding="rggt",
        )


def test_pbamo_rejects_duplicate_weighted_literals():
    with pytest.raises((TypeError, ValueError), match="duplicate|literal|terms"):
        PBAMOEnc.leq(
            lits=[1, 1],
            weights=[1, 1],
            groups=[[1], [2]],
            bound=1,
            encoding="rggt",
        )


@pytest.mark.parametrize("method", ["auto_leq", "auto_eq"])
def test_pbamo_auto_methods_reject_invalid_explicit_groups(method):
    with pytest.raises((TypeError, ValueError), match="group|partition|literal"):
        getattr(PBAMOEnc, method)(
            lits=[1, 2],
            weights=[1, 1],
            groups=[[1, 3]],
            bound=1,
        )


def test_pbamo_multi_leq_rejects_misaligned_stub_literals():
    with pytest.raises((TypeError, ValueError), match="literal|core|align"):
        PBAMOEnc.multi_leq(
            lits=[1, 2],
            stubs=[PBConstraintStub(lits=(1, 3), weights=(2, 2), bound=2, op="<=")],
            top_id=2,
        )
