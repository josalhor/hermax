"""Compact SAT encodings for finite-domain global constraints."""
from numbers import Integral
from .expressions import Clause, ClauseGroup
from .variables import IntVar


def _items(model, items):
    items = tuple(items)
    if any(not isinstance(x, IntVar) for x in items):
        raise TypeError('Global constraints require IntVar items.')
    if any(x._model is not model for x in items):
        raise ValueError('Variables belong to different models.')
    return items


def _group(model, parts):
    result = ClauseGroup(model, [])
    for part in parts:
        result = result & model._as_clausegroup(part)
    return result


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
                allowed = model.bool()
                matches = [x == v for v in excluded]
                parts.append(Clause(model, [~allowed, *matches]))
                parts.append((x == y).only_if(allowed))
                parts.append((x != y).only_if(~allowed))
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
    parts = []
    if items:
        for a,b in zip(values, values[1:]):
            parts.append(~(items[0] == b))
            seen = items[0] == a
            for i,x in enumerate(items[1:],1):
                parts.append((x == b).implies(seen))
                if i < len(items)-1:
                    prefix = model.bool()
                    parts.append((seen | (x == a)).iff(prefix))
                    seen = prefix
    return _group(model, parts)


def regular(model, items, transitions, start, accepting):
    items = _items(model, items)
    transitions = tuple(transitions)
    accepting = set(accepting)
    states = {start, *accepting}
    for a,v,b in transitions:
        if not isinstance(v, Integral):
            raise TypeError('Transition labels must be integers.')
        states.update((a,b))
    ids = {state:i for i,state in enumerate(states)}
    if not items:
        return _group(model, [start in accepting])
    tag = str(model.fresh_internal_bool().id)
    previous = model.int('_regular_' + tag + '_start', ids[start], ids[start])
    parts = []
    rows = [(ids[a],int(v),ids[b]) for a,v,b in transitions]
    for i, x in enumerate(items):
        nxt = model.int('_regular_' + tag + '_' + str(i), 0, len(ids)-1)
        parts.append(model.table([previous,x,nxt], allowed=rows))
        previous = nxt
    parts.append(Clause(model, [previous == ids[a] for a in accepting]))
    return _group(model, parts)


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
            match = items[level] == value
            if child == terminal:
                terms.append(match)
            else:
                suffix, term = signals[child], model.bool()
                parts.extend([~term | match, ~term | suffix, ~match | ~suffix | term])
                terms.append(term)
        signal = model.bool()
        signals[node] = signal
        if terms:
            clause = Clause(model, terms)
            parts.append(clause.iff(signal))
        else:
            parts.append(~signal)
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
        parts.append(Clause(model, [active, *[x == int(v) for v in set(excluded)]]))
        parts.append((x == representative).only_if(active))
    return _group(model, parts)
