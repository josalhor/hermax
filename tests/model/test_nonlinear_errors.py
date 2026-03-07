from __future__ import annotations

import pytest

from hermax.model import Model


def test_intvar_times_intvar_has_clear_nonlinear_error():
    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 0, 5)
    with pytest.raises(TypeError, match=r"Unsupported arithmetic: <IntVar: x> \* <IntVar: y>"):
        _ = x * y


def test_chained_scaled_product_ending_in_intvar_has_clear_nonlinear_error():
    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 0, 5)
    with pytest.raises(TypeError, match=r"Unsupported arithmetic: <PBExpr> \* <IntVar: y>"):
        _ = (3 * x) * 2 * y


def test_pbexpr_times_intvar_has_clear_nonlinear_error():
    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 0, 5)
    with pytest.raises(TypeError, match=r"Unsupported arithmetic: <PBExpr> \* <IntVar: y>"):
        _ = (x + 1) * y


def test_literal_times_intvar_has_clear_nonlinear_error():
    m = Model()
    b = m.bool("b")
    x = m.int("x", 0, 5)
    with pytest.raises(TypeError, match=r"Unsupported arithmetic: <Literal: b> \* <IntVar: x>"):
        _ = b * x


def test_intvar_floor_div_intvar_reports_nonlinear_arithmetic():
    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 1, 6)
    with pytest.raises(TypeError, match=r"Unsupported arithmetic: <IntVar: x> // <IntVar: y>"):
        _ = x // y


def test_pbexpr_floor_div_intvar_reports_nonlinear_arithmetic():
    m = Model()
    x = m.int("x", 0, 5)
    y = m.int("y", 1, 6)
    with pytest.raises(TypeError, match=r"Unsupported arithmetic: <PBExpr> // <IntVar: y>"):
        _ = (x + 1) // y
