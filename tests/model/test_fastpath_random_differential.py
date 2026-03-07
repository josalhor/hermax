from __future__ import annotations

import random
from typing import Callable

import pytest

import hermax.model as hm
from hermax.model import Model


SATLIKE = {"sat", "optimum"}


def _status_bucket(status: str) -> str:
    if status in SATLIKE:
        return "sat"
    if status == "unsat":
        return "unsat"
    return status


def _rand_domain(rng: random.Random, *, min_lb: int = -3, max_lb: int = 3, min_span: int = 2, max_span: int = 6) -> tuple[int, int]:
    lb = rng.randint(min_lb, max_lb)
    span = rng.randint(min_span, max_span)
    return lb, lb + span


def _extract_assignment(result, vars_int: dict[str, object], vars_bool: dict[str, object]) -> dict[str, int | bool]:
    out: dict[str, int | bool] = {}
    for name, v in vars_int.items():
        out[name] = int(result[v])
    for name, b in vars_bool.items():
        out[name] = bool(result[b])
    return out


def _solve_with_path_control(
    build_model: Callable[[], tuple[Model, dict[str, object], dict[str, object], Callable[[dict[str, int | bool]], bool]]],
    *,
    fastpath_name: str,
    disable: bool,
):
    orig = getattr(hm._EncoderDispatch, fastpath_name)
    matched = {"n": 0}

    def wrapped(model, lhs, op, rhs):
        out = orig(model, lhs, op, rhs)
        if out is not None:
            matched["n"] += 1
        return out

    try:
        if disable:
            setattr(hm._EncoderDispatch, fastpath_name, staticmethod(lambda *args, **kwargs: None))
        else:
            setattr(hm._EncoderDispatch, fastpath_name, staticmethod(wrapped))

        m, vars_int, vars_bool, truth = build_model()
        r = m.solve()
        return r, vars_int, vars_bool, truth, matched["n"]
    finally:
        setattr(hm._EncoderDispatch, fastpath_name, orig)


def _run_random_differential(
    *,
    rng_seed: int,
    cases: int,
    fastpath_name: str,
    min_matches: int = 1,
    make_case: Callable[[random.Random], tuple[Callable[[], tuple[Model, dict[str, object], dict[str, object], Callable[[dict[str, int | bool]], bool]]], str]],
):
    rng = random.Random(rng_seed)
    total_matches = 0
    for _ in range(cases):
        build_model, label = make_case(rng)

        r_fast, vi_f, vb_f, truth_f, matched_fast = _solve_with_path_control(
            build_model, fastpath_name=fastpath_name, disable=False
        )
        r_slow, vi_s, vb_s, truth_s, _ = _solve_with_path_control(
            build_model, fastpath_name=fastpath_name, disable=True
        )

        total_matches += matched_fast

        b_fast = _status_bucket(r_fast.status)
        b_slow = _status_bucket(r_slow.status)
        assert b_fast == b_slow, (fastpath_name, label, r_fast.status, r_slow.status)
        assert b_fast in {"sat", "unsat"}, (fastpath_name, label, r_fast.status, r_slow.status)

        if b_fast == "sat":
            a_fast = _extract_assignment(r_fast, vi_f, vb_f)
            a_slow = _extract_assignment(r_slow, vi_s, vb_s)
            assert truth_f(a_fast), (fastpath_name, label, "fast invalid assignment", a_fast)
            assert truth_s(a_slow), (fastpath_name, label, "slow invalid assignment", a_slow)

    assert total_matches >= min_matches, (
        fastpath_name,
        f"expected at least {min_matches} matched compile(s), got {total_matches}",
    )


def test_random_diff_univariate_fastpath():
    def make_case(rng: random.Random):
        lb, ub = _rand_domain(rng)
        a = rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])
        op = rng.choice(["<=", "<", ">=", ">", "=="])
        c = rng.randint(-12, 12)
        pin = rng.choice([None, rng.randint(lb, ub - 1)])

        def build():
            m = Model()
            x = m.int("x", lb, ub)
            expr = a * x
            if op == "<=":
                m &= (expr <= c)
            elif op == "<":
                m &= (expr < c)
            elif op == ">=":
                m &= (expr >= c)
            elif op == ">":
                m &= (expr > c)
            else:
                m &= (expr == c)
            if pin is not None:
                m &= (x == pin)

            def truth(asg):
                xv = int(asg["x"])
                v = a * xv
                ok = (v <= c) if op == "<=" else (v < c) if op == "<" else (v >= c) if op == ">=" else (v > c) if op == ">" else (v == c)
                return ok and (pin is None or xv == pin)

            return m, {"x": x}, {}, truth

        return build, f"a={a},op={op},c={c},dom=[{lb},{ub}),pin={pin}"

    _run_random_differential(
        rng_seed=11,
        cases=40,
        fastpath_name="_try_univariate_int_fastpath",
        make_case=make_case,
    )


def test_random_diff_univariate_bool_fastpath():
    def make_case(rng: random.Random):
        lb, ub = _rand_domain(rng, min_lb=0, max_lb=3)
        a = rng.choice([-3, -2, -1, 1, 2, 3])
        w = rng.randint(1, 5)
        op = rng.choice(["<=", "<", ">=", ">", "=="])
        c = rng.randint(-10, 12)
        pin_x = rng.choice([None, rng.randint(lb, ub - 1)])
        pin_b = rng.choice([None, True, False])

        def build():
            m = Model()
            x = m.int("x", lb, ub)
            b = m.bool("b_flag")
            expr = a * x + w * b
            if op == "<=":
                m &= (expr <= c)
            elif op == "<":
                m &= (expr < c)
            elif op == ">=":
                m &= (expr >= c)
            elif op == ">":
                m &= (expr > c)
            else:
                m &= (expr == c)

            if pin_x is not None:
                m &= (x == pin_x)
            if pin_b is True:
                m &= b
            elif pin_b is False:
                m &= ~b

            def truth(asg):
                xv = int(asg["x"])
                bv = 1 if bool(asg["b_flag"]) else 0
                v = a * xv + w * bv
                ok = (v <= c) if op == "<=" else (v < c) if op == "<" else (v >= c) if op == ">=" else (v > c) if op == ">" else (v == c)
                return ok and (pin_x is None or xv == pin_x) and (pin_b is None or bool(asg["b_flag"]) == pin_b)

            return m, {"x": x}, {"b_flag": b}, truth

        return build, f"a={a},w={w},op={op},c={c},pinx={pin_x},pinb={pin_b}"

    _run_random_differential(
        rng_seed=12,
        cases=40,
        fastpath_name="_try_univariate_with_bool_fastpath",
        make_case=make_case,
    )


def test_random_diff_bivariate_fastpath():
    def make_case(rng: random.Random):
        xl, xu = _rand_domain(rng)
        yl, yu = _rand_domain(rng)
        a = rng.choice([-3, -2, -1, 1, 2, 3])
        b = rng.choice([-3, -2, -1, 1, 2, 3])
        op = rng.choice(["<=", "<", ">=", ">", "=="])
        c = rng.randint(-14, 14)
        pinx = rng.choice([None, rng.randint(xl, xu - 1)])
        piny = rng.choice([None, rng.randint(yl, yu - 1)])

        def build():
            m = Model()
            x = m.int("x", xl, xu)
            y = m.int("y", yl, yu)
            expr = a * x + b * y
            if op == "<=":
                m &= (expr <= c)
            elif op == "<":
                m &= (expr < c)
            elif op == ">=":
                m &= (expr >= c)
            elif op == ">":
                m &= (expr > c)
            else:
                m &= (expr == c)
            if pinx is not None:
                m &= (x == pinx)
            if piny is not None:
                m &= (y == piny)

            def truth(asg):
                xv = int(asg["x"])
                yv = int(asg["y"])
                v = a * xv + b * yv
                ok = (v <= c) if op == "<=" else (v < c) if op == "<" else (v >= c) if op == ">=" else (v > c) if op == ">" else (v == c)
                return ok and (pinx is None or xv == pinx) and (piny is None or yv == piny)

            return m, {"x": x, "y": y}, {}, truth

        return build, f"a={a},b={b},op={op},c={c}"

    _run_random_differential(
        rng_seed=13,
        cases=45,
        fastpath_name="_try_bivariate_int_fastpath",
        make_case=make_case,
    )


def test_random_diff_trivariate_fastpath():
    def make_case(rng: random.Random):
        xl, xu = _rand_domain(rng, min_lb=0, max_lb=2)
        yl, yu = _rand_domain(rng, min_lb=0, max_lb=2)
        zl, zu = _rand_domain(rng, min_lb=0, max_lb=3, min_span=3, max_span=8)
        op = rng.choice(["<=", "<"])
        pinx = rng.choice([None, rng.randint(xl, xu - 1)])
        piny = rng.choice([None, rng.randint(yl, yu - 1)])
        pinz = rng.choice([None, rng.randint(zl, zu - 1)])

        def build():
            m = Model()
            x = m.int("x", xl, xu)
            y = m.int("y", yl, yu)
            z = m.int("z", zl, zu)
            if op == "<=":
                m &= (x + y <= z)
            else:
                m &= (x + y < z)
            if pinx is not None:
                m &= (x == pinx)
            if piny is not None:
                m &= (y == piny)
            if pinz is not None:
                m &= (z == pinz)

            def truth(asg):
                xv = int(asg["x"])
                yv = int(asg["y"])
                zv = int(asg["z"])
                ok = (xv + yv <= zv) if op == "<=" else (xv + yv < zv)
                return ok and (pinx is None or xv == pinx) and (piny is None or yv == piny) and (pinz is None or zv == pinz)

            return m, {"x": x, "y": y, "z": z}, {}, truth

        return build, f"op={op}"

    _run_random_differential(
        rng_seed=14,
        cases=45,
        fastpath_name="_try_trivariate_int_fastpath",
        make_case=make_case,
    )


def test_random_diff_unary_adder_eq_fastpath():
    def make_case(rng: random.Random):
        xl, xu = _rand_domain(rng, min_lb=-2, max_lb=3, min_span=2, max_span=7)
        yl, yu = _rand_domain(rng, min_lb=-2, max_lb=3, min_span=2, max_span=7)
        # Match compact-ladder unary-adder shape exactly:
        # bits(z) == bits(x) + bits(y)
        # with bits(v)= (ub-lb-1), choose z in [min_sum, max_sum+1).
        zl = xl + yl
        zu = xu + yu - 1
        pinx = rng.choice([None, rng.randint(xl, xu - 1)])
        piny = rng.choice([None, rng.randint(yl, yu - 1)])
        pinz = rng.choice([None, rng.randint(zl, zu - 1)])

        def build():
            m = Model()
            x = m.int("x", xl, xu)
            y = m.int("y", yl, yu)
            z = m.int("z", zl, zu)
            m &= (x + y == z)
            if pinx is not None:
                m &= (x == pinx)
            if piny is not None:
                m &= (y == piny)
            if pinz is not None:
                m &= (z == pinz)

            def truth(asg):
                xv = int(asg["x"])
                yv = int(asg["y"])
                zv = int(asg["z"])
                ok = (xv + yv == zv)
                return ok and (pinx is None or xv == pinx) and (piny is None or yv == piny) and (pinz is None or zv == pinz)

            return m, {"x": x, "y": y, "z": z}, {}, truth

        return build, "x+y==z"

    _run_random_differential(
        rng_seed=15,
        cases=45,
        fastpath_name="_try_unary_adder_eq_fastpath",
        make_case=make_case,
    )
