from __future__ import annotations

import itertools

import pytest

import hermax.model as hm
from hermax.model.encoders import _EncoderDispatch
from hermax.model import Model


def _status(m: Model) -> str:
    return m.solve().status


def _point_sat(build_constraint, domains, point, *, disable_fastpath: str | None = None) -> bool:
    m = Model()
    vars_by_name = {}
    for name, (lb, ub) in domains.items():
        vars_by_name[name] = m.int(name, lb, ub)
    bools_by_name = {}
    for name in point:
        if name.startswith("b_"):
            bools_by_name[name] = m.bool(name)

    if disable_fastpath is not None:
        orig = getattr(_EncoderDispatch, disable_fastpath)
        setattr(_EncoderDispatch, disable_fastpath, staticmethod(lambda *args, **kwargs: None))
    try:
        m &= build_constraint(vars_by_name, bools_by_name)
    finally:
        if disable_fastpath is not None:
            setattr(_EncoderDispatch, disable_fastpath, orig)

    for name, value in point.items():
        if name.startswith("b_"):
            lit = bools_by_name[name]
            m &= (lit if value else ~lit)
        else:
            m &= (vars_by_name[name] == value)
    return _status(m) != "unsat"


def _assert_diff_equivalent(
    *,
    build_constraint,
    domains: dict[str, tuple[int, int]],
    bool_names: tuple[str, ...] = (),
    disable_fastpath: str,
    truth_fn,
) -> None:
    int_names = tuple(domains.keys())
    int_ranges = [range(domains[n][0], domains[n][1]) for n in int_names]
    bool_ranges = [[False, True] for _ in bool_names]
    for values in itertools.product(*int_ranges, *bool_ranges):
        point = {}
        idx = 0
        for n in int_names:
            point[n] = values[idx]
            idx += 1
        for n in bool_names:
            point[n] = values[idx]
            idx += 1

        expected = bool(truth_fn(point))
        sat_fast = _point_sat(
            build_constraint, domains, point, disable_fastpath=None
        )
        sat_slow = _point_sat(
            build_constraint, domains, point, disable_fastpath=disable_fastpath
        )
        assert sat_fast == expected, (disable_fastpath, "fast", point, expected)
        assert sat_slow == expected, (disable_fastpath, "slow", point, expected)
        assert sat_fast == sat_slow, (disable_fastpath, "diff", point)


def test_diff_univariate_fastpath_soundness():
    a, c, op = 3, 7, "<="

    def build(v, _b):
        return (a * v["x"] <= c)

    def truth(p):
        x = p["x"]
        return (a * x <= c) if op == "<=" else False

    _assert_diff_equivalent(
        build_constraint=build,
        domains={"x": (0, 5)},
        disable_fastpath="_try_univariate_int_fastpath",
        truth_fn=truth,
    )


def test_diff_univariate_bool_fastpath_soundness():
    a, w, c = 2, 3, 6

    def build(v, b):
        return (a * v["x"] + w * b["b_flag"] <= c)

    def truth(p):
        return a * p["x"] + w * (1 if p["b_flag"] else 0) <= c

    _assert_diff_equivalent(
        build_constraint=build,
        domains={"x": (0, 5)},
        bool_names=("b_flag",),
        disable_fastpath="_try_univariate_with_bool_fastpath",
        truth_fn=truth,
    )


def test_diff_bivariate_fastpath_soundness():
    a, b, c, op = 2, -3, -1, ">="

    def build(v, _b):
        return (a * v["x"] + b * v["y"] >= c)

    def truth(p):
        return a * p["x"] + b * p["y"] >= c

    _assert_diff_equivalent(
        build_constraint=build,
        domains={"x": (-2, 3), "y": (0, 5)},
        disable_fastpath="_try_bivariate_int_fastpath",
        truth_fn=truth,
    )


def test_diff_trivariate_fastpath_soundness():
    def build(v, _b):
        return (v["x"] + v["y"] <= v["z"])

    def truth(p):
        return p["x"] + p["y"] <= p["z"]

    _assert_diff_equivalent(
        build_constraint=build,
        domains={"x": (0, 4), "y": (0, 4), "z": (0, 7)},
        disable_fastpath="_try_trivariate_int_fastpath",
        truth_fn=truth,
    )


def test_diff_trivariate_fastpath_soundness_with_shift():
    def build(v, _b):
        return (v["x"] + v["y"] - 2 <= v["z"])

    def truth(p):
        return p["x"] + p["y"] - 2 <= p["z"]

    _assert_diff_equivalent(
        build_constraint=build,
        domains={"x": (-2, 3), "y": (1, 5), "z": (-1, 6)},
        disable_fastpath="_try_trivariate_int_fastpath",
        truth_fn=truth,
    )


def test_diff_unary_adder_eq_fastpath_soundness():
    def build(v, _b):
        return (v["x"] + v["y"] == v["z"])

    def truth(p):
        return p["x"] + p["y"] == p["z"]

    _assert_diff_equivalent(
        build_constraint=build,
        domains={"x": (3, 7), "y": (-2, 3), "z": (1, 9)},
        disable_fastpath="_try_unary_adder_eq_fastpath",
        truth_fn=truth,
    )


def test_diff_boolsum_bigm_upper_soundness():
    def build(_v, b):
        return (b["b_x0"] + b["b_x1"] + b["b_x2"] + b["b_x3"] <= (2 + 2 * b["b_gate"]))

    def truth(p):
        return (
            (1 if p["b_x0"] else 0)
            + (1 if p["b_x1"] else 0)
            + (1 if p["b_x2"] else 0)
            + (1 if p["b_x3"] else 0)
            <= 2 + 2 * (1 if p["b_gate"] else 0)
        )

    _assert_diff_equivalent(
        build_constraint=build,
        domains={},
        bool_names=("b_x0", "b_x1", "b_x2", "b_x3", "b_gate"),
        disable_fastpath="_try_boolsum_bigm_fastpath",
        truth_fn=truth,
    )


def test_diff_boolsum_bigm_lower_soundness():
    def build(_v, b):
        return (b["b_x0"] + b["b_x1"] + b["b_x2"] >= (1 + 2 * b["b_gate"]))

    def truth(p):
        return (
            (1 if p["b_x0"] else 0)
            + (1 if p["b_x1"] else 0)
            + (1 if p["b_x2"] else 0)
            >= 1 + 2 * (1 if p["b_gate"] else 0)
        )

    _assert_diff_equivalent(
        build_constraint=build,
        domains={},
        bool_names=("b_x0", "b_x1", "b_x2", "b_gate"),
        disable_fastpath="_try_boolsum_bigm_fastpath",
        truth_fn=truth,
    )


def test_diff_int_equals_unit_bool_sum_fastpath_soundness_with_shift():
    def build(v, b):
        return (v["x"] + 1 == (b["b_0"] + b["b_1"] + b["b_2"] - 1))

    def truth(p):
        return p["x"] + 1 == (
            (1 if p["b_0"] else 0)
            + (1 if p["b_1"] else 0)
            + (1 if p["b_2"] else 0)
            - 1
        )

    _assert_diff_equivalent(
        build_constraint=build,
        domains={"x": (-1, 5)},
        bool_names=("b_0", "b_1", "b_2"),
        disable_fastpath="_try_int_equals_unit_bool_sum_fastpath",
        truth_fn=truth,
    )


def test_diff_mixed_int_boolsum_fastpath_soundness():
    def build(v, b):
        return (2 * v["x"] + b["b_0"] + b["b_1"] + b["b_2"] <= (4 + 3 * b["b_gate"]))

    def truth(p):
        return 2 * p["x"] + (
            (1 if p["b_0"] else 0)
            + (1 if p["b_1"] else 0)
            + (1 if p["b_2"] else 0)
        ) <= 4 + 3 * (1 if p["b_gate"] else 0)

    _assert_diff_equivalent(
        build_constraint=build,
        domains={"x": (0, 5)},
        bool_names=("b_0", "b_1", "b_2", "b_gate"),
        disable_fastpath="_try_mixed_int_boolsum_bigm_fastpath",
        truth_fn=truth,
    )


def test_dispatch_precedence_unary_adder_over_trivariate():
    seen = {"unary_adder": 0, "trivariate": 0}
    o1 = _EncoderDispatch._try_unary_adder_eq_fastpath
    o2 = _EncoderDispatch._try_trivariate_int_fastpath

    def w1(model, lhs, op, rhs):
        out = o1(model, lhs, op, rhs)
        if out is not None:
            seen["unary_adder"] += 1
        return out

    def w2(model, lhs, op, rhs):
        out = o2(model, lhs, op, rhs)
        if out is not None:
            seen["trivariate"] += 1
        return out

    _EncoderDispatch._try_unary_adder_eq_fastpath = staticmethod(w1)
    _EncoderDispatch._try_trivariate_int_fastpath = staticmethod(w2)
    try:
        m = Model()
        x = m.int("x", 0, 6)
        y = m.int("y", 0, 6)
        z = m.int("z", 0, 11)
        m &= (x + y == z)
        m &= (x == 2)
        m &= (y == 3)
        m &= (z == 5)
        r = m.solve()
        assert r.ok
    finally:
        _EncoderDispatch._try_unary_adder_eq_fastpath = o1
        _EncoderDispatch._try_trivariate_int_fastpath = o2

    assert seen["unary_adder"] >= 1
    assert seen["trivariate"] == 0


def test_dispatch_precedence_boolsum_over_univariate():
    seen = {"boolsum": 0, "univariate": 0}
    o1 = _EncoderDispatch._try_int_equals_unit_bool_sum_fastpath
    o2 = _EncoderDispatch._try_univariate_int_fastpath

    def w1(model, lhs, op, rhs):
        out = o1(model, lhs, op, rhs)
        if out is not None:
            seen["boolsum"] += 1
        return out

    def w2(model, lhs, op, rhs):
        out = o2(model, lhs, op, rhs)
        if out is not None:
            seen["univariate"] += 1
        return out

    _EncoderDispatch._try_int_equals_unit_bool_sum_fastpath = staticmethod(w1)
    _EncoderDispatch._try_univariate_int_fastpath = staticmethod(w2)
    try:
        m = Model()
        x = m.int("x", 0, 4)
        b = [m.bool(f"b{i}") for i in range(3)]
        m &= (x == (b[0] + b[1] + b[2]))
        m &= (x == 2)
        m &= b[0]
        m &= b[1]
        m &= ~b[2]
        r = m.solve()
        assert r.ok
    finally:
        _EncoderDispatch._try_int_equals_unit_bool_sum_fastpath = o1
        _EncoderDispatch._try_univariate_int_fastpath = o2

    assert seen["boolsum"] >= 1
    assert seen["univariate"] == 0
