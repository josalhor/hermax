from pysat.solvers import Solver

from hermax.encoder.pb_enc import EncType, PBEnc


def _is_sat(cnf, assumptions=()):
    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        return solver.solve(assumptions=list(assumptions))


def test_empty_pb_sum_uses_comparator_semantics():
    assert _is_sat(PBEnc.leq([], weights=[], bound=0, encoding=EncType.adder))
    assert _is_sat(PBEnc.leq([], weights=[], bound=7, encoding=EncType.adder))
    assert _is_sat(PBEnc.geq([], weights=[], bound=0, encoding=EncType.adder))
    assert not _is_sat(PBEnc.geq([], weights=[], bound=1, encoding=EncType.adder))
    assert _is_sat(PBEnc.equals([], weights=[], bound=0, encoding=EncType.adder))
    assert not _is_sat(PBEnc.equals([], weights=[], bound=1, encoding=EncType.adder))


def test_false_empty_pb_sum_respects_conditionals():
    cnf = PBEnc.geq(
        [],
        weights=[],
        bound=1,
        top_id=1,
        encoding=EncType.adder,
        conditionals=[1],
    )

    assert _is_sat(cnf, assumptions=[-1])
    assert not _is_sat(cnf, assumptions=[1])
