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
        self._variable_events = any(start._binary_primary for start, _, _ in jobs)
        self._point_loads = {}

    def _load(self, time):
        if isinstance(time, IntVar):
            key = id(time)
            if key not in self._point_loads:
                terms = []
                m = self.model
                for start, duration, demand in self.jobs:
                    if start is time:
                        terms.append(demand)
                        continue
                    active = m._predicate_bool(
                        lambda result, s=start, d=duration: result[s] <= result[time] < result[s] + d
                    )
                    present = start._relop_intvar(time, "<=") & time._relop_intvar(start, "<", -duration)
                    m._register_literal_definition(active, present.iff(active))
                    terms.append(demand * active)
                self._point_loads[key] = sum_expr(terms)
            return self._point_loads[key]
        terms = []
        m = self.model
        true = m._get_bool_constant_literal(True)
        false = m._get_bool_constant_literal(False)
        for start, duration, demand in self.jobs:
            active = start.in_range(time - duration + 1, time)
            dim = m._lit_to_dimacs(active)
            if dim == m._lit_to_dimacs(false):
                continue
            terms.append(demand if dim == m._lit_to_dimacs(true) else demand * active)
        return sum_expr(terms)

    def _events(self):
        if self._variable_events:
            # Any overload begins at an actual task start. Compare against
            # those variable-valued events instead of enumerating wide times.
            seen = set()
            for start, _, _ in self.jobs:
                if id(start) not in seen:
                    seen.add(id(start))
                    yield start
            return
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

    def positive_parts(self, *, pairwise_only=False):
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
                    left = si._relop_intvar(sj, "<=", di)
                    right = sj._relop_intvar(si, "<=", dj)
                    if left.is_empty() or right.is_empty():
                        continue
                    if left.single_clause_or_none() == ():
                        parts.append(right)
                    elif right.single_clause_or_none() == ():
                        parts.append(left)
                    else:
                        selector = m.bool()
                        parts.extend((left.only_if(selector), right.only_if(~selector)))
        if pairwise_only and all(r <= self.capacity for _, _, r in self.jobs) and all(
            ri + rj > self.capacity
            for i, (_, _, ri) in enumerate(self.jobs)
            for _, _, rj in self.jobs[i + 1 :]
        ):
            # Pairwise exclusion is sufficient when every pair overloads.
            # Do not cache this posting-only form: reification retains load
            # circuits so overload can propagate to its result literal.
            return parts
        # A load increase can occur only at an actual job start, which is
        # included in the union of possible start times.
        for time in self._events():
            parts.append(self._load(time) <= self.capacity)
        self._positive = parts
        return parts

    def negative_parts(self):
        if self._negative is not None:
            return self._negative
        m, parts, witnesses = self.model, [], []
        # Overload is witnessed at a time tick, or at an actual job start.
        for time in self._events():
            cut = self._load(time) > self.capacity
            if cut is False:
                continue
            witness = m.bool()
            witnesses.append(witness)
            if cut is not True:
                parts.append(cut.only_if(witness))
        parts.append(Clause(m, witnesses))
        self._negative = parts
        return parts


def _value(assignment, integer):
    return assignment[integer] if isinstance(integer, IntVar) else integer


class _VariableCumulativeEncoding(_CumulativeEncoding):
    """General resource encoding; fixed jobs retain the specialized fast path.

    Activity and conditional demand values are exact definitions and are shared
    by positive and negative forms without constraining the input variables.
    """

    def __init__(self, model, jobs, capacity, backend):
        self.model, self.jobs, self.capacity = model, jobs, capacity
        self.begin = min((s.lb for s, _, _ in jobs), default=0)
        self.end = max((s.ub for s, _, _ in jobs), default=self.begin) + 1
        self.backend = backend
        # Actual start events avoid enumerating wide domains. The auto policy
        # is deliberately separate from the fixed-duration encoding's policy.
        self._variable_events = backend == "task"
        if backend == "auto":
            # Variable demand needs a conditional product at every event, so
            # favor fewer events. With fixed demand, unary event comparisons
            # cost more clauses: prefer ticks on moderately sized horizons.
            event_factor = 1 if any(isinstance(r, IntVar) for _, _, r in jobs) else 4
            self._variable_events = event_factor * len(jobs) < self.end - self.begin
            self.backend = "task" if self._variable_events else "time"
        self._positive = self._negative = None
        self._point_loads = {}
        self._products = {}
        self._demand_products = {}

    def _indicator(self, constraint, evaluate=None):
        m = self.model
        if isinstance(constraint, bool):
            return m._get_bool_constant_literal(constraint)
        if isinstance(constraint, Literal):
            return constraint
        result = m._predicate_bool(evaluate) if evaluate is not None else m.bool()
        m._register_literal_definition(result, constraint.iff(result))
        return result

    def _constant_value(self, literal):
        dimacs = self.model._lit_to_dimacs(literal)
        for value, constant in self.model._const_lits.items():
            constant_dimacs = self.model._lit_to_dimacs(constant)
            if dimacs == constant_dimacs:
                return value
            if dimacs == -constant_dimacs:
                return not value
        return None

    def _and(self, left, right):
        m = self.model
        a, b = m._lit_to_dimacs(left), m._lit_to_dimacs(right)
        left_value, right_value = self._constant_value(left), self._constant_value(right)
        if left_value is False:
            return left
        if right_value is False:
            return right
        if left_value is True:
            return right
        if right_value is True or a == b:
            return left
        if a == -b:
            return m._get_bool_constant_literal(False)
        key = tuple(sorted((a, b)))
        if key not in self._products:
            self._products[key] = self._indicator(
                left & right, lambda result: result[left] and result[right])
        return self._products[key]

    def _load(self, time):
        key = ("var", id(time)) if isinstance(time, IntVar) else ("time", time)
        if key in self._point_loads:
            return self._point_loads[key]
        m, terms = self.model, []
        for start, duration, demand in self.jobs:
            if start is time and (duration if isinstance(duration, int) else duration.lb) > 0:
                terms.append(demand)
                continue
            # Fixed durations use native order comparisons/range predicates.
            if start is time:
                active = self._indicator(duration > 0,
                    lambda result, d=duration: _value(result, d) > 0)
            elif isinstance(time, int) and isinstance(duration, int):
                active = start.in_range(time - duration + 1, time)
            else:
                begins = self._indicator(start <= time,
                    lambda result, s=start: result[s] <= _value(result, time))
                end_condition = self._end_condition(start, duration, time)
                ends = self._indicator(end_condition,
                    lambda result, s=start, d=duration: result[s] + _value(result, d) > _value(result, time))
                active = self._and(begins, ends)
            if isinstance(demand, int):
                terms.append(demand * active)
            else:
                terms.append(self._demand_contribution(demand, active))
        load = sum_expr(terms)
        self._point_loads[key] = load
        return load

    def _end_condition(self, start, duration, time):
        if isinstance(time, IntVar) and isinstance(duration, int):
            return time._relop_intvar(start, "<", -duration)
        return start + duration > time

    def _demand_contribution(self, demand, active):
        m = self.model
        constant = self._constant_value(active)
        if constant is not None:
            return demand if constant else 0
        key = (id(demand), m._lit_to_dimacs(active))
        if key not in self._demand_products:
            product = m.int(m._reserve_name(None), min(0, demand.lb), max(0, demand.ub))
            # These definitions are total, including for negative input values.
            # Nonnegativity belongs to the cumulative condition, not here.
            m &= (product == demand).only_if(active)
            m &= (product == 0).only_if(~active)
            self._demand_products[key] = product
        return self._demand_products[key]

    def positive_parts(self, *, pairwise_only=False):
        if self._positive is None:
            self._positive = [value >= 0 for _, d, r in self.jobs
                              for value in (d, r) if isinstance(value, IntVar) and value.lb < 0]
            if isinstance(self.capacity, IntVar) and self.capacity.lb < 0:
                self._positive.append(self.capacity >= 0)
            self._positive.extend(self._load(t) <= self.capacity for t in self._events())
        return self._positive

    def negative_parts(self):
        if self._negative is None:
            # Complement every conjunct, including input validity checks.
            indicators = [self._indicator(part)
                          for part in self.positive_parts()]
            self._negative = [Clause(self.model, [~lit for lit in indicators])]
        return self._negative


class _CumulativeConstraint(_BooleanComposition):
    __slots__ = ("_encoding", "_conditions")

    def __init__(self, encoding, conditions=()):
        self._encoding = encoding
        self._conditions = conditions
        super().__init__(encoding.model, self._positive_group, self._negative_group)

    def _parts(self, *, pairwise_only=False):
        m = self._model
        for part in self._encoding.positive_parts(pairwise_only=pairwise_only):
            for condition in self._conditions:
                part = (
                    part.only_if(condition)
                    if isinstance(part, PBConstraint)
                    else m._as_clausegroup(part).only_if(condition)
                )
            yield part

    def _posting_parts(self):
        return self._parts(pairwise_only=not self._conditions) if self._compiled is None else None

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
    if isinstance(capacity, bool) or not isinstance(capacity, (int, IntVar)):
        raise TypeError("cumulative() expects an integer or IntVar capacity.")
    if isinstance(capacity, int) and capacity < 0:
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
        if any(isinstance(v, bool) or not isinstance(v, (int, IntVar)) for v in values):
            raise TypeError(f"cumulative() expects integer or IntVar {label}.")
        if any(isinstance(v, int) and v < 0 for v in values):
            raise ValueError(f"cumulative() does not support negative {label}.")
    parameters = (*durations, *demands, capacity)
    if any(isinstance(v, IntVar) and v._model is not model for v in parameters):
        raise ValueError("Variables belong to different models.")
    if any(isinstance(v, IntVar) for v in parameters):
        # Keep zero jobs too: their variable arguments still have validity
        # conditions, even when they cannot contribute to resource load.
        return _CumulativeConstraint(_VariableCumulativeEncoding(
            model, tuple(zip(starts, durations, demands)), capacity, backend))
    jobs = tuple(
        (s, d, r) for s, d, r in zip(starts, durations, demands) if d > 0 and r > 0
    )
    return _CumulativeConstraint(_CumulativeEncoding(model, jobs, capacity, backend))
