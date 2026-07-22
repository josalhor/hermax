from __future__ import annotations
import math
import sys
import time
from dataclasses import dataclass
from functools import reduce
from typing import Iterable, Mapping, Optional, Sequence
from hermax.encoder.pbamo import PBAMOEnc
from hermax.utils import batcher_odd_even_unary_add_network

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
        # Build lhs - rhs and normalize all coefficients to be positive by
        # flipping literals and shifting the constant.
        diff = lhs - rhs
        pairs: list[tuple[int, Literal]] = []
        const = diff.constant
        for t in diff.terms:
            c = int(t.coefficient)
            lit = t.literal
            if c == 0:
                continue
            if c < 0:
                pairs.append((-c, ~lit))
                const += c  # c is negative:  -w*x == w*~x - w
            else:
                pairs.append((c, lit))
        return pairs, const

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
    def _extract_multi_int_affine(model: "Model", expr: PBExpr) -> tuple[list[tuple[IntVar, int]], int] | None:
        """Return ``({intvar: coeff, ...}, offset)`` for a pure affine Int expression.

        The expression must consist solely of full lifted threshold sets for one or
        more IntVars, each with a uniform nonzero coefficient (which may be
        negative), plus an integer constant. No raw boolean literals are allowed.
        """
        if not expr.terms:
            return [], int(expr.constant)
        per_owner: dict[int, tuple[IntVar, int, set[int]]] = {}
        for t in expr.terms:
            c = int(t.coefficient)
            if c == 0:
                continue
            lit = t.literal
            if not lit.polarity:
                return None
            info = model._intvar_threshold_owner_by_litid.get(lit.id)
            if info is None:
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

        coeffs: list[tuple[IntVar, int]] = []
        offset = int(expr.constant)
        for x, c, seen in per_owner.values():
            if len(seen) != len(x._threshold_lits):
                return None
            if seen != set(range(len(x._threshold_lits))):
                return None
            coeffs.append((x, c))
            offset -= c * x.lb
        return coeffs, offset

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

    @staticmethod
    def _lit_implies(clauses: list[Clause], model: "Model", antecedent: bool | Literal, consequent: bool | Literal) -> None:
        """Append CNF for ``antecedent -> consequent`` with constant folding."""
        if isinstance(antecedent, bool):
            if not antecedent:
                return
            if isinstance(consequent, bool):
                if consequent:
                    return
                clauses.append(Clause(model, []))
                return
            clauses.append(Clause(model, [consequent]))
            return
        # antecedent is a Literal
        if isinstance(consequent, bool):
            if consequent:
                return
            clauses.append(Clause(model, [~antecedent]))
            return
        clauses.append(Clause(model, [~antecedent, consequent]))

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
        network=None,
    ) -> tuple[list[Clause], list[bool | Literal]]:
        """Build ``sum >= r`` literals for two descending unary ladders.

        ``left_desc`` and ``right_desc`` are IntVar threshold ladders in the
        native descending order ``[x>=lb+1, x>=lb+2, ...]``. The returned
        ``ge[r]`` literals encode the count sum over both ladders for
        ``r in [0, len(left_desc)+len(right_desc)]`` with ``ge[0] == True``.
        """
        nx = len(left_desc)
        ny = len(right_desc)
        total = nx + ny
        if total == 0:
            return [], [True]

        net = batcher_odd_even_unary_add_network(nx, ny) if network is None else network
        width = int(net.n)
        clauses: list[Clause] = []

        if nx == 0:
            wires: list[bool | Literal] = list(reversed(right_desc))
        elif ny == 0:
            wires = list(reversed(left_desc))
        else:
            p2 = width // 2
            if 2 * p2 != width:
                raise AssertionError("Unary-add merge network width must be even for two non-empty inputs.")
            wires = [
                *([False] * (p2 - nx)),
                *reversed(left_desc),
                *([False] * (p2 - ny)),
                *reversed(right_desc),
            ]
            if len(wires) != width:
                raise AssertionError("Unary-add merge network width mismatch.")

        for i, j in net:
            a = wires[i]
            b = wires[j]
            lo = _EncoderDispatch._lit_and(clauses, model, a, b)
            hi = _EncoderDispatch._lit_or(clauses, model, a, b)
            wires[i] = lo
            wires[j] = hi

        ge: list[bool | Literal] = [True]
        for r in range(1, total + 1):
            ge.append(wires[width - r])
        return clauses, ge

    @staticmethod
    def _try_unary_adder_eq_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile ``x + y == z`` (affine-shifted) via unary merge network."""
        if op != "==":
            return None
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
        if len(coeff_items) != 3:
            return None

        plus_vars: list[IntVar] = []
        minus_vars: list[IntVar] = []
        for v, c in coeff_items:
            if c == 1:
                plus_vars.append(v)
            elif c == -1:
                minus_vars.append(v)
            else:
                return None
        if len(plus_vars) != 2 or len(minus_vars) != 1:
            return None

        x, y = plus_vars
        z = minus_vars[0]
        # Compact ladder uses (ub-lb) threshold bits.
        nx = len(x._threshold_lits)
        ny = len(y._threshold_lits)
        nz = len(z._threshold_lits)
        # Relation on ladder-count variables.
        # For affine relation lhs == rhs with coeffs built over values:
        #   sum(c_i * (cnt_i + lb_i)) + (loff - roff) == 0
        # -> sum(c_i * cnt_i) == - (sum(c_i * lb_i) + (loff - roff))
        delta = -(
            sum(c * v.lb for v, c in coeff_items) + (loff - roff)
        )

        net = batcher_odd_even_unary_add_network(nx, ny)
        width = int(net.n)
        if width <= 0:
            return None
        clauses, ge = _EncoderDispatch._build_unary_sum_ge_ladder(
            model,
            x._threshold_lits,
            y._threshold_lits,
            network=net,
        )
        nsum = nx + ny
        # Channel boundary-inclusive cuts for exact equality with affine shift.
        # sum_ge(r) <-> z_count_ge(r - c_target), for r in [0, nsum+1]
        for r in range(0, nsum + 2):
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
        if op == "==":
            if rhs_val % b != 0:
                return False
            return ("==", rhs_val // b)
        if op == "!=":
            if rhs_val % b != 0:
                return True
            return ("!=", rhs_val // b)
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
        if x_op == "==":
            ge_lit = _EncoderDispatch._int_cmp_constraint(x, ">=", k)
            lt_lit = _EncoderDispatch._int_cmp_constraint(x, "<", k + 1)
            _EncoderDispatch._lit_implies(clauses, model, antecedent, ge_lit)
            _EncoderDispatch._lit_implies(clauses, model, antecedent, lt_lit)
            return True
        if x_op == "!=":
            if k < x.lb or k > x.ub:
                _EncoderDispatch._lit_implies(clauses, model, antecedent, True)
                return True
            neq_lit = _EncoderDispatch._negate_bool_or_lit(_EncoderDispatch._int_cmp_constraint(x, "==", k))
            _EncoderDispatch._lit_implies(clauses, model, antecedent, neq_lit)
            return True

        lit = _EncoderDispatch._int_cmp_constraint(x, x_op, k)
        _EncoderDispatch._lit_implies(clauses, model, antecedent, lit)
        return True

    @staticmethod
    def _extract_univariate_with_bool_affine(model: "Model", expr: PBExpr) -> tuple[IntVar, int, Literal, int, int] | None:
        """Return ``(x, a, b_lit, w, offset)`` for ``a*x + w*b_lit + offset``.

        The Int part must be a full lifted threshold set for exactly one IntVar
        with uniform nonzero coefficient. The boolean part must be exactly one
        (possibly negated) non-threshold literal with nonzero coefficient.
        """
        if not expr.terms:
            return None

        per_owner: dict[int, tuple[IntVar, int, set[int]]] = {}
        bool_coeffs: dict[tuple[int, bool], tuple[Literal, int]] = {}
        for t in expr.terms:
            c = int(t.coefficient)
            if c == 0:
                continue
            lit = t.literal
            info = model._intvar_threshold_owner_by_litid.get(lit.id)
            if info is not None:
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
                key = (lit.id, lit.polarity)
                if key in bool_coeffs:
                    lit0, c0 = bool_coeffs[key]
                    bool_coeffs[key] = (lit0, c0 + c)
                else:
                    bool_coeffs[key] = (lit, c)

        bool_items = [(lit, c) for lit, c in bool_coeffs.values() if c != 0]
        if len(per_owner) != 1 or len(bool_items) != 1:
            return None

        x, a, seen = next(iter(per_owner.values()))
        if len(seen) != len(x._threshold_lits) or seen != set(range(len(x._threshold_lits))):
            return None
        b_lit, w = bool_items[0]
        offset = int(expr.constant) - a * x.lb
        return x, a, b_lit, w, offset

    @staticmethod
    def _extract_bivariate_with_bool_affine(
        model: "Model", expr: PBExpr
    ) -> tuple[IntVar, int, IntVar, int, Literal, int, int] | None:
        """Return ``(x, a, y, b, bit, w, offset)`` for ``a*x + b*y + w*bit + offset``.

        Requirements:
            * exactly two IntVars represented by full threshold sets
            * uniform nonzero integer coefficient on each IntVar thresholds
            * exactly one non-threshold boolean literal term with nonzero coefficient
            * no lifted ``int_terms``
        """
        if not expr.terms or expr.int_terms:
            return None

        per_owner: dict[int, tuple[IntVar, int, set[int]]] = {}
        bool_coeffs: dict[tuple[int, bool], tuple[Literal, int]] = {}
        for t in expr.terms:
            c = int(t.coefficient)
            if c == 0:
                continue
            lit = t.literal
            info = model._intvar_threshold_owner_by_litid.get(lit.id)
            if info is not None:
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
                continue
            key = (lit.id, lit.polarity)
            if key in bool_coeffs:
                lit0, c0 = bool_coeffs[key]
                bool_coeffs[key] = (lit0, c0 + c)
            else:
                bool_coeffs[key] = (lit, c)

        int_items = [(x, c, seen) for x, c, seen in per_owner.values() if c != 0]
        if len(int_items) != 2:
            return None
        for x, _c, seen in int_items:
            if len(seen) != len(x._threshold_lits) or seen != set(range(len(x._threshold_lits))):
                return None

        bool_items = [(lit, c) for lit, c in bool_coeffs.values() if c != 0]
        if len(bool_items) != 1:
            return None

        # Ordering keeps cache/debug behavior stable.
        int_items.sort(key=lambda it: id(it[0]))
        (x, a, _), (y, b, _) = int_items
        bit, w = bool_items[0]
        offset = int(expr.constant) - a * x.lb - b * y.lb
        return x, int(a), y, int(b), bit, int(w), int(offset)

    @staticmethod
    def _extract_unit_bool_sum_affine(model: "Model", expr: PBExpr) -> tuple[list[Literal], int] | None:
        """Return ``(lits, offset)`` for ``sum(lits) + offset`` with unit coefficients.

        The expression must contain no lifted IntVar threshold literals and every
        term must have coefficient exactly ``+1``.
        """
        if expr.int_terms:
            return None
        lits: list[Literal] = []
        for t in expr.terms:
            if int(t.coefficient) != 1:
                return None
            lit = t.literal
            if model._intvar_threshold_owner_by_litid.get(lit.id) is not None:
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
    def _emit_sum_le_gated(
        clauses: list[Clause],
        model: "Model",
        antecedent: bool | Literal,
        lits: Sequence[Literal],
        bound: int,
        ge_cache: list[bool | Literal] | None,
    ) -> list[bool | Literal] | None:
        """Append CNF for ``antecedent -> (sum(lits) <= bound)``."""
        n = len(lits)
        if bound >= n:
            return ge_cache
        if bound < 0:
            _EncoderDispatch._lit_implies(clauses, model, antecedent, False)
            return ge_cache
        if bound == 0:
            for lit in lits:
                _EncoderDispatch._lit_implies(clauses, model, antecedent, ~lit)
            return ge_cache
        if bound == n - 1:
            negated = [~lit for lit in lits]
            if isinstance(antecedent, bool):
                if antecedent:
                    clauses.append(Clause(model, negated))
                return ge_cache
            clauses.append(Clause(model, [~antecedent, *negated]))
            return ge_cache
        if ge_cache is None:
            seq_clauses, ge_cache = _EncoderDispatch._build_sequential_ge_counter(model, lits)
            clauses.extend(seq_clauses)
        # sum <= bound  <=>  not(sum >= bound+1)
        ge_lit = ge_cache[bound + 1]
        if isinstance(ge_lit, bool):
            _EncoderDispatch._lit_implies(clauses, model, antecedent, not ge_lit)
        else:
            _EncoderDispatch._lit_implies(clauses, model, antecedent, ~ge_lit)
        return ge_cache

    @staticmethod
    def _emit_sum_ge_gated(
        clauses: list[Clause],
        model: "Model",
        antecedent: bool | Literal,
        lits: Sequence[Literal],
        threshold: int,
        ge_cache: list[bool | Literal] | None,
    ) -> list[bool | Literal] | None:
        """Append CNF for ``antecedent -> (sum(lits) >= threshold)``."""
        n = len(lits)
        if threshold <= 0:
            return ge_cache
        if threshold > n:
            _EncoderDispatch._lit_implies(clauses, model, antecedent, False)
            return ge_cache
        if threshold == n:
            for lit in lits:
                _EncoderDispatch._lit_implies(clauses, model, antecedent, lit)
            return ge_cache
        if threshold == 1:
            if isinstance(antecedent, bool):
                if antecedent:
                    clauses.append(Clause(model, list(lits)))
                return ge_cache
            clauses.append(Clause(model, [~antecedent, *lits]))
            return ge_cache
        if ge_cache is None:
            seq_clauses, ge_cache = _EncoderDispatch._build_sequential_ge_counter(model, lits)
            clauses.extend(seq_clauses)
        ge_lit = ge_cache[threshold]
        _EncoderDispatch._lit_implies(clauses, model, antecedent, ge_lit)
        return ge_cache

    @staticmethod
    def _emit_sum_le_gated_conj(
        clauses: list[Clause],
        model: "Model",
        left: bool | Literal,
        right: bool | Literal,
        lits: Sequence[Literal],
        bound: int,
        ge_cache: list[bool | Literal] | None,
    ) -> list[bool | Literal] | None:
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
        ge_cache: list[bool | Literal] | None,
    ) -> list[bool | Literal] | None:
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
    def _emit_sum_ge_implies_lit(
        clauses: list[Clause],
        model: "Model",
        lits: Sequence[Literal],
        threshold: int,
        consequent: bool | Literal,
        ge_cache: list[bool | Literal] | None,
    ) -> list[bool | Literal] | None:
        """Append CNF for ``(sum(lits) >= threshold) -> consequent``."""
        n = len(lits)
        if threshold <= 0:
            _EncoderDispatch._lit_implies(clauses, model, True, consequent)
            return ge_cache
        if threshold > n:
            return ge_cache
        if threshold == 1:
            for lit in lits:
                _EncoderDispatch._lit_implies(clauses, model, lit, consequent)
            return ge_cache
        if threshold == 2:
            redundant_pairs: set[tuple[int, int]] = set()
            for group in model._known_amo_groups.values():
                group_list = list(group)
                for i in range(len(group_list)):
                    for j in range(i + 1, len(group_list)):
                        a = int(group_list[i])
                        b = int(group_list[j])
                        redundant_pairs.add((a, b) if a < b else (b, a))
            for i in range(len(lits)):
                li = lits[i]
                for j in range(i + 1, len(lits)):
                    lj = lits[j]
                    key = (li.id, lj.id) if li.id < lj.id else (lj.id, li.id)
                    if key in redundant_pairs:
                        continue
                    if isinstance(consequent, bool):
                        if not consequent:
                            clauses.append(Clause(model, [~li, ~lj]))
                    else:
                        clauses.append(Clause(model, [~li, ~lj, consequent]))
            return ge_cache
        if threshold == n:
            negated = [~lit for lit in lits]
            if isinstance(consequent, bool):
                if not consequent:
                    clauses.append(Clause(model, negated))
                return ge_cache
            clauses.append(Clause(model, [*negated, consequent]))
            return ge_cache
        if ge_cache is None:
            seq_clauses, ge_cache = _EncoderDispatch._build_sequential_ge_counter(model, lits)
            clauses.extend(seq_clauses)
        ge_lit = ge_cache[threshold]
        _EncoderDispatch._lit_implies(clauses, model, ge_lit, consequent)
        return ge_cache

    @staticmethod
    def _sum_le_bound_is_direct(n: int, bound: int) -> bool:
        return bound >= n or bound < 0 or bound == 0 or bound == n - 1

    @staticmethod
    def _sum_ge_threshold_is_direct(n: int, threshold: int) -> bool:
        return threshold <= 0 or threshold > n or threshold == n or threshold == 1

    @staticmethod
    def _try_boolsum_bigm_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect canonical upper-gated bool-sum forms with aux-free clauses.

        Supported oriented forms:
            * ``sum(unit_bools) <= k + m*lit``

        only when the loose branch is tautological and the tight branch has
        ``k <= 1``, so the encoding can stay exact and aux-free with unary,
        binary, or ternary clauses.
        """
        if op not in ("<=", "<", ">=", ">"):
            return None

        def compile_oriented(
            sum_expr: PBExpr,
            cmp_op: str,
            affine_expr: PBExpr,
        ) -> ClauseGroup | None:
            ext_sum = _EncoderDispatch._extract_unit_bool_sum_affine(model, sum_expr)
            if ext_sum is None:
                return None
            lits, sum_const = ext_sum
            # Keep constant-only branches on generic PB/Card dispatch. This
            # fast path is meant for real boolean sums.
            if not lits:
                return None

            # Constant-only RHS: sum OP k
            if (not affine_expr.int_terms) and all(int(t.coefficient) == 0 for t in affine_expr.terms):
                rhs_const = int(affine_expr.constant)
                if cmp_op == "<":
                    cmp_op = "<="
                    rhs_const -= 1
                elif cmp_op == ">":
                    return None
                k = rhs_const - sum_const
                # Keep standard cardinality dispatch for generic constant bounds.
                # Special-case only the degenerate "all must be false" bound,
                # which gives a zero-aux direct implication form.
                if not (cmp_op == "<=" and k == 0):
                    return None
                clauses: list[Clause] = []
                ge_cache: list[bool | Literal] | None = None
                if cmp_op == "<=":
                    _EncoderDispatch._emit_sum_le_gated(clauses, model, True, lits, k, ge_cache)
                    return ClauseGroup(model, clauses)
                return None

            ext_aff = _EncoderDispatch._extract_single_weighted_bool_affine(model, affine_expr)
            if ext_aff is None:
                return None
            ind_lit, mcoef, rhs_const = ext_aff
            # Normalize strict operators to non-strict by adjusting RHS.
            if cmp_op == "<":
                cmp_op = "<="
                rhs_const -= 1
            elif cmp_op == ">":
                return None

            # sum(lits) + sum_const OP rhs_const + mcoef * ind_lit
            # -> sum(lits) OP (rhs_const - sum_const) + mcoef * ind_lit
            k = rhs_const - sum_const

            # The branch literal is already used as the gate below. Its
            # syntactic polarity must not change the value of ``m * lit``.
            bound_false = k
            bound_true = k + mcoef

            clauses: list[Clause] = []
            ge_cache: list[bool | Literal] | None = None
            if cmp_op == "<=":
                upper = max(bound_false, bound_true)
                lower = min(bound_false, bound_true)
                if upper < len(lits):
                    return None
                active_gate = ~ind_lit if bound_false < bound_true else ind_lit
                if lower >= len(lits):
                    return ClauseGroup(model, clauses)
                if lower <= 1:
                    ge_cache = _EncoderDispatch._emit_sum_ge_implies_lit(
                        clauses,
                        model,
                        lits,
                        lower + 1,
                        ~active_gate,
                        ge_cache,
                    )
                    return ClauseGroup(model, clauses)
                gated_group = _EncoderDispatch._compile_structured_auto_leq(
                    model,
                    [model._lit_to_dimacs(lit) for lit in lits],
                    [1] * len(lits),
                    lower,
                ).only_if(active_gate)
                return gated_group
            return None

        # Primary orientation: sum_expr OP affine_expr
        out = compile_oriented(lhs, op, rhs)
        if out is not None:
            return out

        # Swapped orientation:
        #   affine >= sum  <=> sum <= affine
        swapped = {"<=": ">=", "<": ">", ">=": "<=", ">": "<"}
        out = compile_oriented(rhs, swapped[op], lhs)
        if out is not None:
            return out
        return None

    @staticmethod
    def _emit_int_boolsum_le_gated(
        clauses: list[Clause],
        model: "Model",
        antecedent: bool | Literal,
        x: IntVar,
        a: int,
        bool_lits: Sequence[Literal],
        bound: int,
        ge_cache: list[bool | Literal] | None,
    ) -> list[bool | Literal] | None:
        """Append CNF for ``antecedent -> (a*x + sum(bool_lits) <= bound)``."""
        # Enumerate ladder cuts like univariate/bivariate fast paths and push a
        # gated upper bound on the bool sum for each cut.
        for k in range(x.lb, x.ub + 2):
            x_ge_k = _EncoderDispatch._int_cmp_constraint(x, ">=", k)
            if a > 0:
                cond = x_ge_k
                rhs_bound = bound - a * k
            else:
                cond = _EncoderDispatch._negate_bool_or_lit(x_ge_k)
                rhs_bound = bound - a * (k - 1)
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
        ge_cache: list[bool | Literal] | None,
    ) -> list[bool | Literal] | None:
        """Append CNF for ``antecedent -> (a*x + sum(bool_lits) >= bound)``."""
        for k in range(x.lb, x.ub + 2):
            if a > 0:
                cond = _EncoderDispatch._int_cmp_constraint(x, "<", k)
                rhs_threshold = bound - a * (k - 1)
            else:
                cond = _EncoderDispatch._int_cmp_constraint(x, ">=", k)
                rhs_threshold = bound - a * k
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

            clauses: list[Clause] = []
            ge_cache: list[bool | Literal] | None = None
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
        """Detect ``sum(nonnegative_terms) <= 0`` and force all terms to zero.

        After normalization all PB terms are nonnegative weighted literals.
        The only non-trivial zero-bound case is ``sum(w_i*l_i) <= 0`` with
        ``w_i > 0``, which implies every literal must be false.
        """
        if op != "<=":
            return None
        pairs, const = _EncoderDispatch._normalize_pb(lhs, rhs)
        cmp_op, bound = _EncoderDispatch._bound_from_zero_compare(op, const)
        if cmp_op != "<=" or int(bound) != 0:
            return None
        if not pairs:
            return None
        seen: set[int] = set()
        clauses: list[Clause] = []
        for _w, lit in pairs:
            dim = int(model._lit_to_dimacs(lit))
            if dim in seen:
                continue
            seen.add(dim)
            clauses.append(Clause(model, [~lit]))
        return ClauseGroup(model, clauses)

    @staticmethod
    def _build_sequential_ge_counter(model: "Model", lits: Sequence[Literal]) -> tuple[list[Clause], list[bool | Literal]]:
        """Build ``count >= r`` literals for a sequence of booleans.

        Historical note:
            The helper name is legacy. The implementation now uses a balanced
            tree of unary merges rather than the old quadratic sequential table.

        Returns:
            ``(clauses, ge)`` where ``ge[r]`` encodes ``sum(lits) >= r`` for
            ``r in [0, len(lits)]`` and ``ge[0]`` is ``True``.
        """
        n = len(lits)
        if n == 0:
            return [], [True]
        if n == 1:
            return [], [True, lits[0]]

        clauses: list[Clause] = []
        ladders: list[list[bool | Literal]] = [[lit] for lit in lits]
        while len(ladders) > 1:
            next_ladders: list[list[bool | Literal]] = []
            for idx in range(0, len(ladders), 2):
                if idx + 1 >= len(ladders):
                    next_ladders.append(ladders[idx])
                    continue
                merge_clauses, ge = _EncoderDispatch._build_unary_sum_ge_ladder(
                    model,
                    ladders[idx],
                    ladders[idx + 1],
                )
                clauses.extend(merge_clauses)
                next_ladders.append(ge[1:])
            ladders = next_ladders
        return clauses, [True, *ladders[0]]

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
            clauses, ge = _EncoderDispatch._build_sequential_ge_counter(model, bool_lits)
            n = len(bool_lits)

            # Channel all threshold cuts including the impossible upper boundary
            # at ``ub + 1``. The closed-domain model needs that final cut to
            # distinguish ``x == ub`` from larger shifted bool sums.
            # This is required for exact equality when domains are shifted.
            for k in range(x.lb, x.ub + 2):
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

        normalized = _EncoderDispatch._normalize_bivariate_to_leq(a, b, c_target, op)
        if normalized is None:
            return None
        obligations, _is_eq = normalized

        clauses: list[Clause] = []
        for a1, b1, c1, _ in obligations:
            # iterate over smaller x-domain for fewer generated implications
            xx, aa, yy, bb = x, a1, y, b1
            if (xx.ub - xx.lb) > (yy.ub - yy.lb):
                xx, yy = yy, xx
                aa, bb = bb, aa

            # If coefficient of iterated var is zero after swap/normalization, skip (should not happen with 2 vars)
            if aa == 0 or bb == 0:
                return None

            # Map each distinct consequent (limit) to the weakest possible antecedent.
            # For aa > 0, we want the SMALLEST k such that x >= k implies the limit.
            # For aa < 0, we want the LARGEST k such that x < k (or ~x >= k) implies the limit.
            limit_to_weakest_k: dict[tuple[str, int], int] = {}

            for k in range(xx.lb, xx.ub + 2):
                # Calculate the limit for this threshold k.
                if aa > 0:
                    V = c1 - aa * k
                else:
                    V = c1 - aa * (k - 1)

                if bb > 0:
                    limit_val = V // bb
                    consequent_key = ("<=", limit_val)
                else:
                    limit_val = -((-V) // bb)
                    consequent_key = (">=", limit_val)

                if consequent_key not in limit_to_weakest_k:
                    limit_to_weakest_k[consequent_key] = k
                else:
                    # If aa > 0, we want to minimize k (weaker antecedent x >= k).
                    # If aa < 0, we want to maximize k (weaker antecedent ~x >= k).
                    if aa > 0:
                        if k < limit_to_weakest_k[consequent_key]:
                            limit_to_weakest_k[consequent_key] = k
                    else:
                        if k > limit_to_weakest_k[consequent_key]:
                            limit_to_weakest_k[consequent_key] = k

            for (op_y, lim), k in limit_to_weakest_k.items():
                if k <= xx.lb:
                    x_ge_k: bool | Literal = True
                elif k > xx.ub:
                    x_ge_k = False
                else:
                    x_ge_k = xx.__ge__(k)
                
                if aa > 0:
                    antecedent = x_ge_k
                else:
                    antecedent = _EncoderDispatch._negate_bool_or_lit(x_ge_k)

                consequent = _EncoderDispatch._int_cmp_constraint(yy, op_y, lim)
                _EncoderDispatch._lit_implies(clauses, model, antecedent, consequent)
        return ClauseGroup(model, clauses)

    @staticmethod
    def _try_trivariate_int_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile ternary sum constraints without PB/Card.

        Supported shape:
            ``x + y <= z`` and ``x + y < z`` (including affine offsets after
            normalization, i.e. ``x + y - z <= c``).

        This path introduces zero auxiliary variables and emits only binary/
        ternary clauses via ladder threshold implications.
        """
        if op not in ("<=", "<"):
            return None

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
        if len(coeff_items) != 3:
            return None

        # lhs OP rhs  =>  sum_i(c_i * x_i) OP c_target
        c_target = -(loff - roff)
        if op == "<":
            c_target -= 1

        plus_vars: list[IntVar] = []
        minus_vars: list[IntVar] = []
        for v, c in coeff_items:
            if c == 1:
                plus_vars.append(v)
            elif c == -1:
                minus_vars.append(v)
            else:
                return None
        if len(plus_vars) != 2 or len(minus_vars) != 1:
            return None

        x, y = plus_vars
        z = minus_vars[0]
        nx = len(x._threshold_lits)
        ny = len(y._threshold_lits)
        net = batcher_odd_even_unary_add_network(nx, ny)
        pair_clause_upper = (nx + 1) * (ny + 1)
        merge_clause_upper = 6 * len(net) + (nx + ny)

        if pair_clause_upper <= merge_clause_upper:
            return _EncoderDispatch._compile_trivariate_int_pairwise_leq(model, x, y, z, c_target)
        return _EncoderDispatch._compile_trivariate_int_merged_leq(model, x, y, z, c_target, network=net)

    @staticmethod
    def _compile_trivariate_int_pairwise_leq(
        model: "Model",
        x: IntVar,
        y: IntVar,
        z: IntVar,
        c_target: int,
    ) -> ClauseGroup:
        """Compile ``x + y - z <= c_target`` by pairwise threshold implications."""
        if (x.ub - x.lb) > (y.ub - y.lb):
            x, y = y, x

        clauses: list[Clause] = []
        for i in range(x.lb, x.ub + 1):
            xi = _EncoderDispatch._int_cmp_constraint(x, ">=", i)
            if xi is False:
                continue
            for j in range(y.lb, y.ub + 1):
                yj = _EncoderDispatch._int_cmp_constraint(y, ">=", j)
                if yj is False:
                    continue

                zk = _EncoderDispatch._int_cmp_constraint(z, ">=", i + j - c_target)
                if zk is True:
                    continue

                if xi is True and yj is True:
                    _EncoderDispatch._lit_implies(clauses, model, True, zk)
                elif xi is True:
                    _EncoderDispatch._lit_implies(clauses, model, yj, zk)
                elif yj is True:
                    _EncoderDispatch._lit_implies(clauses, model, xi, zk)
                else:
                    if zk is False:
                        clauses.append(Clause(model, [~xi, ~yj]))
                    else:
                        clauses.append(Clause(model, [~xi, ~yj, zk]))
        return ClauseGroup(model, clauses)

    @staticmethod
    def _compile_trivariate_int_merged_leq(
        model: "Model",
        x: IntVar,
        y: IntVar,
        z: IntVar,
        c_target: int,
        *,
        network=None,
    ) -> ClauseGroup:
        """Compile ``x + y - z <= c_target`` via unary merged sum thresholds."""
        clauses, sum_ge = _EncoderDispatch._build_unary_sum_ge_ladder(
            model,
            x._threshold_lits,
            y._threshold_lits,
            network=network,
        )
        nsum = len(sum_ge) - 1
        delta_count = c_target - x.lb - y.lb + z.lb

        for r in range(1, nsum + 1):
            sum_ge_r = sum_ge[r]
            z_count_ge = r - delta_count
            if z_count_ge <= 0:
                zk: bool | Literal = True
            elif z_count_ge > len(z._threshold_lits):
                zk = False
            else:
                zk = _EncoderDispatch._int_cmp_constraint(z, ">=", z.lb + z_count_ge)
            _EncoderDispatch._lit_implies(clauses, model, sum_ge_r, zk)

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

        int_aff = a * x + b * y
        g_false = _EncoderDispatch._try_bivariate_int_fastpath(model, PBExpr.from_item(int_aff), op, PBExpr.from_item(c_target))
        if g_false is None:
            return None
        g_true = _EncoderDispatch._try_bivariate_int_fastpath(
            model, PBExpr.from_item(int_aff), op, PBExpr.from_item(c_target - w)
        )
        if g_true is None:
            return None

        clauses = [*g_false.only_if(~bit), *g_true.only_if(bit)]
        return ClauseGroup(model, clauses)

    @staticmethod
    def compile(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup:
        """Compile a PB comparison with fast paths and PB/Card fallback."""
        lhs = lhs._realize_int_terms(model)
        rhs = rhs._realize_int_terms(model)
        unary_adder_eq_fast = _EncoderDispatch._try_unary_adder_eq_fastpath(model, lhs, op, rhs)
        if unary_adder_eq_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_unary_adder_eq op={op} clauses={len(unary_adder_eq_fast)}")
            return unary_adder_eq_fast
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
