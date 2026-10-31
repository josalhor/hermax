"""Encoder adapters for the model's private clause storage."""

from dataclasses import dataclass, field

import hermax_pycard
from hermax.internal import _pblib, _pbamo
from hermax.internal._clause_storage import ClauseStorage
from .card import CardEnc as _CardEnc, ITotalizer as _ITotalizer
from .pb_enc import PBEnc as _PBEnc
from .pbamo import PBAMOEnc as _PBAMOEnc, _append_amo
from .pb import PBCompiler as _PBCompiler


@dataclass(slots=True)
class _EncodedCNF:
    clauses: ClauseStorage = field(default_factory=ClauseStorage)
    nv: int = 0
    atmosts: list = field(default_factory=list)


def encode_amo(lits, top_id, *, equality=False):
    cnf = _EncodedCNF(nv=top_id)
    _append_amo(cnf, lits, equality=equality)
    return cnf


def _wrap(result):
    if result is None:
        return None
    clauses, nv = result
    return ClauseStorage._wrap(clauses), nv


class PBEnc(_PBEnc):
    _new_cnf = _EncodedCNF

    @staticmethod
    def _encode_native(**kwargs):
        return _wrap(_pblib._encode_pb_packed(**kwargs))


class CardEnc(_CardEnc):
    _new_cnf = _EncodedCNF

    @staticmethod
    def _encode_atmost_native(*args):
        return _wrap(hermax_pycard._encode_atmost_packed(*args))

    @staticmethod
    def _encode_atleast_native(*args):
        return _wrap(hermax_pycard._encode_atleast_packed(*args))


class ITotalizer(_ITotalizer):
    _new_cnf = _EncodedCNF

    @staticmethod
    def _new_native(*args):
        tree, clauses, rhs, top_id = hermax_pycard._itot_new_packed(*args)
        return tree, ClauseStorage._wrap(clauses), rhs, top_id


class PBAMOEnc(_PBAMOEnc):
    _new_cnf = _EncodedCNF
    _pb_encoder = PBEnc
    _card_encoder = CardEnc
    _totalizer = ITotalizer

    @staticmethod
    def _encode_leq_native(**kwargs):
        return _wrap(_pbamo._encode_leq_packed(**kwargs))

    @staticmethod
    def _encode_eq_native(**kwargs):
        return _wrap(_pbamo._encode_eq_packed(**kwargs))


class PBCompiler(_PBCompiler):
    _encoder = PBAMOEnc


class _ModelPBAMOEnc(PBAMOEnc):
    """Model owns the AMO/EO facts, including pending unconditional constraints."""

    _emit_candidate_facts = False


class _ModelPBCompiler(PBCompiler):
    _encoder = _ModelPBAMOEnc
