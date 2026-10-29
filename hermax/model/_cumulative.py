"""Cumulative resource constraints with explicit posting and reification."""

from .expressions import (
    Clause,
    ClauseGroup,
    DeferredClauseGroup,
    Literal,
    PBConstraint,
    sum_expr,
    _BooleanComposition,
    _detection_error,
    _ensure_same_model_pair_fast,
)
from .variables import IntVar


def _parts_group(model, parts):
    clauses, amo, eo = [], [], []
    for part in parts:
        group = model._as_clausegroup(part)
        while isinstance(group, DeferredClauseGroup):
            group = group._realize()
        clauses.extend(group._clauses)
        amo.extend(group._copy_groups(group._amo_groups))
        eo.extend(group._copy_groups(group._eo_groups))
    return ClauseGroup._from_dimacs_trusted(
        model, clauses, amo_groups=amo, eo_groups=eo
    )


class _CumulativeEncoding:
    def __init__(self, model, jobs, capacity, backend):
        self.model = model
        self.jobs = jobs
        self.capacity = capacity
        self.begin = min((s.lb for s, _, _ in jobs), default=0)
        self.end = max((s.ub + d + 1 for s, d, _ in jobs), default=0)
        work = sum(s.ub - s.lb + 1 for s, _, _ in jobs)
        self.backend = (
            ("task" if work < self.end - self.begin else "time")
            if backend == "auto"
            else backend
        )
        self._positive = None
        self._negative = None

    def _and_literal(self, left, right, parts):
        m = self.model
        true = m._get_bool_constant_literal(True)
        false = m._get_bool_constant_literal(False)
        ld, rd = m._lit_to_dimacs(left), m._lit_to_dimacs(right)
        if ld == m._lit_to_dimacs(false) or rd == m._lit_to_dimacs(false) or ld == -rd:
            return false
        if ld == m._lit_to_dimacs(true):
            return right
        if rd == m._lit_to_dimacs(true) or ld == rd:
            return left
        result = m.bool()
        parts.append(
            ClauseGroup(
                m,
                [
                    Clause(m, [~result, left]),
                    Clause(m, [~result, right]),
                    Clause(m, [~left, ~right, result]),
                ],
            )
        )
        return result

    def _order_indicator(self, left, duration, right, parts):
        relation = left._relop_intvar(right, "<=", duration)
        if not relation:
            return self.model._get_bool_constant_literal(True)
        if any(not clause for clause in relation):
            return self.model._get_bool_constant_literal(False)
        indicator = self.model.bool()
        parts.append(relation.only_if(indicator))
        return indicator

    def _load(self, time, parts):
        terms = []
        m = self.model
        true = m._get_bool_constant_literal(True)
        false = m._get_bool_constant_literal(False)
        for start, duration, demand in self.jobs:
            active = self._and_literal(
                start <= time, start >= time - duration + 1, parts
            )
            dim = m._lit_to_dimacs(active)
            if dim == m._lit_to_dimacs(false):
                continue
            terms.append(demand if dim == m._lit_to_dimacs(true) else demand * active)
        return sum_expr(terms)

    def _events(self):
        if self.backend == "time":
            yield from range(self.begin, self.end)
            return
        intervals = sorted((start.lb, start.ub) for start, _, _ in self.jobs)
        if not intervals:
            return
        lower, upper = intervals[0]
        for lo, hi in intervals[1:]:
            if lo <= upper + 1:
                upper = max(upper, hi)
            else:
                yield from range(lower, upper + 1)
                lower, upper = lo, hi
        yield from range(lower, upper + 1)

    def positive_parts(self):
        if self._positive is not None:
            return self._positive
        m, parts = self.model, []
        if not self.jobs:
            self._positive = parts
            return parts
        m._get_bool_constant_literal(True)
        m._get_bool_constant_literal(False)
        if self.capacity == 0:
            self._positive = [False]
            return self._positive
        for i, (si, di, ri) in enumerate(self.jobs):
            for sj, dj, rj in self.jobs[i + 1 :]:
                if ri + rj > self.capacity:
                    left = self._order_indicator(si, di, sj, parts)
                    right = self._order_indicator(sj, dj, si, parts)
                    parts.append(Clause(m, [left, right]))
        # A load increase can occur only at an actual job start, which is
        # included in the union of possible start times.
        for time in self._events():
            parts.append(self._load(time, parts) <= self.capacity)
        self._positive = parts
        return parts

    def negative_parts(self):
        if self._negative is not None:
            return self._negative
        m, parts, witnesses = self.model, [], []
        # Overload is witnessed at a time tick, or at an actual job start.
        for time in self._events():
            cut = self._load(time, parts) > self.capacity
            if cut is False:
                continue
            witness = m.bool()
            witnesses.append(witness)
            if cut is not True:
                parts.append(cut.only_if(witness))
        parts.append(Clause(m, witnesses))
        self._negative = parts
        return parts


class _CumulativeConstraint(_BooleanComposition):
    __slots__ = ("_encoding", "_conditions")

    def __init__(self, encoding, conditions=()):
        self._encoding = encoding
        self._conditions = conditions
        super().__init__(encoding.model, self._positive_group, self._negative_group)

    def _parts(self):
        m = self._model
        for part in self._encoding.positive_parts():
            for condition in self._conditions:
                part = (
                    part.only_if(condition)
                    if isinstance(part, PBConstraint)
                    else m._as_clausegroup(part).only_if(condition)
                )
            yield part

    def _posting_parts(self):
        return self._parts() if self._compiled is None else None

    def _positive_group(self):
        return _parts_group(self._model, self._parts())

    def _negative_group(self):
        parts = [*self._encoding.negative_parts(), *self._conditions]
        return _parts_group(self._model, parts)

    def only_if(self, condition):
        if not isinstance(condition, Literal):
            raise _detection_error()
        _ensure_same_model_pair_fast(self, condition)
        if self._negative is None:
            return super().only_if(condition)
        return _CumulativeConstraint(self._encoding, (*self._conditions, condition))


def cumulative_constraint(
    model, starts, durations, demands, capacity, *, backend="auto"
):
    if isinstance(capacity, bool) or not isinstance(capacity, int):
        raise TypeError("cumulative() expects an integer capacity.")
    if capacity < 0:
        raise ValueError("cumulative() expects nonnegative capacity.")
    if backend not in ("auto", "time", "task"):
        raise ValueError(
            f"cumulative() backend must be 'auto', 'time', or 'task'; got {backend!r}"
        )
    starts, durations, demands = tuple(starts), tuple(durations), tuple(demands)
    if not (len(starts) == len(durations) == len(demands)):
        raise ValueError(
            "cumulative() expects starts, durations, and demands of equal length."
        )
    if any(not isinstance(s, IntVar) for s in starts):
        raise TypeError("cumulative() expects IntVar starts.")
    if any(s._model is not model for s in starts):
        raise ValueError("Variables belong to different models.")
    for values, label in ((durations, "durations"), (demands, "demands")):
        if any(isinstance(v, bool) or not isinstance(v, int) for v in values):
            raise TypeError(f"cumulative() expects integer {label}.")
        if any(v < 0 for v in values):
            raise ValueError(f"cumulative() does not support negative {label}.")
    jobs = tuple(
        (s, d, r) for s, d, r in zip(starts, durations, demands) if d > 0 and r > 0
    )
    return _CumulativeConstraint(_CumulativeEncoding(model, jobs, capacity, backend))
