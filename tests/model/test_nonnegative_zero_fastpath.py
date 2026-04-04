from __future__ import annotations

import hermax.encoder.pbamo as pbamo_mod
from hermax.model import Model


def _solve(m: Model):
    return m.solve()


def test_nonnegative_zero_fastpath_weighted_boolsum_avoids_structured(monkeypatch):
    def fail_auto(*args, **kwargs):
        raise AssertionError("PBAMOEnc.auto_leq should not be called for <=0 nonnegative fastpath")

    monkeypatch.setattr(
        pbamo_mod.PBAMOEnc,
        "auto_leq",
        classmethod(lambda cls, *a, **kw: fail_auto(*a, **kw)),
    )

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    m &= (2 * a + 3 * b + 5 * c <= 0)
    r = _solve(m)
    assert r.ok
    assert r[a] is False
    assert r[b] is False
    assert r[c] is False


def test_nonnegative_zero_fastpath_nonnegative_intvars_avoids_structured(monkeypatch):
    def fail_auto(*args, **kwargs):
        raise AssertionError("PBAMOEnc.auto_leq should not be called for <=0 nonnegative fastpath")

    monkeypatch.setattr(
        pbamo_mod.PBAMOEnc,
        "auto_leq",
        classmethod(lambda cls, *a, **kw: fail_auto(*a, **kw)),
    )

    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 0, 5)
    z = m.int("z", 0, 5)
    m &= (2 * x + 3 * y + 5 * z <= 0)
    m &= (x >= 1)
    r = _solve(m)
    assert r.status == "unsat"


def test_nonnegative_zero_fastpath_does_not_claim_nonzero_bound(monkeypatch):
    called = {"auto": 0}
    orig_auto = pbamo_mod.PBAMOEnc.auto_leq

    def wrapped_auto(*args, **kwargs):
        called["auto"] += 1
        return orig_auto(*args, **kwargs)

    monkeypatch.setattr(
        pbamo_mod.PBAMOEnc,
        "auto_leq",
        classmethod(lambda cls, *a, **kw: wrapped_auto(*a, **kw)),
    )

    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = m.bool("c")
    m &= (2 * a + 3 * b + 5 * c <= 1)
    r = _solve(m)
    assert r.status in {"sat", "optimum", "unsat"}
    assert called["auto"] >= 1
