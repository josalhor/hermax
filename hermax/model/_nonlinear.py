"""Exact bounded nonlinear operations, compiled to clauses and linear PB sums."""

from hermax.internal.operation_cache import _Identity
from .expressions import PBExpr, PBConstraint, Term, Literal, Clause, ClauseGroup, _LazyIntExpr, _ensure_model
from .variables import IntVar
from ._binary_integer import compile_pb


_PRODUCT_TABLE_PAIRS = 64
_SQUARE_TABLE_VALUES = 32


def _validate(model, value):
    if not isinstance(value, (IntVar, Literal, _LazyIntExpr, PBExpr, Term, int)):
        raise TypeError("Expected an integer variable, Boolean literal, or integer expression.")
    _ensure_model(model, value.literal if isinstance(value, Term) else value)
    expression_bounds(value)


def expression_bounds(value):
    """Static integer bounds without realizing lazy derived expressions."""
    if isinstance(value, (IntVar, _LazyIntExpr)):
        return value.lb, value.ub
    if isinstance(value, int):
        return int(value), int(value)
    expr = PBExpr.from_item(value)
    if not isinstance(expr.constant, int):
        raise TypeError("Nonlinear operations require integer-valued expressions.")
    constant = expr.constant
    coefficients = {}
    for term in expr.terms:
        c = term.coefficient
        if not isinstance(c, int):
            raise TypeError("Nonlinear operations require integer-valued expressions.")
        if not term.literal.polarity:
            constant += c
            c = -c
        index = term.literal.id
        coefficients[index] = coefficients.get(index, 0) + c
    lo = constant + sum(min(0, c) for c in coefficients.values())
    hi = constant + sum(max(0, c) for c in coefficients.values())
    lazy = {}
    for c, source in expr.int_terms:
        if not isinstance(c, int):
            raise TypeError("Nonlinear operations require integer-valued expressions.")
        key = id(source)
        old = lazy.get(key)
        lazy[key] = (source, c + (old[1] if old else 0))
    for source, c in lazy.values():
        a, b = source.lb, source.ub
        lo += min(c*a, c*b)
        hi += max(c*a, c*b)
    return lo, hi


def _canonical(model, value):
    expr = PBExpr.from_item(value)._realize_int_terms(model)
    constant = expr.constant
    coefficients = {}
    for term in expr.terms:
        c = term.coefficient
        if not term.literal.polarity:
            constant += c
            c = -c
        coefficients[term.literal.id] = coefficients.get(term.literal.id, 0) + c
    terms = tuple(sorted((i, c) for i, c in coefficients.items() if c))
    normalized = PBExpr(model, [Term(c, model._dimacs_to_lit(i)) for i, c in terms], constant)
    return normalized, (terms, constant)


def _linear_integer(model, value):
    if isinstance(value, _LazyIntExpr):
        value = value._realize()
    if isinstance(value, (IntVar, Literal, int)):
        return model.as_int(value)
    lo, hi = expression_bounds(value)
    expr, key = _canonical(model, value)
    if not expr.terms:
        return model.as_int(expr.constant)

    def build():
        out = model.int(model._reserve_name(None), lo, hi)
        out._register_value_definition(model._compile_pb_compare(PBExpr.from_item(out), '==', expr))
        return out

    return model._operation_cache.get_or_create((_linear_integer, key), build)


def _named(result, name):
    return result if name is None else IntVar._from_offset(result, 0, name)


def _and(model, a, b):
    if a == b:
        return model._dimacs_to_lit(a)
    if a == -b:
        return None
    key = (_and, *sorted((a, b)))

    def build():
        out = model.fresh_internal_bool()
        x, y = model._dimacs_to_lit(a), model._dimacs_to_lit(b)
        group = ClauseGroup(model, [Clause(model, [~out, x]), Clause(model, [~out, y]),
                                   Clause(model, [out, ~x, ~y])])
        model._register_literal_definition(out, group)
        return out

    return model._operation_cache.get_or_create(key, build)


def _mask(model, control, source):
    out = model.int(model._reserve_name(None), min(0, source.lb), max(0, source.ub))
    clauses = []
    if not out._binary_primary and not source._binary_primary:
        for k in range(out.lb+1, out.ub+1):
            y = out >= k
            if k <= source.lb:
                clauses.extend(model._equiv_literals_group(y, control))
            elif k > source.ub:
                clauses.extend(model._equiv_literals_group(y, ~control))
            else:
                x = source >= k
                if k > 0:
                    clauses.extend([Clause(model, [~y, control]), Clause(model, [~y, x]),
                                    Clause(model, [y, ~control, ~x])])
                else:
                    clauses.extend([Clause(model, [control, y]), Clause(model, [~x, y]),
                                    Clause(model, [~y, ~control, x])])
        out._register_value_definition(ClauseGroup(model, clauses))
    elif source.lb == 0 and out._binary_primary:
        for yi, xi in zip(out._get_binary_view(), source._get_binary_view()):
            y, x = model._dimacs_to_lit(yi), model._dimacs_to_lit(xi)
            clauses.extend([Clause(model, [~y, control]), Clause(model, [~y, x]),
                            Clause(model, [y, ~control, ~x])])
        out._register_value_definition(ClauseGroup(model, clauses))
    else:
        terms = [source.lb * control]
        c = model._lit_to_dimacs(control)
        for i, bit in enumerate(source._get_binary_view()):
            gate = _and(model, c, bit)
            if gate is not None:
                terms.append((1 << i) * gate)
        from .expressions import sum_expr
        out._register_value_definition(compile_pb(model, PBExpr.from_item(out), '==', sum_expr(terms)))
    return out


def product(model, left, right, name=None):
    _validate(model, left)
    _validate(model, right)
    if name is not None:
        model._assert_names_available(name)
    a, b = _linear_integer(model, left), _linear_integer(model, right)
    if id(a) > id(b):
        a, b = b, a
    key = (product, _Identity(a), _Identity(b))

    def build():
        if a.lb == a.ub or b.lb == b.ub:
            constant, other = (a.lb, b) if a.lb == a.ub else (b.lb, a)
            return model.as_int(0) if constant == 0 else model.scale(other, constant)
        if a.lb == b.lb == 0 and a.ub == b.ub == 1:
            gate = _and(model, a._get_binary_view()[0], b._get_binary_view()[0])
            return model.as_int(0) if gate is None else model.as_int(gate)
        if a.lb == 0 and a.ub == 1:
            return _mask(model, model._dimacs_to_lit(a._get_binary_view()[0]), b)
        if b.lb == 0 and b.ub == 1:
            return _mask(model, model._dimacs_to_lit(b._get_binary_view()[0]), a)
        square = a._encoding_owner() is b._encoding_owner() and a.lb == b.lb
        corners = [x*y for x in (a.lb, a.ub) for y in (b.lb, b.ub)]
        lo, hi = min(corners), max(corners)
        if square:
            lo = 0 if a.lb <= 0 <= a.ub else min(a.lb*a.lb, a.ub*a.ub)
        out = model.int(model._reserve_name(None), lo, hi)
        if square and a.ub-a.lb+1 <= _SQUARE_TABLE_VALUES:
            definition = model.table([a, out], allowed=[(v, v*v) for v in range(a.lb, a.ub+1)])
        elif (a.ub-a.lb+1)*(b.ub-b.lb+1) <= _PRODUCT_TABLE_PAIRS:
            definition = model.table([a, b, out], allowed=[(x,y,x*y) for x in range(a.lb,a.ub+1) for y in range(b.lb,b.ub+1)])
        else:
            from .expressions import sum_expr
            ax, by = a._get_binary_view(), b._get_binary_view()
            terms = [a.lb*b.lb]
            terms.extend((b.lb << i)*model._dimacs_to_lit(bit) for i,bit in enumerate(ax) if b.lb)
            terms.extend((a.lb << j)*model._dimacs_to_lit(bit) for j,bit in enumerate(by) if a.lb)
            for i, x in enumerate(ax):
                for j, y in enumerate(by):
                    gate = _and(model, x, y)
                    if gate is not None:
                        terms.append((1 << (i+j))*gate)
            definition = compile_pb(model, PBExpr.from_item(out), '==', sum_expr(terms))
        out._register_value_definition(definition)
        return out

    return _named(model._operation_cache.get_or_create(key, build), name)


def absolute(model, source, name=None):
    _validate(model, source)
    if name is not None:
        model._assert_names_available(name)
    if isinstance(source, _LazyIntExpr):
        source = source._realize()
    if isinstance(source, (Literal, int)):
        source = model.as_int(source)
    lo, hi = expression_bounds(source)
    if isinstance(source, IntVar):
        if lo >= 0:
            return _named(source, name)
        if hi <= 0:
            return model.scale(source, -1, name=name)
    expr, key = _canonical(model, source)
    # abs(e) and abs(-e) share one definition.
    negative = (tuple((i, -c) for i, c in key[0]), -key[1])
    key = min(key, negative)

    def build():
        if not expr.terms:
            return model.as_int(abs(expr.constant))
        lower = lo if lo >= 0 else -hi if hi <= 0 else 0
        out = model.int(model._reserve_name(None), lower, max(abs(lo), abs(hi)))
        if lo >= 0 or hi <= 0:
            definition = model._compile_pb_compare(PBExpr.from_item(out), '==', expr if lo >= 0 else -expr)
        else:
            sign = source >= 0 if isinstance(source, IntVar) else model.fresh_internal_bool()
            parts = [] if isinstance(source, IntVar) else [(expr >= 0).iff(sign)]
            parts.extend([(out == expr).only_if(sign), (out == -expr).only_if(~sign)])
            definition = ClauseGroup(model, [clause for part in parts
                                             for clause in (part.clauses() if isinstance(part, PBConstraint) else part)])
        out._register_value_definition(definition)
        return out

    return _named(model._operation_cache.get_or_create((absolute, key), build), name)
