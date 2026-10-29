import pytest

from hermax.model import Model
from hermax.model.expressions import PBExpr, sum_expr


@pytest.mark.parametrize('coefficient', [-3, 2])
def test_realize_integer_terms_batches_without_merges(monkeypatch, coefficient):
    m = Model()
    x = m.int('x', -4, 4)
    b = m.bool('b')
    expression = sum_expr([b, coefficient * (x // 2), x // 2, 7])

    expression = PBExpr(m, expression.terms, expression.constant,
                        int_terms=[*expression.int_terms, (2, x)])

    def forbidden(*args, **kwargs):
        raise AssertionError('integer realization repeatedly merges expressions')

    with monkeypatch.context() as patch:
        patch.setattr(PBExpr, '_merge', forbidden)
        lowered = expression._realize_int_terms(m)
    assert not lowered.int_terms
    assert expression.int_terms  # The source expression remains reusable.
    for xv in range(-4, 5):
        for bv in (False, True):
            result = m.solve(assumptions=[x == xv, b if bv else ~b])
            assert result[lowered] == 7 + int(bv) + (coefficient + 1) * (xv // 2) + 2 * xv


def test_expression_without_integer_terms_needs_no_realization():
    m = Model()
    expression = sum_expr([m.bool('b'), 5])
    assert expression._realize_int_terms(m) is expression
