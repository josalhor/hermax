"""Compact SAT encodings for finite-domain global constraints."""
from numbers import Integral
from .expressions import Clause, ClauseGroup, _BooleanComposition, DeferredClauseGroup, Literal
from .variables import IntVar


def _items(model, items):
    items = tuple(items)
    if any(not isinstance(x, IntVar) for x in items):
        raise TypeError('Global constraints require IntVar items.')
    if any(x._model is not model for x in items):
        raise ValueError('Variables belong to different models.')
    return items


def _flatten(model, parts):
    clauses, amo, eo = [], [], []
    for part in parts:
        group = model._as_clausegroup(part)
        while isinstance(group, DeferredClauseGroup):
            group = group._realize()
        clauses.extend(group._clauses)
        amo.extend(group._copy_groups(group._amo_groups))
        eo.extend(group._copy_groups(group._eo_groups))
    return ClauseGroup._from_dimacs_trusted(model, clauses, amo_groups=amo, eo_groups=eo)


def _defined(model, formula):
    if isinstance(formula, Literal):
        return formula
    flag = model.bool()
    model._register_literal_definition(
        flag, formula.iff(flag) if hasattr(formula, "iff")
        else model._as_clausegroup(formula).iff(flag))
    return flag


def _group(model, parts):
    parts = tuple(parts)
    def negative():
        flags = [_defined(model, part) for part in parts]
        return _flatten(model, [Clause(model, [~flag for flag in flags])])
    return _BooleanComposition(model, lambda: _flatten(model, parts), negative)


def _excluded(model, x, values):
    return Clause(model, [x == v for v in values if x.lb <= v <= x.ub])


def all_different_except(model, items, excluded=(0,)):
    items = _items(model, items)
    excluded = tuple(excluded)
    if any(not isinstance(v, Integral) for v in excluded):
        raise TypeError('Excluded values must be integers.')
    excluded = set(map(int, excluded))
    parts = []
    if any(x._binary_primary for x in items) or sum(x.ub-x.lb+1 for x in items) > 4*len(items)**2:
        for i, x in enumerate(items):
            for y in items[i+1:]:
                # Equal pairs are allowed only at an excluded value.
                excluded_x = _defined(model, _excluded(model, x, excluded))
                parts.append((x != y).only_if(~excluded_x))
    else:
        columns = {}
        for x in items:
            for value in range(x.lb, x.ub+1):
                if value not in excluded:
                    columns.setdefault(value, []).append(x)
        parts.extend(sum(x == v for x in owners) <= 1 for v, owners in columns.items() if len(owners)>1)
    return _group(model, parts)


def precedence(model, items, values):
    items = _items(model, items)
    values = tuple(values)
    if any(not isinstance(v, Integral) for v in values):
        raise TypeError('Precedence values must be integers.')

    def matches(item, value):
        if item.lb <= value <= item.ub:
            return item == int(value)
        return model._get_bool_constant_literal(False)

    parts = []
    if items:
        for a,b in zip(values, values[1:]):
            parts.append(~matches(items[0], b))
            seen = matches(items[0], a)
            for i,x in enumerate(items[1:],1):
                parts.append(matches(x, b).implies(seen))
                if i < len(items)-1:
                    prefix = model.bool()
                    model._register_literal_definition(prefix, (seen | matches(x, a)).iff(prefix))
                    seen = prefix
    return _group(model, parts)


def regular(model, items, transitions, start, accepting):
    items = _items(model, items)
    transitions = tuple(transitions)
    accepting = set(accepting)
    for a,v,b in transitions:
        if not isinstance(v, Integral):
            raise TypeError('Transition labels must be integers.')
    if not items:
        return _group(model, [start in accepting])
    previous = {start: model._get_bool_constant_literal(True)}
    for x in items:
        incoming = {}
        for a, value, b in transitions:
            if a not in previous or not x.lb <= int(value) <= x.ub:
                continue
            term = _defined(model, previous[a] & (x == int(value)))
            incoming.setdefault(b, []).append(term)
        previous = {state: _defined(model, Clause(model, terms))
                    for state, terms in incoming.items()}
    return _group(model, [Clause(model, [flag for state, flag in previous.items()
                                       if state in accepting])])


def mdd(model, items, transitions, start):
    items = _items(model, items)
    edges = {}
    for a,v,b in transitions:
        if not isinstance(v, Integral):
            raise TypeError('Transition labels must be integers.')
        if v in edges.setdefault(a, {}):
            raise ValueError('MDD transitions must be deterministic.')
        edges[a][int(v)] = b
    levels = {start:0}
    frontier = {start}
    for level in range(len(items)):
        nxt = set()
        for node in frontier:
            for child in edges.get(node, {}).values():
                if child in levels and levels[child] != level+1:
                    raise ValueError('MDD must be acyclic and layered.')
                levels[child] = level+1
                nxt.add(child)
        frontier = nxt
    if len(frontier) != 1 or any(edges.get(n) for n in frontier):
        raise ValueError('MDD requires one terminal at the final layer.')
    terminal = next(iter(frontier))
    if not items:
        return ClauseGroup(model, [])
    parts, signals = [], {}
    for node,level in sorted(levels.items(), key=lambda p:p[1], reverse=True):
        if node == terminal:
            continue
        terms = []
        for value,child in edges.get(node, {}).items():
            if not items[level].lb <= value <= items[level].ub:
                continue
            match = items[level] == value
            if child == terminal:
                terms.append(match)
            else:
                suffix, term = signals[child], model.bool()
                model._register_literal_definition(term, _flatten(model, [~term | match, ~term | suffix, ~match | ~suffix | term]))
                terms.append(term)
        signal = model.bool()
        signals[node] = signal
        if terms:
            clause = Clause(model, terms)
            model._register_literal_definition(signal, clause.iff(signal))
        else:
            model._register_literal_definition(signal, model._as_clausegroup(~signal))
    parts.append(signals[start])
    return _group(model, parts)


def all_equal_except(model, items, excluded=(0,)):
    items = _items(model, items)
    excluded = tuple(excluded)
    if any(not isinstance(v, Integral) for v in excluded):
        raise TypeError('Excluded values must be integers.')
    if len(items) < 2:
        return ClauseGroup(model, [])
    tag = str(model.fresh_internal_bool().id)
    representative = model.int('_equal_except_' + tag,
                               min(x.lb for x in items), max(x.ub for x in items))
    parts = []
    for x in items:
        active = model.bool()
        parts.append(Clause(model, [active, *[x == int(v) for v in set(excluded) if x.lb <= int(v) <= x.ub]]))
        parts.append((x == representative).only_if(active))
    def negative():
        witnesses = []
        excluded_values = set(map(int, excluded))
        excluded_flags = [_defined(model, _excluded(model, x, excluded_values))
                          for x in items]
        for i, x in enumerate(items):
            for j in range(i + 1, len(items)):
                different = _defined(model, x != items[j])
                witnesses.append(_defined(
                    model, ~excluded_flags[i] & ~excluded_flags[j] & different))
        return _flatten(model, [Clause(model, witnesses)])
    return _BooleanComposition(model, lambda: _flatten(model, parts), negative)
