import pytest
from pysat.formula import IDPool
from pysat.solvers import Solver

from hermax.encoder.pb_enc import EncType, PBEnc


def test_pb_encoder_handles_occupied_id_pool_ranges_with_auxiliaries():
    pool = IDPool()
    pool.top = 4
    pool.occupy(9, 11)

    cnf = PBEnc.leq(
        lits=[1, 2, 3, 4],
        weights=[1, 1, 1, 1],
        bound=2,
        vpool=pool,
        encoding=EncType.bdd,
    )

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        assert solver.solve(assumptions=[1, 2, -3, -4])
        assert not solver.solve(assumptions=[1, 2, 3, -4])
