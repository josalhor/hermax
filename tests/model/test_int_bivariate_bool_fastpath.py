from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
from hermax.model.encoders import _EncoderDispatch
from hermax.internal.card import CardEnc
from hermax.internal.pb import PBEnc
from hermax.model import Model


def _cmp(lhs: int, op: str, rhs: int) -> bool:
    if op == "<=":
        return lhs <= rhs
    if op == "<":
        return lhs < rhs
    if op == ">=":
        return lhs >= rhs
    if op == ">":
        return lhs > rhs
    if op == "==":
        return lhs == rhs
    raise ValueError(op)


def _exists_sat(a: int, b: int, w: int, op: str, k: int, *, neg_lit: bool) -> bool:
    for xv, yv, bv in itertools.product(range(0, 4), range(0, 4), (0, 1)):
        bit = (1 - bv) if neg_lit else bv
        if _cmp(a * xv + b * yv + w * bit, op, k):
            return True
    return False


def _post_rel(m: Model, lhs, op: str, rhs) -> None:
    if op == "<=":
        m &= (lhs <= rhs)
    elif op == "<":
        m &= (lhs < rhs)
    elif op == ">=":
        m &= (lhs >= rhs)
    elif op == ">":
        m &= (lhs > rhs)
    elif op == "==":
        m &= (lhs == rhs)
    else:
        raise ValueError(op)


@pytest.mark.parametrize("op", ["<=", "<", ">=", ">", "=="])
@pytest.mark.parametrize("a,b,w,k", [
    (1, 1, 5, 4),
    (2, -1, 7, 3),
    (-1, 2, -4, -1),
])
@pytest.mark.parametrize("neg_lit", [False, True])
def test_bivariate_bool_fastpath_matches_bruteforce_small_domains(op: str, a: int, b: int, w: int, k: int, neg_lit: bool):
    m = Model()
    x = m.int("x", 0, 4)
    y = m.int("y", 0, 4)
    bit = m.bool("bit")
    lit = (~bit) if neg_lit else bit
    _post_rel(m, a * x + b * y + w * lit, op, k)
    r = m.solve()
    expected = _exists_sat(a, b, w, op, k, neg_lit=neg_lit)
    assert (r.ok if expected else r.status == "unsat")


def test_bivariate_bool_fastpath_bypasses_pb_and_card_encoders(monkeypatch):
    def fail_pb(*args, **kwargs):
        raise AssertionError("PBEnc should not be called for bivariate-int+bool fastpath")

    def fail_card(*args, **kwargs):
        raise AssertionError("CardEnc should not be called for bivariate-int+bool fastpath")

    monkeypatch.setattr(PBEnc, "leq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "geq", staticmethod(fail_pb))
    monkeypatch.setattr(PBEnc, "equals", staticmethod(fail_pb))
    monkeypatch.setattr(CardEnc, "atmost", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "atleast", staticmethod(fail_card))
    monkeypatch.setattr(CardEnc, "equals", staticmethod(fail_card))

    m = Model()
    x = m.int("x", 0, 4)
    y = m.int("y", 0, 4)
    b = m.bool("b")
    m &= (2 * x - y + 100 * b <= 97)
    r = m.solve()
    assert r.status in {"sat", "optimum", "unsat"}


def test_dispatch_attempts_bivariate_bool_fastpath(monkeypatch):
    seen = {"hit": 0}
    orig = _EncoderDispatch._try_bivariate_with_bool_fastpath

    def wrapped(*args, **kwargs):
        seen["hit"] += 1
        return orig(*args, **kwargs)

    monkeypatch.setattr(_EncoderDispatch, "_try_bivariate_with_bool_fastpath", staticmethod(wrapped))

    m = Model()
    x = m.int("x", 0, 4)
    y = m.int("y", 0, 4)
    b = m.bool("b")
    m &= (x + 2 * y + 9 * b <= 10)
    _ = m.solve()
    assert seen["hit"] >= 1
