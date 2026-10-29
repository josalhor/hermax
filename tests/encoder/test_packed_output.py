import itertools

import pytest

from hermax.encoder.card import CardEnc as PublicCard, UnsupportedBound
from hermax.encoder.pb_enc import PBEnc as PublicPB, EncType as PBType
from hermax.encoder.pbamo import PBAMOEnc as PublicPBAMO, available_encoders
from hermax.encoder._packed import CardEnc, PBEnc, PBAMOEnc
from hermax.internal._clause_storage import ClauseStorage
from hermax.model import BoolVector, Model


def _same(plain, packed):
    assert type(plain.clauses) is list
    assert all(type(row) is list for row in plain.clauses)
    assert isinstance(packed.clauses, ClauseStorage)
    assert packed.clauses.to_lists() == plain.clauses
    assert packed.nv == plain.nv
    assert packed.atmosts == plain.atmosts


@pytest.mark.parametrize("encoding", [PBType.best, PBType.bdd, PBType.seqcounter,
                                    PBType.sortnetwrk, PBType.adder, PBType.binmerge, PBType.lpw])
@pytest.mark.parametrize("method", ["leq", "geq", "equals"])
@pytest.mark.parametrize("conditions", [[], [33, -34]])
def test_pblib_packed_output_matches_public_encoder_exactly(encoding, method, conditions):
    kwargs = dict(lits=list(range(1, 17)), weights=[i % 7 + 1 for i in range(16)],
                  bound=25, top_id=34, encoding=encoding, conditionals=conditions)
    _same(getattr(PublicPB, method)(**kwargs), getattr(PBEnc, method)(**kwargs))


@pytest.mark.parametrize("encoding", range(9))
@pytest.mark.parametrize("method,bound", [("atmost", 0), ("atmost", 1), ("atmost", 7),
                                         ("atleast", 1), ("atleast", 6), ("equals", 1)])
def test_pycard_packed_output_matches_public_encoder_exactly(encoding, method, bound):
    kwargs = dict(lits=[1, -2, 3, 4, -5, 6, 7, 8], bound=bound, top_id=30, encoding=encoding)
    try:
        plain = getattr(PublicCard, method)(**kwargs)
    except UnsupportedBound:
        with pytest.raises(UnsupportedBound):
            getattr(CardEnc, method)(**kwargs)
        return
    _same(plain, getattr(CardEnc, method)(**kwargs))


@pytest.mark.parametrize("encoding", [name for name in available_encoders() if name != "best"])
@pytest.mark.parametrize("groups", [[[1], [-2], [3], [4]], [[1, -2], [3, 4]]])
@pytest.mark.parametrize("emit_amo", [False, True])
def test_pbamo_packed_output_matches_public_encoder_exactly(encoding, groups, emit_amo):
    kwargs = dict(lits=[1, -2, 3, 4], weights=[3, 5, 7, 11], groups=groups,
                  bound=13, top_id=20, encoding=encoding, emit_amo=emit_amo)
    _same(PublicPBAMO.leq(**kwargs), PBAMOEnc.leq(**kwargs))


@pytest.mark.parametrize("bound", [0, 8, 13, 26, 27])
def test_pbamo_packed_equality_matches_public_encoder_exactly(bound):
    kwargs = dict(lits=[1, -2, 3, 4], weights=[3, 5, 7, 11], groups=[[1, -2], [3, 4]],
                  bound=bound, top_id=20, emit_amo=True)
    _same(PublicPBAMO.equals(**kwargs), PBAMOEnc.equals(**kwargs))


@pytest.mark.parametrize("family", ["plain", "weighted", "amo", "eo"])
@pytest.mark.parametrize("method", ["auto_leq", "auto_eq"])
def test_packed_auto_portfolios_preserve_selection_and_candidate_clauses(family, method):
    lits = list(range(1, 17))
    kwargs = dict(lits=lits, weights=[1] * 16 if family == "plain" else [i % 7 + 1 for i in range(16)],
                  bound=12, top_id=30)
    if family in {"amo", "eo"}:
        kwargs[family + "_groups"] = [lits[:4], lits[3:7], lits[8:12]]
    _same(getattr(PublicPBAMO, method)(**kwargs), getattr(PBAMOEnc, method)(**kwargs))


@pytest.mark.parametrize("encoder,methods", [(CardEnc, ["atmost", "atleast", "equals"]),
                                           (PBEnc, ["leq", "geq", "equals"])])
def test_packed_trivial_and_empty_results_remain_packed(encoder, methods):
    for method, size in itertools.product(methods, [0, 1]):
        kwargs = dict(lits=list(range(1, size + 1)), bound=0, top_id=10)
        if encoder is PBEnc:
            kwargs["weights"] = [1] * size
        result = getattr(encoder, method)(**kwargs)
        assert isinstance(result.clauses, ClauseStorage)


@pytest.mark.parametrize("family", ["pb", "card", "enum", "pbamo"])
def test_model_uses_private_native_outputs_without_calling_plain_bindings(monkeypatch, family):
    import hermax_pycard
    from hermax.internal import _pblib, _pbamo

    def forbidden(*args, **kwargs):
        raise AssertionError("plain Python-clause binding was called")

    monkeypatch.setattr(_pblib, "encode_pb", forbidden)
    monkeypatch.setattr(_pbamo, "encode_leq", forbidden)
    monkeypatch.setattr(_pbamo, "encode_eq", forbidden)
    monkeypatch.setattr(hermax_pycard, "encode_atmost", forbidden)
    monkeypatch.setattr(hermax_pycard, "encode_atleast", forbidden)
    m = Model()
    if family == "enum":
        choice = m.enum("choice", choices=list(range(30)))
        m &= choice == 7
    else:
        xs = m.bool_vector("x", 32)
        if family == "pbamo":
            m &= BoolVector(m, "view", xs[:8]).at_most_one()
        m &= sum((1 if family == "card" else i % 9 + 1) * x for i, x in enumerate(xs)) <= 40
    assert m.solve().ok


@pytest.mark.parametrize("bound", [0, 1, 5, 12])
def test_private_totalizer_initial_output_and_lifetime(bound):
    from hermax.encoder.card import ITotalizer as PublicTotalizer
    from hermax.encoder._packed import ITotalizer

    with PublicTotalizer(lits=list(range(1, 13)), ubound=bound, top_id=20) as plain:
        with ITotalizer(lits=list(range(1, 13)), ubound=bound, top_id=20) as packed:
            assert packed.cnf.clauses.to_lists() == plain.cnf.clauses
            assert packed.top_id == plain.top_id
            assert packed.rhs == plain.rhs
            saved = ClauseStorage(packed.cnf.clauses)
        assert saved.to_lists() == plain.cnf.clauses


@pytest.mark.parametrize("encoding", [PBType.best, PBType.bdd, PBType.seqcounter,
                                    PBType.sortnetwrk, PBType.adder, PBType.binmerge, PBType.lpw])
def test_packed_pb_matches_independent_arithmetic(encoding):
    from pysat.solvers import Solver

    lits, weights = [1, -2, 3, 4], [6, 12, 18, 30]
    for method, bound in itertools.product(("leq", "geq", "equals"), (0, 25, 30, 67)):
        result = getattr(PBEnc, method)(lits=lits, weights=weights, bound=bound,
                                      conditionals=[5], top_id=10, encoding=encoding)
        with Solver(name="g4", bootstrap_with=result.clauses) as solver:
            for values in itertools.product((False, True), repeat=5):
                total = sum(w for lit, w in zip(lits, weights)
                            if values[abs(lit) - 1] == (lit > 0))
                holds = {"leq": total <= bound, "geq": total >= bound,
                         "equals": total == bound}[method]
                expected = not values[4] or holds
                assignment = [i if v else -i for i, v in enumerate(values, 1)]
                assert solver.solve(assumptions=assignment) == expected


@pytest.mark.parametrize("encoder", [PBEnc, CardEnc, PBAMOEnc])
def test_packed_outputs_can_be_shared_then_mutated_independently(encoder):
    if encoder is CardEnc:
        result = encoder.atmost(lits=list(range(1, 17)), bound=7, top_id=20)
    else:
        kwargs = {"groups": [[i] for i in range(1, 17)]} if encoder is PBAMOEnc else {}
        result = encoder.leq(lits=list(range(1, 17)), weights=list(range(1, 17)),
                             bound=50, top_id=20, **kwargs)
    expected = result.clauses.to_lists()
    saved = ClauseStorage(result.clauses)
    result.clauses.append([])
    assert saved.to_lists() == expected
    del result
    saved.append([100])
    assert saved.to_lists() == expected + [[100]]
