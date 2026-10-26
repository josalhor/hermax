import itertools

import pytest
from pysat.solvers import Solver

from hermax.model import Model, PBExpr, Term


def test_decode_linear_expressions_without_mutating_model():
    m = Model()
    b = m.bool("b")
    x = m.int("x", -3, 3)
    m &= b
    m &= x == -2
    result = m.solve()
    lazy = x // 2
    expressions = [2 * b, 3 * ~b, 4 + 2 * b - 3 * x,
                   PBExpr(m, [], 7, int_terms=[(3, lazy)])]
    before = m._next_id, len(m._hard), len(m._soft)
    assert result[expressions] == [2, 0, 12, 4]
    assert result[0.5 * b] == 0.5
    assert result[PBExpr(m, [], -5)] == -5
    assert lazy._realized is None
    assert (m._next_id, len(m._hard), len(m._soft)) == before
    other = Model()
    with pytest.raises(ValueError, match="same model"):
        result[Term(2, other.bool("foreign"))]


@pytest.mark.parametrize("bv,cv,xv", itertools.product((False, True), (False, True), range(-1, 2)))
def test_sum_var_accepts_mixed_literals(bv, cv, xv):
    m = Model()
    b, c = m.bool("b"), m.bool("c")
    x = m.int("x", -1, 1)
    total = m.sum_var([b, ~c, x])
    m &= b if bv else ~b
    m &= c if cv else ~c
    m &= x == xv
    result = m.solve()
    assert result.ok
    assert result[total] == int(bv) + int(not cv) + xv


@pytest.mark.parametrize("bounds,divisor", [((-5, 5), 3), ((-4, -1), 3),
    ((0, 4), 1), ((2, 4), 20), ((19, 20), 20), ((-2, -2), 3)])
def test_modulo_exact_relation(bounds, divisor):
    m = Model()
    x = m.int("x", *bounds)
    rem = m.modulo(x, divisor, name="remainder")
    cnf = m.to_cnf()
    # Verify both correct and incorrect remainder values, independently of objectives.
    with Solver(name="g4", bootstrap_with=cnf.clauses) as solver:
        for xv in range(bounds[0], bounds[1] + 1):
            for rv in range(rem.lb, rem.ub + 1):
                cuts = [lit.id if xv >= bounds[0] + i + 1 else -lit.id
                        for i, lit in enumerate(x._threshold_lits)]
                cuts += [lit.id if rv >= rem.lb + i + 1 else -lit.id
                         for i, lit in enumerate(rem._threshold_lits)]
                assert solver.solve(assumptions=cuts) == (rv == xv % divisor)


def test_lazy_modulo_composes_and_decodes_without_realization():
    m = Model()
    x = m.int("x", -5, 5)
    m &= x == -4
    result = m.solve()
    rem = (x // 2) % 3
    assert result[rem] == 1
    assert rem._realized is None
    m &= rem == 1
    assert m.solve().ok


@pytest.mark.parametrize("bad,error", [(0, ValueError), (-1, ValueError),
    (True, ValueError), (1.5, TypeError)])
def test_modulo_rejects_invalid_divisors_without_mutation(bad, error):
    m = Model()
    x = m.int("x", 0, 3)
    before = m._next_id, len(m._hard), set(m._container_names)
    for make in (lambda: x % bad, lambda: m.modulo(x, bad)):
        with pytest.raises(error):
            make()
    assert (m._next_id, len(m._hard), set(m._container_names)) == before


@pytest.mark.parametrize("factor", [-1, -3])
def test_negative_scale_exact_relation(factor):
    m = Model()
    x = m.int("x", -2, 3)
    scaled = m.scale(x, factor)
    lazy = x.scale(factor)
    assert (lazy.lb, lazy.ub) == (3 * factor, -2 * factor)
    m &= scaled == lazy
    cnf = m.to_cnf()
    with Solver(name="g4", bootstrap_with=cnf.clauses) as solver:
        for xv in range(-2, 4):
            for sv in range(scaled.lb, scaled.ub + 1):
                cuts = [lit.id if xv >= x.lb + i + 1 else -lit.id
                        for i, lit in enumerate(x._threshold_lits)]
                cuts += [lit.id if sv >= scaled.lb + i + 1 else -lit.id
                         for i, lit in enumerate(scaled._threshold_lits)]
                assert solver.solve(assumptions=cuts) == (sv == xv * factor)


def test_zero_objective_is_noop_even_for_lazy_target():
    m = Model()
    x = m.int("x", 0, 4)
    lazy = x // 2
    before = m._next_id, len(m._hard), len(m._soft)
    m.obj += 0 * lazy
    m.obj += 0 * (x != 2)
    m.obj += 0 * (3 * x)
    assert lazy._realized is None
    # Constructing x != 2 above may register an equality indicator; the zero
    # addition itself must not realize it or add objective entries.
    assert len(m._hard) == before[1]
    assert len(m._soft) == before[2]
    m.set_objective_precision(decimals=2)
    m.obj.add(lazy, weight=0.0)
    with pytest.raises(ValueError):
        m.obj.add(x, weight=-1)
    other = Model()
    with pytest.raises(ValueError):
        m.obj += 0 * (other.bool("foreign"))
    with pytest.raises(TypeError):
        m.obj += 0 * (object())


def test_zero_does_not_change_managed_soft_update_contract():
    m = Model()
    b = m.bool("b")
    ref = m.obj.add_soft(b, 2)
    with pytest.raises(ValueError):
        m.obj.update_soft(ref, 0)
    m.obj.update_soft(ref, 3)
    m &= ~b
    assert m.solve().cost == 3


def test_modulo_uses_only_result_variables_and_no_generic_pb_encoder(monkeypatch):
    m = Model()
    x = m.int("x", -8, 8)
    before = m._top_id()

    def forbidden(*args, **kwargs):
        raise AssertionError("Modulo should not use a generic arithmetic encoding")

    monkeypatch.setattr(Model, "_compile_pb_compare", forbidden)
    rem = m.modulo(x, 3)
    assert m._top_id() - before == rem.ub - rem.lb
    m &= x == -7
    m &= rem == 2
    assert m.solve().ok


def test_modulo_and_negative_scale_accept_negated_boolean_views_incrementally():
    m = Model()
    b = m.bool("b")
    assert m.solve().ok
    view = m.as_int(~b)
    rem = m.modulo(view, 2)
    scaled = m.scale(view, -3)
    m &= ~b
    result = m.solve()
    assert result.ok
    assert result[rem] == 1
    assert result[scaled] == -3


def test_sum_var_rejects_foreign_literals_without_mutation():
    m = Model()
    x = m.int("x", 0, 2)
    foreign = Model().bool("foreign")
    before = m._next_id, len(m._hard), set(m._container_names)
    with pytest.raises(ValueError):
        m.sum_var([x, foreign])
    assert (m._next_id, len(m._hard), set(m._container_names)) == before


@pytest.mark.parametrize("op", ["__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__"])
@pytest.mark.parametrize("reverse", [False, True])
def test_derived_comparison_or_literals(op, reverse):
    m = Model()
    x = m.int("x", -4, 8)
    b, c = m.bool("b"), m.bool("c")
    constraint = getattr(x // 3, op)(2)
    before = m._next_id, len(m._hard)
    disjunction = (b | constraint) if reverse else (constraint | b)
    disjunction = disjunction | ~c
    assert (m._next_id, len(m._hard)) == before
    m &= disjunction
    with Solver(name="g4", bootstrap_with=m.to_cnf().clauses) as solver:
        for xv, bv, cv in itertools.product(range(-4, 9), (False, True), (False, True)):
            cuts = [lit.id if xv >= x.lb + i + 1 else -lit.id
                    for i, lit in enumerate(x._threshold_lits)]
            cuts += [b.id if bv else -b.id, c.id if cv else -c.id]
            expected = getattr(xv // 3, op)(2) or bv or not cv
            assert solver.solve(assumptions=cuts) == expected


def test_pb_or_checks_model_and_rejects_general_formula_disjunction():
    m = Model()
    b = m.bool("b")
    constraint = 2 * b >= 1
    other = Model().bool("foreign")
    for make in (lambda: constraint | other, lambda: other | constraint):
        with pytest.raises(ValueError):
            make()
    with pytest.raises(TypeError):
        constraint | (2 * b <= 0)
