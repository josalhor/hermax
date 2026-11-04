import itertools

import pytest
from pysat.solvers import Solver

from hermax.encoder.pb_enc import EncType, PBEnc


@pytest.mark.parametrize("encoding", [EncType.binmerge, EncType.lpw])
def test_binary_merge_large_weights(encoding):
    b = 2**55
    weights = [b + 7, b - 1, b + 9]
    cnf = PBEnc.leq([1, 2, 3], weights, bound=b + 9, encoding=encoding)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for bits in itertools.product((False, True), repeat=3):
            assumptions = [i if bit else -i for i, bit in enumerate(bits, 1)]
            assert solver.solve(assumptions=assumptions) == (
                sum(w for w, bit in zip(weights, bits) if bit) <= b + 9
            )


def test_binary_merge_large_sorting_threshold():
    b = 2**29
    weights = [b - 13, b + 14, b - 11, b + 5, b + 12, b - 10]
    cnf = PBEnc.leq(range(1, 7), weights, bound=3*b + 1, encoding=EncType.binmerge)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        for bits in itertools.product((False, True), repeat=6):
            assumptions = [i if bit else -i for i, bit in enumerate(bits, 1)]
            assert solver.solve(assumptions=assumptions) == (
                sum(w for w, bit in zip(weights, bits) if bit) <= 3*b + 1
            )


def test_lpw_rejects_large_weight_overflow():
    b = 2**55
    weights = [b - 14, b + 10, b + 4, b - 10, b - 4, b - 6]
    cnf = PBEnc.leq(range(1, 7), weights, bound=4*b - 6, encoding=EncType.lpw)
    with Solver(bootstrap_with=cnf.clauses) as solver:
        assert not solver.solve(assumptions=[1, 2, 3, -4, 5, -6])


def test_counters_and_adders_avoid_unused_outputs():
    counter = PBEnc.leq(range(1, 21), [1, 2, 3, 4]*5, bound=20,
                        encoding=EncType.seqcounter)
    assert counter.nv - 20 < 400
    assert len(counter.clauses) < 799

    adder = PBEnc.leq(range(1, 33), [i % 9 + 1 for i in range(32)], bound=127,
                      encoding=EncType.adder)
    assert adder.nv - 32 < 96
    assert len(adder.clauses) < 909
