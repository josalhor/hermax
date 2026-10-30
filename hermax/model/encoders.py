from __future__ import annotations
import math
import sys
import time
from dataclasses import dataclass
from functools import reduce
from typing import Iterable, Mapping, Optional, Sequence
from hermax.encoder._packed import PBAMOEnc
from hermax.encoder import _weighted_sum
from ._integer_sum import compile_sum, addition_encoding
from ._counting import count_thresholds, merge_thresholds, _append_implication
from ._weighted_integer_sum import compile_weighted_sum
from ._integer_affine import extract_integer_sum
from hermax.internal.pb_normalize import normalize_signed_terms

from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from .expressions import *
    from .variables import *
    from .encoders import *
    from .core import *

from .expressions import *
from .expressions import _detection_error, _nonlinear_error, _ensure_same_model, _ensure_same_model_pair_fast, _LazyIntExpr
from .variables import *
from .variables import _BaseVector, _BaseDict, _BaseMatrixView, _MultiplexerInt, _VectorElementInt

_CountOutputs = list[bool | Literal] | dict[int, bool | Literal]


@dataclass
class EncodingEvent:
    """Single profiled encoding event."""

    event_id: int
    parent_id: int | None
    kind: str
    label: str | None
    metadata: dict[str, object]
    duration_sec: float = 0.0
    literal_delta: int = 0
    hard_clause_delta: int = 0
    soft_clause_delta: int = 0
    pending_pb_delta: int = 0
    success: bool = True
    _start_ns: int = 0
    _start_top_id: int = 0
    _start_hard: int = 0
    _start_soft: int = 0
    _start_pending_pb: int = 0


class EncodingProfile:
    """Structured encoding profiler with nested event scopes."""

    __slots__ = ("events", "_active_stack", "_next_event_id")

    def __init__(self):
        self.events: list[EncodingEvent] = []
        self._active_stack: list[EncodingEvent] = []
        self._next_event_id = 1

    def begin(
        self,
        model: "Model",
        *,
        kind: str,
        label: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EncodingEvent:
        event = EncodingEvent(
            event_id=self._next_event_id,
            parent_id=self._active_stack[-1].event_id if self._active_stack else None,
            kind=str(kind),
            label=None if label is None else str(label),
            metadata=dict(metadata or {}),
            _start_ns=time.perf_counter_ns(),
            _start_top_id=model._top_id(),
            _start_hard=len(model._hard),
            _start_soft=len(model._soft),
            _start_pending_pb=len(model._pending_pb_constraints),
        )
        self._next_event_id += 1
        self._active_stack.append(event)
        return event

    def end(self, model: "Model", event: EncodingEvent, *, success: bool = True) -> None:
        if not self._active_stack or self._active_stack[-1] is not event:
            raise RuntimeError("EncodingProfile stack corruption: ending non-top event.")
        self._active_stack.pop()
        event.duration_sec = max(0.0, (time.perf_counter_ns() - event._start_ns) / 1_000_000_000.0)
        event.literal_delta = int(model._top_id() - event._start_top_id)
        event.hard_clause_delta = int(len(model._hard) - event._start_hard)
        event.soft_clause_delta = int(len(model._soft) - event._start_soft)
        event.pending_pb_delta = int(len(model._pending_pb_constraints) - event._start_pending_pb)
        event.success = bool(success)
        self.events.append(event)

    def current_event(self) -> EncodingEvent | None:
        return self._active_stack[-1] if self._active_stack else None

    def _summary(self, key_fn) -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        for ev in self.events:
            key = str(key_fn(ev))
            row = out.setdefault(
                key,
                {
                    "count": 0,
                    "duration_sec": 0.0,
                    "literal_delta": 0,
                    "hard_clause_delta": 0,
                    "soft_clause_delta": 0,
                    "pending_pb_delta": 0,
                    "failures": 0,
                },
            )
            row["count"] = int(row["count"]) + 1
            row["duration_sec"] = float(row["duration_sec"]) + float(ev.duration_sec)
            row["literal_delta"] = int(row["literal_delta"]) + int(ev.literal_delta)
            row["hard_clause_delta"] = int(row["hard_clause_delta"]) + int(ev.hard_clause_delta)
            row["soft_clause_delta"] = int(row["soft_clause_delta"]) + int(ev.soft_clause_delta)
            row["pending_pb_delta"] = int(row["pending_pb_delta"]) + int(ev.pending_pb_delta)
            if not ev.success:
                row["failures"] = int(row["failures"]) + 1
        return out

    def summary_by_kind(self) -> dict[str, dict[str, object]]:
        return self._summary(lambda ev: ev.kind)

    def summary_by_label(self) -> dict[str, dict[str, object]]:
        return self._summary(lambda ev: ev.label if ev.label is not None else "<none>")


@dataclass(frozen=True)
class _DeferredPBEntry:
    constraint: "PBConstraint"
    origin_event_id: int | None = None
    origin_kind: str | None = None
    origin_label: str | None = None


def _canonical_pb_cache_key(
    cmp_op: str,
    bound: int,
    lits: Sequence[int],
    weights: Sequence[int],
) -> tuple[str, int, tuple[tuple[int, int], ...]]:
    key_pairs = tuple(sorted((int(lit), int(weight)) for lit, weight in zip(lits, weights)))
    return (str(cmp_op), int(bound), key_pairs)


class _EncoderDispatch:
    """Internal dispatch for eager PB/cardinality comparator compilation."""

    @staticmethod
    def _normalize_pb(lhs: PBExpr, rhs: PBExpr) -> tuple[list[tuple[int, Literal]], int]:
        """Normalize a model PB difference through the shared PB core."""
        diff = lhs - rhs
        normalized = normalize_signed_terms(
            ((term.coefficient, term.literal) for term in diff.terms),
            diff.constant,
            flip=lambda literal: ~literal,
            key=lambda literal: (literal.id, literal.polarity),
        )
        return [(weight, literal) for weight, literal in normalized.terms], normalized.constant

    @staticmethod
    def _bound_from_zero_compare(op: str, const: int) -> tuple[str, int]:
        # Compare normalized sum + const OP 0  =>  sum OP' bound
        # where bound = -const (adjusted for strict ops).
        base = -const
        if op == "<=":
            return ("<=", base)
        if op == "<":
            return ("<=", base - 1)
        if op == ">=":
            return (">=", base)
        if op == ">":
            return (">=", base + 1)
        if op == "==":
            return ("==", base)
        raise ValueError(f"Unsupported comparator {op!r}")

    @staticmethod
    def _structured_overlap_for(model: "Model", pb_lit_ids: Sequence[int]) -> tuple[list[list[int]], list[list[int]]]:
        pb_lit_set = set(int(l) for l in pb_lit_ids)
        pb_amo_groups: list[list[int]] = []
        pb_eo_groups: list[list[int]] = []
        for group in model._known_amo_groups.values():
            overlap = [lit for lit in group if lit in pb_lit_set]
            if len(overlap) > 1:
                pb_amo_groups.append(overlap)
        for group in model._known_eo_groups.values():
            overlap = [lit for lit in group if lit in pb_lit_set]
            if len(overlap) == len(group) and len(overlap) > 1:
                pb_eo_groups.append(overlap)
            elif len(overlap) > 1:
                pb_amo_groups.append(overlap)
        return pb_amo_groups, pb_eo_groups

    @staticmethod
    def _compile_structured_auto_leq(model: "Model", lits: Sequence[int], weights: Sequence[int], bound: int) -> ClauseGroup:
        pb_lit_ids = [int(l) for l in lits]
        pb_weights = [int(w) for w in weights]
        pb_amo_groups, pb_eo_groups = _EncoderDispatch._structured_overlap_for(model, pb_lit_ids)
        return model._cnfplus_to_clausegroup(
            PBAMOEnc.auto_leq(
                lits=pb_lit_ids,
                weights=pb_weights,
                bound=int(bound),
                amo_groups=pb_amo_groups,
                eo_groups=pb_eo_groups,
                top_id=model._top_id(),
            )
        )

    @staticmethod
    def _compile_structured_auto_eq(model: "Model", lits: Sequence[int], weights: Sequence[int], bound: int) -> ClauseGroup:
        pb_lit_ids = [int(l) for l in lits]
        pb_weights = [int(w) for w in weights]
        pb_amo_groups, pb_eo_groups = _EncoderDispatch._structured_overlap_for(model, pb_lit_ids)
        return model._cnfplus_to_clausegroup(
            PBAMOEnc.auto_eq(
                lits=pb_lit_ids,
                weights=pb_weights,
                bound=int(bound),
                amo_groups=pb_amo_groups,
                eo_groups=pb_eo_groups,
                top_id=model._top_id(),
            )
        )

    @staticmethod
    def _extract_affine_parts(
        model: "Model", expr: PBExpr, *, allow_booleans: bool,
    ) -> tuple[list[tuple[IntVar, int]], list[tuple[Literal, int]], int] | None:
        """Recover complete, uniformly weighted integer ladders and residual Boolean terms."""
        if expr.int_terms:
            return None
        owners: dict[int, tuple[IntVar, int, set[int]]] = {}
        booleans: dict[tuple[int, bool], tuple[Literal, int]] = {}
        for term in expr.terms:
            coefficient = int(term.coefficient)
            if not coefficient:
                continue
            literal = term.literal
            info = model._intvar_threshold_owner_by_litid.get(literal.id)
            if info is None:
                if not allow_booleans:
                    return None
                boolean_key = literal.id, literal.polarity
                previous = booleans.get(boolean_key, (literal, 0))[1]
                booleans[boolean_key] = literal, previous + coefficient
                continue
            if not literal.polarity:
                return None
            owner, index = info
            owner_key = id(owner)
            if owner_key not in owners:
                owners[owner_key] = owner, coefficient, set()
            _, previous, seen = owners[owner_key]
            if coefficient != previous or index in seen:
                return None
            seen.add(index)

        integers = []
        offset = int(expr.constant)
        for owner, coefficient, seen in owners.values():
            # Ownership guarantees valid indices; duplicates were rejected above.
            if len(seen) != len(owner._threshold_lits):
                return None
            integers.append((owner, coefficient))
            offset -= coefficient * owner.lb
        return integers, [(literal, c) for literal, c in booleans.values() if c], offset

    @staticmethod
    def _extract_multi_int_affine(model: "Model", expr: PBExpr) -> tuple[list[tuple[IntVar, int]], int] | None:
        extracted = _EncoderDispatch._extract_affine_parts(model, expr, allow_booleans=False)
        if extracted is None:
            return None
        integers, _, offset = extracted
        return integers, offset

    _extract_integer_sum_with_bools = staticmethod(extract_integer_sum)

    @staticmethod
    def _flip_op_for_negative_scale(op: str) -> str:
        if op == "<=":
            return ">="
        if op == "<":
            return ">"
        if op == ">=":
            return "<="
        if op == ">":
            return "<"
        if op == "==":
            return "=="
        if op == "!=":
            return "!="
        raise ValueError(f"Unsupported comparator {op!r}")

    @staticmethod
    def _ceil_div(n: int, d: int) -> int:
        assert d > 0
        return -((-n) // d)

    @staticmethod
    def _int_cmp_constraint(x: IntVar, op: str, k: int) -> bool | Literal:
        if op == "==":
            if k < x.lb or k > x.ub:
                return False
            return x == k
        if op == "<=":
            if k < x.lb:
                return False
            if k >= x.ub:
                return True
            return x <= k
        if op == "<":
            if k <= x.lb:
                return False
            if k > x.ub:
                return True
            return x < k
        if op == ">=":
            if k <= x.lb:
                return True
            if k > x.ub:
                return False
            return x >= k
        if op == ">":
            if k < x.lb:
                return True
            if k >= x.ub:
                return False
            return x > k
        raise ValueError(f"Unsupported comparator {op!r}")

    _lit_implies = staticmethod(_append_implication)

    @staticmethod
    def _lit_conj_implies(
        clauses: list[Clause],
        model: "Model",
        left: bool | Literal,
        right: bool | Literal,
        consequent: bool | Literal,
    ) -> None:
        """Append CNF for ``(left and right) -> consequent`` with folding."""
        if isinstance(left, bool):
            if not left:
                return
            _EncoderDispatch._lit_implies(clauses, model, right, consequent)
            return
        if isinstance(right, bool):
            if not right:
                return
            _EncoderDispatch._lit_implies(clauses, model, left, consequent)
            return
        if left is right:
            _EncoderDispatch._lit_implies(clauses, model, left, consequent)
            return
        if left.id == right.id and left.polarity != right.polarity:
            return
        if isinstance(consequent, bool):
            if consequent:
                return
            clauses.append(Clause(model, [~left, ~right]))
            return
        clauses.append(Clause(model, [~left, ~right, consequent]))

    @staticmethod
    def _append_guarded_clause2(
        clauses: list[Clause],
        model: "Model",
        left: bool | Literal,
        right: bool | Literal,
        body: Sequence[Literal],
    ) -> None:
        """Append ``(~left or ~right or body...)`` with constant folding."""
        if isinstance(left, bool):
            if not left:
                return
            if isinstance(right, bool):
                if not right:
                    return
                clauses.append(Clause(model, list(body)))
                return
            clauses.append(Clause(model, [~right, *body]))
            return
        if isinstance(right, bool):
            if not right:
                return
            clauses.append(Clause(model, [~left, *body]))
            return
        if left is right:
            clauses.append(Clause(model, [~left, *body]))
            return
        if left.id == right.id and left.polarity != right.polarity:
            return
        clauses.append(Clause(model, [~left, ~right, *body]))

    @staticmethod
    def _negate_bool_or_lit(x: bool | Literal) -> bool | Literal:
        if isinstance(x, bool):
            return not x
        return ~x

    @staticmethod
    def _lit_and(clauses: list[Clause], model: "Model", a: bool | Literal, b: bool | Literal) -> bool | Literal:
        if isinstance(a, bool) and isinstance(b, bool):
            return a and b
        if isinstance(a, bool):
            return b if a else False
        if isinstance(b, bool):
            return a if b else False
        if a is b:
            return a
        if a.id == b.id and a.polarity != b.polarity:
            return False
        out = model.bool()
        clauses.append(Clause(model, [~out, a]))
        clauses.append(Clause(model, [~out, b]))
        clauses.append(Clause(model, [out, ~a, ~b]))
        return out

    @staticmethod
    def _lit_or(clauses: list[Clause], model: "Model", a: bool | Literal, b: bool | Literal) -> bool | Literal:
        if isinstance(a, bool) and isinstance(b, bool):
            return a or b
        if isinstance(a, bool):
            return True if a else b
        if isinstance(b, bool):
            return True if b else a
        if a is b:
            return a
        if a.id == b.id and a.polarity != b.polarity:
            return True
        out = model.bool()
        clauses.append(Clause(model, [~a, out]))
        clauses.append(Clause(model, [~b, out]))
        clauses.append(Clause(model, [a, b, ~out]))
        return out

    @staticmethod
    def _build_unary_sum_ge_ladder(
        model: "Model",
        left_desc: Sequence[bool | Literal],
        right_desc: Sequence[bool | Literal],
        *,
        thresholds=None,
    ) -> tuple[list[Clause], _CountOutputs]:
        total = len(left_desc) + len(right_desc)
        requested = range(1, total + 1) if thresholds is None else thresholds
        clauses, outputs = merge_thresholds(
            model, [left_desc, right_desc], requested,
            _EncoderDispatch._lit_and, _EncoderDispatch._lit_or,
        )
        if thresholds is None:
            return clauses, [True, *outputs.values()]
        return clauses, outputs

    @staticmethod
    def _addition_domain_cuts(model, x, y, z, target, *, equality=False):
        clauses = []
        if z.ub + target < x.ub + y.ub:
            clauses.extend(_EncoderDispatch._try_bivariate_int_fastpath(
                model, PBExpr.from_item(x + y), "<=", PBExpr.from_item(z.ub + target)
            ))
        if equality and z.lb + target > x.lb + y.lb:
            clauses.extend(_EncoderDispatch._try_bivariate_int_fastpath(
                model, PBExpr.from_item(x + y), ">=", PBExpr.from_item(z.lb + target)
            ))
        return clauses

    @staticmethod
    def _extract_addition(model, lhs, op, rhs):
        left = _EncoderDispatch._extract_multi_int_affine(model, lhs)
        right = _EncoderDispatch._extract_multi_int_affine(model, rhs)
        if left is None or right is None:
            return None
        coefficients = {}
        for items, sign in ((left[0], 1), (right[0], -1)):
            for variable, coefficient in items:
                previous = coefficients.get(id(variable), (variable, 0))[1]
                coefficients[id(variable)] = variable, previous + sign * coefficient
        items = [(v, c) for v, c in coefficients.values() if c]
        target = right[1] - left[1]
        if op in (">=", ">") or (op == "==" and sum(c == -1 for _, c in items) == 2):
            items = [(v, -c) for v, c in items]
            target = -target
            op = {">=": "<=", ">": "<", "==": "=="}[op]
        if op == "<":
            target -= 1
        positive = sorted((v for v, c in items if c == 1), key=lambda v: v.name)
        negative = [v for v, c in items if c == -1]
        if len(items) != 3 or len(positive) != 2 or len(negative) != 1:
            return None
        return positive[0], positive[1], negative[0], target

    @staticmethod
    def _try_unary_adder_eq_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile ``x + y == z`` (affine-shifted) via unary merge network."""
        if op != "==":
            return None
        addition = _EncoderDispatch._extract_addition(model, lhs, op, rhs)
        if addition is None:
            return None
        x, y, z, target = addition
        coeff_items = [(x, 1), (y, 1), (z, -1)]
        # Compact ladder uses (ub-lb) threshold bits.
        nx = len(x._threshold_lits)
        ny = len(y._threshold_lits)
        nz = len(z._threshold_lits)
        # Relation on ladder-count variables.
        # For affine relation lhs == rhs with coeffs built over values:
        #   sum(c_i * (cnt_i + lb_i)) + (loff - roff) == 0
        # -> sum(c_i * cnt_i) == - (sum(c_i * lb_i) + (loff - roff))
        delta = target - x.lb - y.lb + z.lb
        if addition_encoding(nx, ny, nz, delta, equality=True) == 'general':
            return compile_sum(model, coeff_items, -delta, "==")

        nsum = nx + ny
        lo = max(0, min(nsum + 1, delta))
        hi = min(nsum + 1, max(0, delta + nz + 1))
        clauses, ge = _EncoderDispatch._build_unary_sum_ge_ladder(
            model, x._threshold_lits, y._threshold_lits,
            thresholds=range(max(1, lo), min(nsum, hi) + 1),
        )
        # Channel boundary-inclusive cuts for exact equality with affine shift.
        # sum_ge(r) <-> z_count_ge(r - c_target), for r in [0, nsum+1]
        for r in range(lo, hi + 1):
            if r <= 0:
                sum_ge_r: bool | Literal = True
            elif r > nsum:
                sum_ge_r = False
            else:
                sum_ge_r = ge[r]

            # S - T == delta  =>  T == S - delta
            t = r - delta
            if t <= 0:
                z_ge_t: bool | Literal = True
            elif t > nz:
                z_ge_t = False
            else:
                z_ge_t = _EncoderDispatch._int_cmp_constraint(z, ">=", z.lb + t)

            _EncoderDispatch._lit_implies(clauses, model, sum_ge_r, z_ge_t)
            _EncoderDispatch._lit_implies(clauses, model, z_ge_t, sum_ge_r)

        clauses.extend(_EncoderDispatch._addition_domain_cuts(
            model, x, y, z, target, equality=True
        ))
        return ClauseGroup(model, clauses)


    @staticmethod
    def _normalize_bivariate_to_leq(a: int, b: int, c: int, op: str) -> tuple[list[tuple[int, int, int, str]], bool] | None:
        """Normalize ``a*x + b*y op c`` into one or more ``<=`` obligations.

        Returns a list of tuples ``(a, b, c, '<=')``. ``None`` means unsupported.
        """
        if op == "<=":
            return [(a, b, c, "<=")], False
        if op == "<":
            return [(a, b, c - 1, "<=")], False
        if op == ">=":
            return [(-a, -b, -c, "<=")], False
        if op == ">":
            return [(-a, -b, -c - 1, "<=")], False
        if op == "==":
            return [(a, b, c, "<="), (-a, -b, -c, "<=")], True
        return None

    @staticmethod
    def _solve_bivariate_branch_on_second(b: int, op: str, rhs_val: int) -> tuple[str, int] | bool:
        """Solve ``b*y OP rhs_val`` into a comparator on ``y``.

        Returns ``(op_y, k)`` for a constraint ``y op_y k`` or a boolean if the
        branch is trivially true/false.
        """
        if b == 0:
            return ((0 <= rhs_val) if op == "<=" else (0 < rhs_val) if op == "<" else (0 >= rhs_val) if op == ">=" else (0 > rhs_val) if op == ">" else (0 == rhs_val) if op == "==" else (_ for _ in ()).throw(ValueError(f"Unsupported comparator {op!r}")))
        if b < 0:
            return _EncoderDispatch._solve_bivariate_branch_on_second(-b, _EncoderDispatch._flip_op_for_negative_scale(op), -rhs_val)

        # b > 0
        if op == "<=":
            return ("<=", rhs_val // b)
        if op == "<":
            return ("<", _EncoderDispatch._ceil_div(rhs_val, b))
        if op == ">=":
            return (">=", _EncoderDispatch._ceil_div(rhs_val, b))
        if op == ">":
            return (">", rhs_val // b)
        if op in ("==", "!="):
            if rhs_val % b != 0:
                return op == "!="
            return op, rhs_val // b
        raise ValueError(f"Unsupported comparator {op!r}")

    @staticmethod
    def _emit_univariate_affine_gated(
        clauses: list[Clause],
        model: "Model",
        antecedent: bool | Literal,
        x: IntVar,
        a: int,
        op: str,
        c_target: int,
    ) -> bool:
        """Append CNF for ``antecedent -> (a*x op c_target)`` without helper vars."""
        branch = _EncoderDispatch._solve_bivariate_branch_on_second(a, op, c_target)
        if isinstance(branch, bool):
            _EncoderDispatch._lit_implies(clauses, model, antecedent, branch)
            return True

        x_op, k = branch
        if x_op == "!=":
            if x.lb <= k <= x.ub:
                body = [~atom for atom in x._exact_value_atoms(k)]
                _EncoderDispatch._append_guarded_clause2(clauses, model, antecedent, True, body)
        elif x_op == "==":
            for comparison in (">=", "<="):
                lit = _EncoderDispatch._int_cmp_constraint(x, comparison, k)
                _EncoderDispatch._lit_implies(clauses, model, antecedent, lit)
        else:
            lit = _EncoderDispatch._int_cmp_constraint(x, x_op, k)
            _EncoderDispatch._lit_implies(clauses, model, antecedent, lit)
        return True

    @staticmethod
    def _extract_univariate_with_bool_affine(model: "Model", expr: PBExpr) -> tuple[IntVar, int, Literal, int, int] | None:
        extracted = _EncoderDispatch._extract_affine_parts(model, expr, allow_booleans=True)
        if extracted is None:
            return None
        integers, booleans, offset = extracted
        if len(integers) != 1 or len(booleans) != 1:
            return None
        (x, coefficient), = integers
        (literal, weight), = booleans
        return x, coefficient, literal, weight, offset

    @staticmethod
    def _extract_bivariate_with_bool_affine(
        model: "Model", expr: PBExpr,
    ) -> tuple[IntVar, int, IntVar, int, Literal, int, int] | None:
        extracted = _EncoderDispatch._extract_affine_parts(model, expr, allow_booleans=True)
        if extracted is None:
            return None
        integers, booleans, offset = extracted
        if len(integers) != 2 or len(booleans) != 1:
            return None
        (x, a), (y, b) = sorted(integers, key=lambda item: id(item[0]))
        (literal, weight), = booleans
        return x, a, y, b, literal, weight, offset

    @staticmethod
    def _try_reify_cardinality(model, constraint, indicator):
        if constraint._op not in ("<=", "<", ">=", ">", "=="):
            return None
        if constraint._conditions or constraint._lhs.int_terms or constraint._rhs.int_terms:
            return None
        model._validate_integral_pbexpr(constraint._lhs)
        model._validate_integral_pbexpr(constraint._rhs)
        pairs, constant = _EncoderDispatch._normalize_pb(constraint._lhs, constraint._rhs)
        comparison, bound = _EncoderDispatch._bound_from_zero_compare(constraint._op, constant)
        if len(pairs) < 2 or any(weight != 1 for weight, _ in pairs):
            return None
        literals = [literal for _, literal in pairs]
        if any(literal.id in model._intvar_threshold_owner_by_litid for literal in literals):
            return None
        if comparison == ">=" or (comparison == "==" and bound != 1 and bound == len(literals) - 1):
            literals = [~literal for literal in literals]
            bound = len(literals) - bound
            comparison = "<=" if comparison == ">=" else "=="
        if comparison not in ("<=", "==") or bound != 1:
            return None
        thresholds = [1, 2] if comparison == "==" else [2]
        clauses, outputs = _EncoderDispatch._build_sequential_ge_counter(
            model, literals, thresholds=thresholds
        )
        at_most_one = _EncoderDispatch._negate_bool_or_lit(outputs[2])
        _EncoderDispatch._lit_implies(clauses, model, indicator, at_most_one)
        if comparison == "==":
            _EncoderDispatch._lit_implies(clauses, model, indicator, outputs[1])
            _EncoderDispatch._lit_conj_implies(clauses, model, outputs[1], at_most_one, indicator)
        else:
            _EncoderDispatch._lit_implies(clauses, model, at_most_one, indicator)
        return ClauseGroup(model, clauses)

    @staticmethod
    def _extract_unit_bool_sum_affine(model: "Model", expr: PBExpr) -> tuple[list[Literal], int] | None:
        """Return ``(lits, offset)`` for ``sum(lits) + offset`` with unit coefficients.

        Each term must have coefficient ``+1`` and represent a Boolean input;
        a two-value integer also has exactly one Boolean threshold.
        """
        if expr.int_terms:
            return None
        lits: list[Literal] = []
        for t in expr.terms:
            if int(t.coefficient) != 1:
                return None
            lit = t.literal
            info = model._intvar_threshold_owner_by_litid.get(lit.id)
            if info is not None and info[0].ub - info[0].lb > 1:
                return None
            lits.append(lit)
        return lits, int(expr.constant)

    @staticmethod
    def _extract_int_plus_unit_bool_sum_affine(
        model: "Model", expr: PBExpr
    ) -> tuple[IntVar, int, list[Literal], int] | None:
        """Return ``(x, a, bool_lits, c)`` for ``a*x + sum(bool_lits) + c``.

        Requirements:
            * exactly one IntVar represented by a full threshold set
            * uniform nonzero integer coefficient ``a`` on all thresholds
            * non-threshold boolean literals have unit coefficient ``+1``
            * no lifted int_terms
        """
        if expr.int_terms:
            return None
        per_owner: dict[int, tuple[IntVar, int, set[int]]] = {}
        bool_lits: list[Literal] = []
        for t in expr.terms:
            c = int(t.coefficient)
            if c == 0:
                continue
            lit = t.literal
            info = model._intvar_threshold_owner_by_litid.get(lit.id)
            if info is not None:
                # Int threshold terms must stay positive literal form.
                if not lit.polarity:
                    return None
                x, idx = info
                key = id(x)
                if key in per_owner:
                    x0, c0, seen = per_owner[key]
                    if x0 is not x or c0 != c:
                        return None
                    if idx in seen:
                        return None
                    seen.add(idx)
                else:
                    per_owner[key] = (x, c, {idx})
            else:
                if c != 1:
                    return None
                bool_lits.append(lit)

        if len(per_owner) != 1:
            return None
        x, a, seen = next(iter(per_owner.values()))
        if a == 0:
            return None
        if len(seen) != len(x._threshold_lits) or seen != set(range(len(x._threshold_lits))):
            return None
        # Convert compact threshold-sum form back to actual x-value offset:
        # sum(thresholds) == x - lb.
        c_actual = int(expr.constant) - a * x.lb
        return x, a, bool_lits, c_actual

    @staticmethod
    def _extract_single_weighted_bool_affine(model: "Model", expr: PBExpr) -> tuple[Literal, int, int] | None:
        """Return ``(lit, coeff, const)`` for ``coeff*lit + const``.

        The expression must have exactly one non-threshold boolean literal term
        with nonzero integer coefficient and no lifted Int terms.
        """
        if expr.int_terms:
            return None
        terms = [t for t in expr.terms if int(t.coefficient) != 0]
        if len(terms) != 1:
            return None
        t = terms[0]
        lit = t.literal
        if model._intvar_threshold_owner_by_litid.get(lit.id) is not None:
            return None
        return lit, int(t.coefficient), int(expr.constant)

    @staticmethod
    def _emit_sum_le_gated_conj(
        clauses: list[Clause],
        model: "Model",
        left: bool | Literal,
        right: bool | Literal,
        lits: Sequence[Literal],
        bound: int,
        ge_cache: _CountOutputs | None,
    ) -> _CountOutputs | None:
        """Append CNF for ``(left and right) -> (sum(lits) <= bound)``."""
        n = len(lits)
        if bound >= n:
            return ge_cache
        if bound < 0:
            _EncoderDispatch._lit_conj_implies(clauses, model, left, right, False)
            return ge_cache
        if bound == 0:
            for lit in lits:
                _EncoderDispatch._append_guarded_clause2(clauses, model, left, right, [~lit])
            return ge_cache
        if bound == n - 1:
            _EncoderDispatch._append_guarded_clause2(clauses, model, left, right, [~lit for lit in lits])
            return ge_cache
        if ge_cache is None:
            seq_clauses, ge_cache = _EncoderDispatch._build_sequential_ge_counter(model, lits)
            clauses.extend(seq_clauses)
        ge_lit = ge_cache[bound + 1]
        if isinstance(ge_lit, bool):
            _EncoderDispatch._lit_conj_implies(clauses, model, left, right, not ge_lit)
        else:
            _EncoderDispatch._lit_conj_implies(clauses, model, left, right, ~ge_lit)
        return ge_cache

    @staticmethod
    def _emit_sum_ge_gated_conj(
        clauses: list[Clause],
        model: "Model",
        left: bool | Literal,
        right: bool | Literal,
        lits: Sequence[Literal],
        threshold: int,
        ge_cache: _CountOutputs | None,
    ) -> _CountOutputs | None:
        """Append CNF for ``(left and right) -> (sum(lits) >= threshold)``."""
        n = len(lits)
        if threshold <= 0:
            return ge_cache
        if threshold > n:
            _EncoderDispatch._lit_conj_implies(clauses, model, left, right, False)
            return ge_cache
        if threshold == n:
            for lit in lits:
                _EncoderDispatch._append_guarded_clause2(clauses, model, left, right, [lit])
            return ge_cache
        if threshold == 1:
            _EncoderDispatch._append_guarded_clause2(clauses, model, left, right, list(lits))
            return ge_cache
        if ge_cache is None:
            seq_clauses, ge_cache = _EncoderDispatch._build_sequential_ge_counter(model, lits)
            clauses.extend(seq_clauses)
        ge_lit = ge_cache[threshold]
        _EncoderDispatch._lit_conj_implies(clauses, model, left, right, ge_lit)
        return ge_cache

    @staticmethod
    def _sum_le_bound_is_direct(n: int, bound: int) -> bool:
        return bound >= n or bound < 0 or bound == 0 or bound == n - 1

    @staticmethod
    def _sum_ge_threshold_is_direct(n: int, threshold: int) -> bool:
        return threshold <= 0 or threshold > n or threshold == n or threshold == 1

    @staticmethod
    def _try_boolsum_bigm_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Encode a Boolean count with one unrestricted and one gated bound."""
        if op not in ("<=", "<", ">=", ">"):
            return None

        def compile_oriented(left, comparison, right):
            if comparison not in ("<=", "<"):
                return None
            count = _EncoderDispatch._extract_unit_bool_sum_affine(model, left)
            affine = _EncoderDispatch._extract_single_weighted_bool_affine(model, right)
            if count is None or affine is None:
                return None
            literals, offset = count
            if not literals:
                return None
            flag, coefficient, constant = affine
            if comparison == "<":
                constant -= 1
            false_bound = constant - offset
            true_bound = false_bound + coefficient
            lower, upper = min(false_bound, true_bound), max(false_bound, true_bound)
            if upper < len(literals):
                return None
            if lower >= len(literals):
                return ClauseGroup(model, [])
            gate = ~flag if false_bound < true_bound else flag
            if lower < 0:
                return ClauseGroup(model, [Clause(model, [~gate])])
            if lower == 0:
                return ClauseGroup(model, [Clause(model, [~literal, ~gate]) for literal in literals])
            return _EncoderDispatch._compile_structured_auto_leq(
                model, [model._lit_to_dimacs(literal) for literal in literals],
                [1] * len(literals), lower,
            ).only_if(gate)

        result = compile_oriented(lhs, op, rhs)
        if result is not None:
            return result
        swapped = {"<=": ">=", "<": ">", ">=": "<=", ">": "<"}
        return compile_oriented(rhs, swapped[op], lhs)

    @staticmethod
    def _affine_leq_cuts(width_x, step_x, width_y, step_y, bound):
        """Yield essential ``x >= k -> y <= limit`` cuts for nonnegative counts."""
        k = max(0, (bound - step_y * width_y) // step_x + 1)
        while k <= width_x:
            limit = (bound - step_x * k) // step_y
            yield k, limit
            if limit < 0:
                break
            # Skip counts whose rounded consequent is unchanged.
            k = (bound - step_y * limit) // step_x + 1

    @staticmethod
    def _int_boolsum_cuts(x, coefficient, bound, comparison, count):
        if comparison == ">=":
            # Complement the Boolean count to normalize to <=.
            coefficient, bound = -coefficient, count - bound
        bound -= coefficient * (x.lb if coefficient > 0 else x.ub)
        for k, limit in _EncoderDispatch._affine_leq_cuts(
            x.ub - x.lb, abs(coefficient), count, 1, bound
        ):
            condition = _EncoderDispatch._int_cmp_constraint(
                x, ">=" if coefficient > 0 else "<=",
                x.lb + k if coefficient > 0 else x.ub - k,
            )
            yield condition, limit if comparison == "<=" else count - limit

    @staticmethod
    def _emit_int_boolsum_le_gated(
        clauses: list[Clause],
        model: "Model",
        antecedent: bool | Literal,
        x: IntVar,
        a: int,
        bool_lits: Sequence[Literal],
        bound: int,
        ge_cache: _CountOutputs | None,
    ) -> _CountOutputs | None:
        """Append CNF for ``antecedent -> (a*x + sum(bool_lits) <= bound)``."""
        for cond, rhs_bound in _EncoderDispatch._int_boolsum_cuts(x, a, bound, "<=", len(bool_lits)):
            ge_cache = _EncoderDispatch._emit_sum_le_gated_conj(
                clauses, model, antecedent, cond, bool_lits, rhs_bound, ge_cache
            )
        return ge_cache

    @staticmethod
    def _emit_int_boolsum_ge_gated(
        clauses: list[Clause],
        model: "Model",
        antecedent: bool | Literal,
        x: IntVar,
        a: int,
        bool_lits: Sequence[Literal],
        bound: int,
        ge_cache: _CountOutputs | None,
    ) -> _CountOutputs | None:
        """Append CNF for ``antecedent -> (a*x + sum(bool_lits) >= bound)``."""
        for cond, rhs_threshold in _EncoderDispatch._int_boolsum_cuts(x, a, bound, ">=", len(bool_lits)):
            ge_cache = _EncoderDispatch._emit_sum_ge_gated_conj(
                clauses, model, antecedent, cond, bool_lits, rhs_threshold, ge_cache
            )
        return ge_cache

    @staticmethod
    def _try_mixed_int_boolsum_bigm_fastpath(
        model: "Model", lhs: PBExpr, op: str, rhs: PBExpr
    ) -> ClauseGroup | None:
        """Detect and compile ``a*x + sum(unit-bools) OP k + m*lit``.

        Supports the ``<=, <, >=, >`` families by enumerating ladder cuts of
        the IntVar side and pushing gated bounds on the unit-bool sum.
        """
        if op not in ("<=", "<", ">=", ">"):
            return None

        def compile_oriented(main_expr: PBExpr, cmp_op: str, affine_expr: PBExpr) -> ClauseGroup | None:
            left = _EncoderDispatch._extract_int_plus_unit_bool_sum_affine(model, main_expr)
            right = _EncoderDispatch._extract_single_weighted_bool_affine(model, affine_expr)
            if left is None or right is None:
                return None
            x, a, bool_lits, c_left = left
            lit, mcoef, c_right = right

            if cmp_op == "<":
                cmp_op = "<="
                c_right -= 1
            elif cmp_op == ">":
                cmp_op = ">="
                c_right += 1

            # a*x + sum + c_left OP c_right + mcoef*lit
            # -> a*x + sum OP (c_right - c_left) + mcoef*lit
            base = c_right - c_left
            # ``~lit`` selects the zero contribution and ``lit`` selects
            # the full ``mcoef`` contribution, regardless of lit polarity.
            b_false = base
            b_true = base + mcoef

            minimum = min(a * x.lb, a * x.ub)
            maximum = max(a * x.lb, a * x.ub) + len(bool_lits)
            if cmp_op == "<=":
                false_free, true_free = b_false >= maximum, b_true >= maximum
            else:
                false_free, true_free = b_false <= minimum, b_true <= minimum
            if false_free and true_free:
                return ClauseGroup(model, [])
            if false_free or true_free:
                gate = lit if false_free else ~lit
                bound = b_true if false_free else b_false
                return _EncoderDispatch.compile(
                    model, main_expr, cmp_op, PBExpr.from_item(bound + c_left)
                ).only_if(gate)

            thresholds = set()
            direct = (_EncoderDispatch._sum_le_bound_is_direct if cmp_op == "<=" else
                      _EncoderDispatch._sum_ge_threshold_is_direct)
            for bound in (b_false, b_true):
                for _, cut in _EncoderDispatch._int_boolsum_cuts(x, a, bound, cmp_op, len(bool_lits)):
                    if not direct(len(bool_lits), cut):
                        thresholds.add(cut + 1 if cmp_op == "<=" else cut)
            clauses, ge_cache = _EncoderDispatch._build_sequential_ge_counter(
                model, bool_lits, thresholds=thresholds
            )
            if cmp_op == "<=":
                ge_cache = _EncoderDispatch._emit_int_boolsum_le_gated(
                    clauses, model, ~lit, x, a, bool_lits, b_false, ge_cache
                )
                ge_cache = _EncoderDispatch._emit_int_boolsum_le_gated(
                    clauses, model, lit, x, a, bool_lits, b_true, ge_cache
                )
                return ClauseGroup(model, clauses)
            if cmp_op == ">=":
                ge_cache = _EncoderDispatch._emit_int_boolsum_ge_gated(
                    clauses, model, ~lit, x, a, bool_lits, b_false, ge_cache
                )
                ge_cache = _EncoderDispatch._emit_int_boolsum_ge_gated(
                    clauses, model, lit, x, a, bool_lits, b_true, ge_cache
                )
                return ClauseGroup(model, clauses)
            return None

        out = compile_oriented(lhs, op, rhs)
        if out is not None:
            return out

        # Swapped orientation:
        #   main <= affine  handled above
        #   main >= affine  <=> affine <= main
        swapped = {"<=": ">=", "<": ">", ">=": "<=", ">": "<"}
        out = compile_oriented(rhs, swapped[op], lhs)
        if out is not None:
            return out
        return None

    @staticmethod
    def _try_nonnegative_zero_leq_fastpath(
        model: "Model", lhs: PBExpr, op: str, rhs: PBExpr
    ) -> ClauseGroup | None:
        """Force positive-weight literals false, retaining only strongest order cuts."""
        if op not in ("<=", "<"):
            return None
        pairs, const = _EncoderDispatch._normalize_pb(lhs, rhs)
        cmp_op, bound = _EncoderDispatch._bound_from_zero_compare(op, const)
        if cmp_op != "<=" or int(bound) != 0:
            return None
        if not pairs:
            return None
        booleans: dict[int, Literal] = {}
        cuts: dict[tuple[int, bool], tuple[int, Literal]] = {}
        for _w, lit in pairs:
            info = model._intvar_threshold_owner_by_litid.get(lit.id)
            if info is None:
                booleans[model._lit_to_dimacs(lit)] = lit
                continue
            owner, index = info
            key = (id(owner), lit.polarity)
            previous = cuts.get(key)
            if previous is None or (index < previous[0] if lit.polarity else index > previous[0]):
                cuts[key] = (index, lit)
        # Domain clauses propagate each retained cut through its threshold chain.
        forced = list(booleans.values())
        forced.extend(lit for _index, lit in cuts.values())
        return ClauseGroup(model, [Clause(model, [~lit]) for lit in forced])

    @staticmethod
    def _build_sequential_ge_counter(
        model: "Model", lits: Sequence[Literal], *, thresholds=None,
    ) -> tuple[list[Clause], _CountOutputs]:
        requested = range(1, len(lits) + 1) if thresholds is None else thresholds
        clauses, outputs = count_thresholds(
            model, lits, requested, _EncoderDispatch._lit_and, _EncoderDispatch._lit_or,
        )
        if thresholds is None:
            return clauses, [True, *outputs.values()]
        return clauses, outputs

    @staticmethod
    def _try_weighted_sum_eq_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Encode IntVar == weighted Boolean sum with our smaller construction."""
        if op != "==":
            return None

        for integer, expression in ((lhs, rhs), (rhs, lhs)):
            affine = _EncoderDispatch._extract_multi_int_affine(model, integer)
            if affine is None or len(affine[0]) != 1:
                continue
            (total, coefficient), = affine[0]
            if coefficient != 1 or total.lb != 0 or affine[1] or expression.constant:
                continue
            if len(expression.terms) < 2 or any(
                term.coefficient <= 0
                or term.literal.id in model._intvar_threshold_owner_by_litid
                for term in expression.terms
            ):
                continue
            lits = [model._lit_to_dimacs(term.literal) for term in expression.terms]
            weights = [int(term.coefficient) for term in expression.terms]
            if all(weight == 1 for weight in weights):
                continue  # The existing unit-sum fastpath owns this case.

            pairs, constant = _EncoderDispatch._normalize_pb(lhs, rhs)
            cache_key = _canonical_pb_cache_key(
                "==", -constant, [model._lit_to_dimacs(lit) for _, lit in pairs],
                [weight for weight, _ in pairs],
            )
            cached = model._pb_clause_cache.get(cache_key)
            if cached is not None:
                return cached

            available, used, groups = set(lits), set(), []
            for group in sorted(model._known_eo_groups.values(), key=lambda g: (-len(g), g)):
                if set(group) <= available and not used.intersection(map(abs, group)):
                    groups.append(group)
                    used.update(map(abs, group))
            plans = _weighted_sum.plan_candidates(lits, weights, total.ub, groups)
            plans, possible = _weighted_sum.bounded_candidates(plans)
            if not plans:
                continue

            # Candidates share these cached predicates and the same private
            # ID range. Losing clauses and auxiliary IDs never enter the model.
            values = {value: model._lit_to_dimacs(total == value) for value in possible}
            thresholds = [model._lit_to_dimacs(lit) for lit in total._threshold_lits]
            cnf = _weighted_sum.encode_best(plans, thresholds, model._top_id(), values)
            model._debug(
                model.DEBUG_COMPILE,
                f"encode path=fast_weighted_sum_eq clauses={len(cnf.clauses)}",
            )
            result = model._cnfplus_to_clausegroup(cnf)
            model._pb_clause_cache[cache_key] = result
            return result
        return None

    @staticmethod
    def _try_int_equals_unit_bool_sum_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile ``IntVar + c1 OP sum(unit-bools) + c2``.

        Supports ``OP in {==, <=, >=, <, >}`` using directional channeling:
            * ``==``: both directions
            * ``<=``: ``x>=k -> sum>=r``
            * ``>=``: ``sum>=r -> x>=k``
        Strict forms are normalized to non-strict by shifting the integer side:
            * ``x < sum``  ->  ``x + 1 <= sum``
            * ``x > sum``  ->  ``x >= sum + 1``

        Uses a reusable bool-count threshold ladder for ``sum>=r`` states and
        channels these with ladder thresholds. Avoids PB/Card encoders for this
        pattern.
        """
        if op not in ("==", "<=", ">=", "<", ">"):
            return None

        def try_orient(
            int_items: list[tuple[IntVar, int]],
            int_off: int,
            bool_expr: PBExpr,
            cmp_op: str,
        ) -> ClauseGroup | None:
            if len(int_items) != 1:
                return None
            x, a = int_items[0]
            if a != 1:
                return None
            ext = _EncoderDispatch._extract_unit_bool_sum_affine(model, bool_expr)
            if ext is None:
                return None
            bool_lits, bool_off = ext

            # x + int_off == sum(bool_lits) + bool_off
            shift = bool_off - int_off
            eff_op = cmp_op
            if eff_op == "<":
                # x < sum  <=>  x+1 <= sum
                eff_op = "<="
                shift -= 1
            elif eff_op == ">":
                # x > sum  <=>  x >= sum+1
                eff_op = ">="
                shift += 1
            n = len(bool_lits)
            # Outside the count's range, the nearest boundary cut propagates
            # through the integer ladder; the remaining cuts are redundant.
            lo = max(x.lb, min(x.ub + 1, shift))
            hi = min(x.ub + 1, max(x.lb, shift + n + 1))
            thresholds = range(max(1, lo - shift), min(n, hi - shift) + 1)
            clauses, ge = _EncoderDispatch._build_sequential_ge_counter(
                model, bool_lits, thresholds=thresholds
            )
            for k in range(lo, hi + 1):
                x_ge_k = _EncoderDispatch._int_cmp_constraint(x, ">=", k)
                r = k - shift
                if r <= 0:
                    sum_ge_r: bool | Literal = True
                elif r > n:
                    sum_ge_r = False
                else:
                    sum_ge_r = ge[r]
                if eff_op in ("==", "<="):
                    _EncoderDispatch._lit_implies(clauses, model, x_ge_k, sum_ge_r)
                if eff_op in ("==", ">="):
                    _EncoderDispatch._lit_implies(clauses, model, sum_ge_r, x_ge_k)

            return ClauseGroup(model, clauses)

        left = _EncoderDispatch._extract_multi_int_affine(model, lhs)
        if left is not None:
            litems, loff = left
            out = try_orient(litems, loff, rhs, op)
            if out is not None:
                return out

        right = _EncoderDispatch._extract_multi_int_affine(model, rhs)
        if right is not None:
            ritems, roff = right
            # sum OP int  <=>  int flip(OP) sum.
            swapped = {"<=": ">=", "<": ">", ">=": "<=", ">": "<", "==": "=="}
            out = try_orient(ritems, roff, lhs, swapped[op])
            if out is not None:
                return out

        return None


    @staticmethod
    def _try_bivariate_int_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile ``a*x + b*y OP c`` using ladder cliff implications.

        This path introduces zero auxiliary variables and supports exactly two
        ``IntVar`` operands in the affine difference ``lhs - rhs`` (no extra
        boolean literals). Supported comparators: ``<=, <, >=, >, ==``.
        """
        left = _EncoderDispatch._extract_multi_int_affine(model, lhs)
        right = _EncoderDispatch._extract_multi_int_affine(model, rhs)
        if left is None or right is None:
            return None
        litems, loff = left
        ritems, roff = right

        coeffs_by_id: dict[int, tuple[IntVar, int]] = {}
        for x, c in litems:
            key = id(x)
            x0, c0 = coeffs_by_id.get(key, (x, 0))
            if x0 is not x:
                return None
            coeffs_by_id[key] = (x, c0 + c)
        for y, c in ritems:
            key = id(y)
            y0, c0 = coeffs_by_id.get(key, (y, 0))
            if y0 is not y:
                return None
            coeffs_by_id[key] = (y, c0 - c)
        coeff_items = [(v, c) for v, c in coeffs_by_id.values() if c != 0]
        if len(coeff_items) != 2:
            return None

        # lhs OP rhs  =>  a*x + b*y OP c
        (x, a), (y, b) = coeff_items[0], coeff_items[1]
        c_target = -(loff - roff)

        return _EncoderDispatch._compile_bivariate_int(model, x, a, y, b, c_target, op)

    @staticmethod
    def _compile_bivariate_int(
        model: "Model", x: IntVar, a: int, y: IntVar, b: int, c_target: int, op: str,
    ) -> ClauseGroup | None:
        """Compile an already recognized ``a*x + b*y OP c_target`` relation."""
        normalized = _EncoderDispatch._normalize_bivariate_to_leq(a, b, c_target, op)
        if normalized is None:
            return None
        obligations, _is_eq = normalized

        clauses: list[Clause] = []
        for a1, b1, c1, _ in obligations:
            xx, aa, yy, bb = x, a1, y, b1
            if (xx.ub - xx.lb) > (yy.ub - yy.lb):
                xx, aa, yy, bb = yy, bb, xx, aa

            # Use nonnegative ladder counts, reversing negative-coefficient inputs.
            bound = c1 - aa * (xx.lb if aa > 0 else xx.ub) - bb * (yy.lb if bb > 0 else yy.ub)
            step_x, step_y = abs(aa), abs(bb)
            width_x, width_y = xx.ub - xx.lb, yy.ub - yy.lb
            for k, limit in _EncoderDispatch._affine_leq_cuts(
                width_x, step_x, width_y, step_y, bound
            ):
                antecedent = _EncoderDispatch._int_cmp_constraint(
                    xx, ">=" if aa > 0 else "<=", xx.lb + k if aa > 0 else xx.ub - k
                )
                consequent = False if limit < 0 else _EncoderDispatch._int_cmp_constraint(
                    yy, "<=" if bb > 0 else ">=", yy.lb + limit if bb > 0 else yy.ub - limit
                )
                _EncoderDispatch._lit_implies(clauses, model, antecedent, consequent)
        return ClauseGroup(model, clauses)

    @staticmethod
    def _try_trivariate_int_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Compile normalized ``x + y <= z`` using direct or merged order thresholds."""
        if op not in ("<=", "<", ">=", ">"):
            return None
        addition = _EncoderDispatch._extract_addition(model, lhs, op, rhs)
        if addition is None:
            return None
        x, y, z, c_target = addition
        coeff_items = [(x, 1), (y, 1), (z, -1)]
        nx = len(x._threshold_lits)
        ny = len(y._threshold_lits)
        delta = c_target - x.lb - y.lb + z.lb
        route = addition_encoding(nx, ny, z.ub - z.lb, delta)
        if route == 'general':
            return compile_sum(model, coeff_items, -delta, "<=")
        if route == 'direct':
            return _EncoderDispatch._compile_trivariate_int_pairwise_leq(model, x, y, z, c_target)
        return _EncoderDispatch._compile_trivariate_int_merged_leq(model, x, y, z, c_target)

    @staticmethod
    def _compile_trivariate_int_pairwise_leq(
        model: "Model",
        x: IntVar,
        y: IntVar,
        z: IntVar,
        c_target: int,
    ) -> ClauseGroup:
        """Compile ``x + y - z <= c_target`` by pairwise threshold implications."""
        if x.ub - x.lb > y.ub - y.lb:
            x, y = y, x
        nx = x.ub - x.lb
        ny = y.ub - y.lb
        nz = z.ub - z.lb
        # Count upward in x/y and downward from z.ub.
        bound = c_target - x.lb - y.lb + z.ub
        clauses: list[Clause] = []
        for i, remaining in _EncoderDispatch._affine_leq_cuts(nx, 1, ny + nz, 1, bound):
            xi = _EncoderDispatch._int_cmp_constraint(x, ">=", x.lb + i)
            for j, limit in _EncoderDispatch._affine_leq_cuts(ny, 1, nz, 1, remaining):
                yj = _EncoderDispatch._int_cmp_constraint(y, ">=", y.lb + j)
                zk = False if limit < 0 else _EncoderDispatch._int_cmp_constraint(
                    z, ">=", z.ub - limit
                )
                _EncoderDispatch._lit_conj_implies(clauses, model, xi, yj, zk)
        return ClauseGroup(model, clauses)

    @staticmethod
    def _compile_trivariate_int_merged_leq(
        model: "Model",
        x: IntVar,
        y: IntVar,
        z: IntVar,
        c_target: int,
    ) -> ClauseGroup:
        """Compile ``x + y - z <= c_target`` via unary merged sum thresholds."""
        nsum = len(x._threshold_lits) + len(y._threshold_lits)
        delta_count = c_target - x.lb - y.lb + z.lb
        lo = max(0, min(nsum, delta_count + 1))
        hi = min(nsum, max(0, delta_count + len(z._threshold_lits) + 1))
        clauses, sum_ge = _EncoderDispatch._build_unary_sum_ge_ladder(
            model, x._threshold_lits, y._threshold_lits,
            thresholds=range(max(1, lo), hi + 1),
        )
        for r in range(lo, hi + 1):
            sum_ge_r = True if r == 0 else sum_ge[r]
            z_count_ge = r - delta_count
            if z_count_ge <= 0:
                zk: bool | Literal = True
            elif z_count_ge > len(z._threshold_lits):
                zk = False
            else:
                zk = _EncoderDispatch._int_cmp_constraint(z, ">=", z.lb + z_count_ge)
            _EncoderDispatch._lit_implies(clauses, model, sum_ge_r, zk)

        clauses.extend(_EncoderDispatch._addition_domain_cuts(model, x, y, z, c_target))
        return ClauseGroup(model, clauses)

    @staticmethod
    def _try_univariate_int_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile ``a*x OP c`` using a single ladder comparator literal.

        Introduces zero auxiliary variables. Unsupported comparators/shapes return ``None``.
        """
        left = _EncoderDispatch._extract_multi_int_affine(model, lhs)
        right = _EncoderDispatch._extract_multi_int_affine(model, rhs)
        if left is None or right is None:
            return None
        litems, loff = left
        ritems, roff = right

        coeffs_by_id: dict[int, tuple[IntVar, int]] = {}
        for x, c in litems:
            key = id(x)
            x0, c0 = coeffs_by_id.get(key, (x, 0))
            if x0 is not x:
                return None
            coeffs_by_id[key] = (x, c0 + c)
        for y, c in ritems:
            key = id(y)
            y0, c0 = coeffs_by_id.get(key, (y, 0))
            if y0 is not y:
                return None
            coeffs_by_id[key] = (y, c0 - c)

        coeff_items = [(v, c) for v, c in coeffs_by_id.values() if c != 0]
        if len(coeff_items) != 1:
            return None

        (x, a) = coeff_items[0]
        c_target = -(loff - roff)
        clauses: list[Clause] = []
        _EncoderDispatch._emit_univariate_affine_gated(clauses, model, True, x, a, op, c_target)
        return ClauseGroup(model, clauses)

    @staticmethod
    def _try_univariate_with_bool_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile ``a*x + w*b_lit OP c`` with gated univariate branches."""
        diff = lhs - rhs
        ext = _EncoderDispatch._extract_univariate_with_bool_affine(model, diff)
        if ext is None:
            return None
        x, a, b_lit, w, offset = ext
        c_target = -offset  # a*x + w*b_lit OP c_target

        clauses: list[Clause] = []
        # Branch 1: b_lit is false => contribution 0
        _EncoderDispatch._emit_univariate_affine_gated(clauses, model, ~b_lit, x, a, op, c_target)
        # Branch 2: b_lit is true => contribution w
        _EncoderDispatch._emit_univariate_affine_gated(clauses, model, b_lit, x, a, op, c_target - w)
        return ClauseGroup(model, clauses)

    @staticmethod
    def _try_bivariate_with_bool_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile ``a*x + b*y + w*bit OP c`` via gated bivariate branches."""
        diff = lhs - rhs
        ext = _EncoderDispatch._extract_bivariate_with_bool_affine(model, diff)
        if ext is None:
            return None
        x, a, y, b, bit, w, offset = ext
        c_target = -offset

        g_false = _EncoderDispatch._compile_bivariate_int(model, x, a, y, b, c_target, op)
        if g_false is None:
            return None
        g_true = _EncoderDispatch._compile_bivariate_int(model, x, a, y, b, c_target - w, op)
        if g_true is None:
            return None

        false_rows = list(g_false.iter_dimacs())
        true_rows = list(g_true.iter_dimacs())
        common = set(false_rows).intersection(true_rows)
        gate = model._lit_to_dimacs(bit)

        def rows():
            # Shared clauses hold for either flag value and need no guard.
            for row in false_rows:
                yield row if row in common else (*row, gate)
            for row in true_rows:
                if row not in common:
                    yield (*row, -gate)

        return ClauseGroup._from_dimacs_trusted(model, rows())

    @staticmethod
    def compile(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup:
        """Compile a PB comparison with fast paths and PB/Card fallback."""
        lhs = lhs._realize_int_terms(model)
        rhs = rhs._realize_int_terms(model)
        unary_adder_eq_fast = _EncoderDispatch._try_unary_adder_eq_fastpath(model, lhs, op, rhs)
        if unary_adder_eq_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_unary_adder_eq op={op} clauses={len(unary_adder_eq_fast)}")
            return unary_adder_eq_fast
        weighted_sum_fast = _EncoderDispatch._try_weighted_sum_eq_fastpath(model, lhs, op, rhs)
        if weighted_sum_fast is not None:
            return weighted_sum_fast
        boolsum_fast = _EncoderDispatch._try_int_equals_unit_bool_sum_fastpath(model, lhs, op, rhs)
        if boolsum_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_boolsum op={op} clauses={len(boolsum_fast)}")
            return boolsum_fast
        boolsum_bigm_fast = _EncoderDispatch._try_boolsum_bigm_fastpath(model, lhs, op, rhs)
        if boolsum_bigm_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_boolsum_bigm op={op} clauses={len(boolsum_bigm_fast)}")
            return boolsum_bigm_fast
        mixed_bigm_fast = _EncoderDispatch._try_mixed_int_boolsum_bigm_fastpath(model, lhs, op, rhs)
        if mixed_bigm_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_mixed_bigm op={op} clauses={len(mixed_bigm_fast)}")
            return mixed_bigm_fast
        uni_fast = _EncoderDispatch._try_univariate_int_fastpath(model, lhs, op, rhs)
        if uni_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_univariate op={op} clauses={len(uni_fast)}")
            return uni_fast
        uni_bool_fast = _EncoderDispatch._try_univariate_with_bool_fastpath(model, lhs, op, rhs)
        if uni_bool_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_univariate_bool op={op} clauses={len(uni_bool_fast)}")
            return uni_bool_fast
        nonnegative_zero_fast = _EncoderDispatch._try_nonnegative_zero_leq_fastpath(model, lhs, op, rhs)
        if nonnegative_zero_fast is not None:
            model._debug(
                model.DEBUG_COMPILE,
                f"encode path=fast_nonnegative_zero op={op} clauses={len(nonnegative_zero_fast)}",
            )
            return nonnegative_zero_fast
        bivar_bool_fast = _EncoderDispatch._try_bivariate_with_bool_fastpath(model, lhs, op, rhs)
        if bivar_bool_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_bivariate_bool op={op} clauses={len(bivar_bool_fast)}")
            return bivar_bool_fast
        tri_fast = _EncoderDispatch._try_trivariate_int_fastpath(model, lhs, op, rhs)
        if tri_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_trivariate op={op} clauses={len(tri_fast)}")
            return tri_fast
        bivar_fast = _EncoderDispatch._try_bivariate_int_fastpath(model, lhs, op, rhs)
        if bivar_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_bivariate op={op} clauses={len(bivar_fast)}")
            return bivar_fast

        # Existing small-arity and mixed Boolean fast paths keep precedence.
        difference = lhs - rhs
        affine = _EncoderDispatch._extract_integer_sum_with_bools(model, difference)
        if affine is not None:
            items = affine.items
            if len(items) >= 2 and any(x.ub - x.lb > 1 for x, _ in items):
                constant = affine.constant
                cmp_op, sum_bound = _EncoderDispatch._bound_from_zero_compare(
                    op, constant
                )
                scale = abs(items[0][1])
                if not affine.overlapping and all(abs(c) == scale for _, c in items):
                    if cmp_op == "==":
                        if sum_bound % scale:
                            return ClauseGroup._from_dimacs_trusted(model, [[]])
                        sum_bound //= scale
                    elif cmp_op == "<=":
                        sum_bound //= scale
                    else:
                        sum_bound = -((-sum_bound) // scale)
                    normalized = [(x, c // scale) for x, c in items]
                    return compile_sum(model, normalized, -sum_bound, cmp_op)
                return compile_weighted_sum(model, items, sum_bound, cmp_op)

        pairs, const = _EncoderDispatch._normalize_pb(lhs, rhs)
        cmp_op, bound = _EncoderDispatch._bound_from_zero_compare(op, const)

        # Trivial constant-only case.
        if not pairs:
            satisfied = False
            if cmp_op == "<=":
                satisfied = 0 <= bound
            elif cmp_op == ">=":
                satisfied = 0 >= bound
            elif cmp_op == "==":
                satisfied = 0 == bound
            lit = model._get_bool_constant_literal(bool(satisfied))
            return ClauseGroup(model, [Clause(model, [lit])])

        lits = [model._lit_to_dimacs(l) for _, l in pairs]
        weights = [w for w, _ in pairs]
        # Universal coefficient GCD normalization (MINISAT+-style):
        # reduces many weighted constraints to cardinalities and can expose
        # contradictions early for equality constraints.
        if weights:
            g = reduce(math.gcd, weights)
        else:
            g = 1
        if g > 1:
            weights = [w // g for w in weights]
            if cmp_op == "<=":
                bound = bound // g
            elif cmp_op == ">=":
                bound = -((-bound) // g)  # ceil(bound / g)
            elif cmp_op == "==":
                if bound % g != 0:
                    return ClauseGroup(model, [Clause(model, [model._get_bool_constant_literal(False)])])
                bound = bound // g
        total_weight = sum(weights)

        # Trivial bound short-circuits (avoid invalid bounds in CardEnc/PBEnc).
        if cmp_op == "<=":
            if bound < 0:
                return ClauseGroup(model, [Clause(model, [model._get_bool_constant_literal(False)])])
            if bound >= total_weight:
                return ClauseGroup(model, [Clause(model, [model._get_bool_constant_literal(True)])])
        elif cmp_op == ">=":
            if bound <= 0:
                return ClauseGroup(model, [Clause(model, [model._get_bool_constant_literal(True)])])
            if bound > total_weight:
                return ClauseGroup(model, [Clause(model, [model._get_bool_constant_literal(False)])])
        elif cmp_op == "==":
            if bound < 0 or bound > total_weight:
                return ClauseGroup(model, [Clause(model, [model._get_bool_constant_literal(False)])])

        # Cardinality fast path: all coefficients are unit.
        if all(w == 1 for w in weights):
            model._debug(model.DEBUG_COMPILE, f"encode path=structured_card_auto op={cmp_op} bound={bound} n={len(lits)}")
        else:
            model._debug(
                model.DEBUG_COMPILE,
                f"encode path=structured_pb_auto op={cmp_op} bound={bound} n={len(lits)} weights_sum={sum(weights)}",
            )

        if cmp_op == "<=":
            return _EncoderDispatch._compile_structured_auto_leq(model, lits, weights, bound)
        elif cmp_op == ">=":
            return _EncoderDispatch._compile_structured_auto_leq(
                model,
                [-int(l) for l in lits],
                weights,
                int(total_weight - bound),
            )
        elif cmp_op == "==":
            return _EncoderDispatch._compile_structured_auto_eq(model, lits, weights, bound)
        else:
            raise ValueError(f"Unsupported PB op {cmp_op!r}")
