from __future__ import annotations

import pytest

from hermax.model import Clause, Model


def test_clause_implies_rejects_unsupported_target_type():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = Clause(m, [a, b])
    with pytest.raises(TypeError, match="Unsupported implication target"):
        c.implies(object())


def test_clause_implies_accepts_clausegroup_and_pbconstraint_targets():
    m = Model()
    a = m.bool("a")
    b = m.bool("b")
    c = Clause(m, [a, b])

    g = c.implies(Clause(m, [~a]) & Clause(m, [~b]))
    assert len(g) > 0

    pbg = c.implies((a + b <= 1))
    assert len(pbg) > 0
