from __future__ import annotations
import math
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import reduce
from typing import Iterable, Mapping, Optional, Sequence
from pysat.formula import CNF, WCNF
from hermax.utils import batcher_odd_even_unary_add_network
from pysat.solvers import Solver as PySATSolver
from hermax.non_incremental import RC2 as HermaxRC2
from hermax.core.time_limits import validate_time_limit
from hermax.core.interrupt_recovery import InterruptRecovery
from hermax.internal.pysat_execution import solve_pysat_with_time_limit
from hermax.internal.sat_replay import PySATReplaySolver

from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from .expressions import *
    from .variables import *
    from .encoders import *
    from .core import *

from .expressions import *
from .expressions import _detection_error, _nonlinear_error, _ensure_same_model, _ensure_same_model_pair_fast, _LazyIntExpr, FLOAT_ZERO_TOL
from .variables import *
from .variables import _BaseVector, _BaseDict, _BaseMatrixView, _MultiplexerInt, _VectorElementInt
from .encoders import *
from .encoders import _DeferredPBEntry, _EncoderDispatch
from .encoders import _canonical_pb_cache_key
from hermax.internal.kmerge import DEFAULT_KMERGE_CONFIG, KMergeConfig


class _ObjectiveProxy:
    __slots__ = ("_model", "_lit_to_sid", "_lit_weights", "_offset")

    def __init__(self, model: "Model"):
        self._model = model
        self._lit_to_sid: dict[int, int] = {}
        self._lit_weights: dict[int, int] = {}
        self._offset: int = 0

    def __getitem__(self, weight: int) -> "_WeightBucket":
        self._model._ensure_no_tier_objective_active()
        scaled, raw = self._model._coerce_soft_weight(weight, allow_zero=False)
        return _WeightBucket(self._model, scaled, raw)

    def __setitem__(self, weight: int, value) -> None:
        # Required for Python's `obj[key] += x` protocol. The mutation is already
        # performed by WeightBucket.__iadd__; this assignment is a no-op.
        return None

    def _disable_all_active_softs(self) -> None:
        m = self._model
        for sid in list(m._soft_ids):
            idx = m._soft_id_to_index.get(int(sid))
            if idx is None:
                continue
            old_w, _ = m._soft[idx]
            if int(old_w) > 0:
                m._set_soft_weight_internal(int(sid), 0, allow_zero=True, allow_when_sat=True)

    def _reset_expression_state(self) -> None:
        self._lit_to_sid.clear()
        self._lit_weights.clear()
        if self._offset:
            self._model._objective_constant -= int(self._offset)
        self._offset = 0

    def _ensure_expr_soft_sid(self, dim: int, weight: int) -> int:
        m = self._model
        lit = m._dimacs_to_lit(int(dim))
        m._ensure_literal_def_realized(lit)
        sid = m._append_soft_entry(int(weight), Clause(m, [lit]), group_id=None)
        self._lit_to_sid[int(dim)] = int(sid)
        return int(sid)

    def _normalize_expr(self, constraint, *, weight: int) -> tuple[dict[int, int], int]:
        if isinstance(constraint, PBConstraint):
            raise TypeError("Objective replacement expects a linear expression (Literal/Term/PBExpr/IntVar).")
        if isinstance(constraint, _LazyIntExpr):
            constraint = constraint._realize()
        try:
            expr = PBExpr.from_item(constraint)
        except TypeError as exc:
            raise TypeError("Objective replacement expects a linear expression.") from exc
        if expr._model is not None and expr._model is not self._model:
            raise ValueError("Variables belong to different models.")
        expr = expr._realize_int_terms(self._model)
        lit_weights: dict[int, int] = {}
        offset_raw: int | float = int(weight) * int(expr.constant)
        for t in expr.terms:
            coeff_raw = t.coefficient
            coeff_abs: int | float
            if isinstance(coeff_raw, float):
                if abs(coeff_raw) <= FLOAT_ZERO_TOL:
                    continue
                coeff_abs = abs(coeff_raw)
            else:
                if coeff_raw == 0:
                    continue
                coeff_abs = abs(int(coeff_raw))

            if coeff_raw > 0:
                lit = ~t.literal
                term_raw: int | float = float(weight) * float(coeff_abs) if isinstance(coeff_abs, float) else int(weight) * int(coeff_abs)
            else:
                lit = t.literal
                term_raw = float(weight) * float(coeff_abs) if isinstance(coeff_abs, float) else int(weight) * int(coeff_abs)
                offset_raw -= term_raw
            w, _rw = self._model._coerce_soft_weight(term_raw, allow_zero=False)
            dim = self._model._lit_to_dimacs(lit)
            lit_weights[dim] = lit_weights.get(dim, 0) + int(w)
        # Policy: by default negative objective offsets are allowed and tracked
        # internally. Teams can flip this behavior on a model instance via
        # ``model.set_objective_offset_policy(allow_negative=False)``.
        if float(offset_raw) < 0 and not bool(self._model._allow_negative_objective_offsets):
            raise ValueError("Negative objective offsets are not supported by current model policy.")

        # Route positive constants to a native always-violated soft unit on
        # __false so solver-reported cost includes the offset directly.
        offset = 0
        if float(offset_raw) > FLOAT_ZERO_TOL:
            pos_w = int(offset_raw) if isinstance(offset_raw, int) else float(offset_raw)
            pos_off, _ = self._model._coerce_soft_weight(pos_w, allow_zero=False)
            false_lit = self._model._get_bool_constant_literal(False)
            dim_false = self._model._lit_to_dimacs(false_lit)
            lit_weights[dim_false] = lit_weights.get(dim_false, 0) + int(pos_off)
        elif float(offset_raw) < -FLOAT_ZERO_TOL:
            neg_abs = -offset_raw
            neg_w = int(neg_abs) if isinstance(neg_abs, int) else float(neg_abs)
            neg_off, _ = self._model._coerce_soft_weight(neg_w, allow_zero=False)
            offset = -int(neg_off)

        # Drop any canceled entries.
        lit_weights = {l: w for l, w in lit_weights.items() if int(w) != 0}
        return lit_weights, int(offset)

    def _current_lit_weights(self) -> dict[int, int]:
        out: dict[int, int] = {}
        m = self._model
        stale_dims: list[int] = []
        for dim, cached_w in self._lit_weights.items():
            sid = self._lit_to_sid.get(int(dim))
            if sid is None:
                stale_dims.append(int(dim))
                continue
            idx = m._soft_id_to_index.get(int(sid))
            if idx is None:
                stale_dims.append(int(dim))
                continue
            w, _ = m._soft[idx]
            if int(w) > 0:
                out[int(dim)] = int(w)
                if int(cached_w) != int(w):
                    self._lit_weights[int(dim)] = int(w)
            else:
                stale_dims.append(int(dim))
        for dim in stale_dims:
            self._lit_weights.pop(int(dim), None)
            self._lit_to_sid.pop(int(dim), None)
        return out

    def _apply_lit_weights(self, lit_weights: dict[int, int], offset: int):
        m = self._model
        hard0 = len(m._hard)
        soft0 = len(m._soft)
        current = self._current_lit_weights()
        all_lits = set(current.keys()) | set(lit_weights.keys())
        for dim in all_lits:
            sid = self._lit_to_sid.get(dim)
            new_w = int(lit_weights.get(dim, 0))
            if sid is None:
                if new_w <= 0:
                    continue
                self._ensure_expr_soft_sid(dim, new_w)
                continue
            idx = m._soft_id_to_index.get(sid)
            if idx is None:
                if new_w <= 0:
                    self._lit_to_sid.pop(dim, None)
                    continue
                self._ensure_expr_soft_sid(dim, new_w)
                continue
            old_w, _cl = m._soft[idx]
            if int(old_w) == new_w:
                continue
            m._set_soft_weight_internal(sid, new_w, allow_zero=True, allow_when_sat=True)

        self._lit_weights = {int(dim): int(w) for dim, w in lit_weights.items() if int(w) > 0}

        delta = int(offset) - int(self._offset)
        if delta:
            m._objective_constant += int(delta)
        self._offset = int(offset)
        m._inc_state.route_deltas(hard0, soft0)
        return self

    def _add_lit_weights(self, add_map: dict[int, int], offset_delta: int):
        m = self._model
        hard0 = len(m._hard)
        soft0 = len(m._soft)
        for dim, w in add_map.items():
            inc = int(w)
            if inc <= 0:
                continue
            sid = self._lit_to_sid.get(int(dim))
            if sid is None:
                self._ensure_expr_soft_sid(int(dim), inc)
                self._lit_weights[int(dim)] = int(self._lit_weights.get(int(dim), 0)) + inc
                continue
            idx = m._soft_id_to_index.get(int(sid))
            if idx is None:
                self._ensure_expr_soft_sid(int(dim), inc)
                self._lit_weights[int(dim)] = int(self._lit_weights.get(int(dim), 0)) + inc
                continue
            old_w, _cl = m._soft[idx]
            new_w = int(old_w) + inc
            if new_w != int(old_w):
                m._set_soft_weight_internal(int(sid), new_w, allow_zero=True, allow_when_sat=True)
            self._lit_weights[int(dim)] = new_w

        if int(offset_delta):
            m._objective_constant += int(offset_delta)
            self._offset += int(offset_delta)
        m._inc_state.route_deltas(hard0, soft0)
        return self

    def set(self, constraint, *, weight: int = 1):
        """Replace expression-managed objective terms with one expression."""
        self._model._ensure_no_tier_objective_active()
        scaled_w, _raw_w = self._model._coerce_soft_weight(weight, allow_zero=False)
        new_lit_weights, new_offset = self._normalize_expr(constraint, weight=int(scaled_w))
        return self._apply_lit_weights(new_lit_weights, new_offset)

    def add(self, constraint, *, weight: int = 1):
        """Add one linear expression to expression-managed objective terms."""
        self._model._ensure_no_tier_objective_active()
        scaled_w, _raw_w = self._model._coerce_soft_weight(weight, allow_zero=False)
        add_map, add_offset = self._normalize_expr(constraint, weight=int(scaled_w))
        return self._add_lit_weights(add_map, int(add_offset))

    def add_soft(self, constraint, weight: int):
        """Add one managed soft objective term and return a grouped handle."""
        self._model._ensure_no_tier_objective_active()
        scaled_w, raw_w = self._model._coerce_soft_weight(weight, allow_zero=False)
        gid, sids = self._model._add_soft(int(scaled_w), constraint, dedup=bool(self._model._soft_dedup_enabled), raw_weight=float(raw_w))
        return SoftRef(gid, sids)

    def update_soft(self, target, new_weight: int) -> None:
        """Update the weight of one logical soft object referenced by ``SoftRef``."""
        self._model._ensure_no_tier_objective_active()
        scaled_w, raw_w = self._model._coerce_soft_weight(new_weight, allow_zero=False)
        if isinstance(target, SoftRef):
            ids = list(target.soft_ids)
        else:
            raise TypeError("target must be a SoftRef returned by obj.add_soft().")
        if not ids:
            return
        for sid in ids:
            self._model._soft_raw_weight_by_id[int(sid)] = float(raw_w)
            self._model._set_soft_weight_internal(int(sid), int(scaled_w), allow_zero=False, allow_when_sat=False)

    def clear(self):
        """Disable all expression-managed objective terms."""
        self._disable_all_active_softs()
        self._reset_expression_state()
        return self

    def replace_with(self, constraint):
        """Replace the currently active objective with ``constraint``."""
        self._model._ensure_no_tier_objective_active()
        # Full objective replacement:
        # disable all currently active soft clauses first, then install the new
        # expression-managed objective.
        self._disable_all_active_softs()
        self._reset_expression_state()
        return self.set(constraint)

    def __iadd__(self, constraint):
        """Add a weighted objective term directly with implicit weight 1.

        Examples:
            ``model.obj += (3 * a + 2 * b)``
            ``model.obj += sum(weights[i] * lits[i] for i in range(n))``
        """
        self._model._ensure_no_tier_objective_active()
        if isinstance(
            constraint,
            (
                PBExpr,
                Term,
                _LazyIntExpr,
                int,  # includes sum(...) seed = 0 and pure offsets
            ),
        ) and not isinstance(constraint, bool):
            return self.add(constraint, weight=1)
        self._model._add_soft(1, constraint, raw_weight=1.0)
        return self


class _WeightBucket:
    __slots__ = ("_model", "_weight", "_raw_weight")

    def __init__(self, model: "Model", weight: int, raw_weight: float):
        self._model = model
        self._weight = weight
        self._raw_weight = raw_weight

    def __iadd__(self, constraint):
        self._model._ensure_no_tier_objective_active()
        if isinstance(
            constraint,
            (
                PBExpr,
                Term,
                _LazyIntExpr,
                int,
            ),
        ) and not isinstance(constraint, bool):
            self._model.obj.add(constraint, weight=self._weight)
        else:
            self._model._add_soft(self._weight, constraint, raw_weight=self._raw_weight)
        return self


class _TierWeightBucket:
    __slots__ = ("_proxy", "_tier", "_weight", "_raw_weight")

    def __init__(self, proxy: "_TierObjectiveProxy", tier: int, weight: int, raw_weight: float):
        self._proxy = proxy
        self._tier = int(tier)
        self._weight = int(weight)
        self._raw_weight = float(raw_weight)

    def __iadd__(self, constraint):
        self._proxy._add_to_tier(self._tier, self._weight, self._raw_weight, constraint)
        return self


class _TierObjectiveProxy:
    __slots__ = ("_model", "_tiers")

    def __init__(self, model: "Model"):
        self._model = model
        # tier -> {"lit_weights": dict[dimacs, int], "offset": int}
        self._tiers: dict[int, dict[str, object]] = {}

    def _normalize_expr(self, constraint, *, weight: int) -> tuple[dict[int, int], int]:
        if isinstance(constraint, PBConstraint):
            raise TypeError("Tier objective expects a linear expression (Literal/Term/PBExpr/IntVar) or Clause/ClauseGroup.")
        if isinstance(constraint, _LazyIntExpr):
            constraint = constraint._realize()
        try:
            expr = PBExpr.from_item(constraint)
        except TypeError as exc:
            raise TypeError("Tier objective expects a linear expression.") from exc
        if expr._model is not None and expr._model is not self._model:
            raise ValueError("Variables belong to different models.")
        expr = expr._realize_int_terms(self._model)
        lit_weights: dict[int, int] = {}
        offset_raw: int | float = int(weight) * int(expr.constant)
        for t in expr.terms:
            coeff_raw = t.coefficient
            if isinstance(coeff_raw, float):
                if abs(coeff_raw) <= FLOAT_ZERO_TOL:
                    continue
                coeff_abs = abs(coeff_raw)
            else:
                if coeff_raw == 0:
                    continue
                coeff_abs = abs(int(coeff_raw))
            if coeff_raw > 0:
                lit = ~t.literal
                term_raw: int | float = float(weight) * float(coeff_abs) if isinstance(coeff_abs, float) else int(weight) * int(coeff_abs)
            else:
                lit = t.literal
                term_raw = float(weight) * float(coeff_abs) if isinstance(coeff_abs, float) else int(weight) * int(coeff_abs)
                offset_raw -= term_raw
            w, _ = self._model._coerce_soft_weight(term_raw, allow_zero=False)
            dim = self._model._lit_to_dimacs(lit)
            lit_weights[dim] = lit_weights.get(dim, 0) + int(w)

        if float(offset_raw) < 0 and not bool(self._model._allow_negative_objective_offsets):
            raise ValueError("Negative objective offsets are not supported by current model policy.")

        offset = 0
        if float(offset_raw) > FLOAT_ZERO_TOL:
            pos_w = int(offset_raw) if isinstance(offset_raw, int) else float(offset_raw)
            pos_off, _ = self._model._coerce_soft_weight(pos_w, allow_zero=False)
            false_lit = self._model._get_bool_constant_literal(False)
            dim_false = self._model._lit_to_dimacs(false_lit)
            lit_weights[dim_false] = lit_weights.get(dim_false, 0) + int(pos_off)
        elif float(offset_raw) < -FLOAT_ZERO_TOL:
            neg_abs = -offset_raw
            neg_w = int(neg_abs) if isinstance(neg_abs, int) else float(neg_abs)
            neg_off, _ = self._model._coerce_soft_weight(neg_w, allow_zero=False)
            offset = -int(neg_off)

        lit_weights = {l: int(w) for l, w in lit_weights.items() if int(w) != 0}
        return lit_weights, int(offset)

    def _ensure_tier(self, tier: int) -> dict[str, object]:
        if int(tier) < 0:
            raise ValueError("tier index must be a non-negative integer.")
        return self._tiers.setdefault(int(tier), {"lit_weights": {}, "offset": 0})

    def _check_exclusive(self) -> None:
        self._model._ensure_no_flat_objective_active()

    def _add_to_tier(self, tier: int, weight: int, raw_weight: float, constraint) -> None:
        del raw_weight  # kept for API symmetry with objective bucket.
        self._check_exclusive()
        if isinstance(constraint, Literal) and constraint._model is not self._model:
            raise ValueError("Variables belong to different models.")
        if isinstance(constraint, PBConstraint):
            raise TypeError("Tier objective does not accept PBConstraint directly; use .clauses() or a linear expression.")
        entry = self._ensure_tier(int(tier))
        lit_weights = entry["lit_weights"]  # type: ignore[assignment]
        assert isinstance(lit_weights, dict)

        if isinstance(constraint, (Literal, Clause, ClauseGroup, bool)):
            group = self._model._as_clausegroup(constraint)
            if group.is_empty():
                return
            c = group.single_clause_or_none()
            if c is not None:
                if len(c) == 0:
                    raise TypeError("Tier objective does not support empty soft clauses.")
                if len(c) == 1:
                    dim = int(c[0])
                else:
                    r = self._model.bool()
                    self._model &= ClauseGroup(self._model, [c]).only_if(r)
                    dim = self._model._lit_to_dimacs(~r)
                lit_weights[int(dim)] = int(lit_weights.get(int(dim), 0)) + int(weight)
                return
            r = self._model.bool()
            self._model &= group.only_if(r)
            dim = self._model._lit_to_dimacs(~r)
            lit_weights[int(dim)] = int(lit_weights.get(int(dim), 0)) + int(weight)
            return

        add_map, add_off = self._normalize_expr(constraint, weight=int(weight))
        for dim, w in add_map.items():
            lit_weights[int(dim)] = int(lit_weights.get(int(dim), 0)) + int(w)
        entry["offset"] = int(entry.get("offset", 0)) + int(add_off)

    def __getitem__(self, key) -> "_TierWeightBucket":
        self._check_exclusive()
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("tier_obj expects indexing as tier_obj[tier_index, weight].")
        tier, weight = key
        if isinstance(tier, bool) or not isinstance(tier, int):
            raise TypeError("tier index must be an integer.")
        if int(tier) < 0:
            raise ValueError("tier index must be a non-negative integer.")
        scaled, raw = self._model._coerce_soft_weight(weight, allow_zero=False)
        return _TierWeightBucket(self, int(tier), int(scaled), float(raw))

    def __setitem__(self, key, value) -> None:
        # No-op for Python's obj[key] += protocol.
        del key, value
        return None

    def set_lexicographic(self, *expressions):
        self._check_exclusive()
        self.clear()
        for i, expr in enumerate(expressions):
            self._add_to_tier(int(i), 1, 1.0, expr)
        return self

    def clear(self):
        self._tiers.clear()
        return self

    def is_active(self) -> bool:
        for _tier, d in self._tiers.items():
            lw = d.get("lit_weights", {})
            off = int(d.get("offset", 0))
            if isinstance(lw, dict) and any(int(v) > 0 for v in lw.values()):
                return True
            if off != 0:
                return True
        return False

    def iter_active_tiers(self) -> list[tuple[int, dict[int, int], int]]:
        out: list[tuple[int, dict[int, int], int]] = []
        for tier in sorted(self._tiers.keys()):
            d = self._tiers[tier]
            lw_raw = d.get("lit_weights", {})
            off = int(d.get("offset", 0))
            if not isinstance(lw_raw, dict):
                continue
            lw = {int(k): int(v) for k, v in lw_raw.items() if int(v) > 0}
            if lw or off != 0:
                out.append((int(tier), lw, off))
        return out


class SolveResult:
    """Convenience result object returned by :meth:`Model.solve`."""
    __slots__ = ("status", "raw_model", "cost", "assignment", "backend", "tier_costs", "tier_models")

    def __init__(
        self,
        model: "Model",
        *,
        status: str,
        raw_model: Sequence[int] | None,
        cost: int | float | None,
        backend: str,
        tier_costs: Optional[list[int | float]] = None,
        tier_models: Optional[list[list[int]]] = None,
    ):
        self.status = status
        self.raw_model = list(raw_model) if raw_model is not None else None
        self.cost = cost
        self.backend = backend
        self.assignment = AssignmentView(model, self.raw_model or [])
        self.tier_costs = list(tier_costs) if tier_costs is not None else None
        self.tier_models = [list(m) for m in tier_models] if tier_models is not None else None

    @property
    def ok(self) -> bool:
        """Return ``True`` when a feasible assignment is available."""
        return self.status in {"sat", "optimum", "interrupted_sat"}

    def __getitem__(self, obj):
        return self.assignment[obj]


class SoftRef:
    """Reference handle returned by :meth:`Model.obj.add_soft`."""

    __slots__ = ("group_id", "soft_ids")

    def __init__(self, group_id: int, soft_ids: Sequence[int]):
        self.group_id = int(group_id)
        self.soft_ids = tuple(int(s) for s in soft_ids)

    def __iter__(self):
        return iter(self.soft_ids)

    def __len__(self) -> int:
        return len(self.soft_ids)

    def __repr__(self) -> str:
        return f"SoftRef(group_id={self.group_id}, soft_ids={list(self.soft_ids)})"


class _IncrementalCoordinator:
    """Internal stateful coordinator for Model-native incremental solving."""

    __slots__ = (
        "_model",
        "mode",
        "sat_solver",
        "sat_solver_name",
        "ip_solver",
        "ip_created",
        "solver_factory",
        "solver_kwargs",
        "ip_next_vid",
        "soft_lit_by_id",
        "hard_routed",
        "soft_routed",
    )

    def __init__(self, model: "Model"):
        self._model = model
        self.mode: str | None = None  # None | sat | maxsat
        self.sat_solver = None
        self.sat_solver_name: str | None = None
        self.ip_solver = None
        self.ip_created = False
        self.solver_factory = None
        self.solver_kwargs: dict = {}
        self.ip_next_vid = 0
        self.soft_lit_by_id: dict[int, int] = {}
        self.hard_routed = 0
        self.soft_routed = 0

    @property
    def bound(self) -> bool:
        """Whether an incremental backend is currently bound."""
        return self.mode is not None

    def close(self) -> None:
        """Close and clear the currently bound incremental backend."""
        if self.sat_solver is not None:
            self._safe_call(self.sat_solver.delete)
        if self.ip_solver is not None and self.ip_created:
            self._safe_call(self.ip_solver.close)
        self.mode = None
        self.sat_solver = None
        self.sat_solver_name = None
        self.ip_solver = None
        self.ip_created = False
        self.solver_factory = None
        self.solver_kwargs = {}
        self.ip_next_vid = 0
        self.soft_lit_by_id.clear()
        self.hard_routed = 0
        self.soft_routed = 0

    @staticmethod
    def _safe_call(fn) -> None:
        """Backend cleanup; teardown must not mask primary failures."""
        try:
            fn()
        except Exception:
            pass

    def _ip_next_var(self) -> int:
        if self.ip_solver is not None:
            try:
                v = int(self.ip_solver.new_var())
                self.ip_next_vid = max(self.ip_next_vid, v)
                return v
            except NotImplementedError:
                pass
        self.ip_next_vid += 1
        return self.ip_next_vid

    def _route_soft_index(self, idx: int) -> None:
        if self.mode != "maxsat" or self.ip_solver is None:
            return
        m = self._model
        sid = m._soft_ids[idx]
        weight, clause = m._soft[idx]
        if int(weight) <= 0:
            lit = self.soft_lit_by_id.get(sid)
            if lit is not None:
                self.ip_solver.set_soft(int(lit), 0)
            return
        lits = list(clause)
        if len(lits) == 1:
            soft_lit = int(lits[0])
            self.ip_solver.add_soft_unit(soft_lit, int(weight))
            self.soft_lit_by_id[sid] = soft_lit
            return
        relax = self._ip_next_var()
        self.ip_solver.add_soft_relaxed([int(l) for l in lits], int(weight), relax)
        self.soft_lit_by_id[sid] = -int(relax)

    def route_deltas(self, hard_start: int, soft_start: int) -> None:
        """Push hard/soft changes since offsets into the bound backend."""
        m = self._model
        hard_from = min(hard_start, self.hard_routed)
        soft_from = min(soft_start, self.soft_routed)
        if m._debug_level >= m.DEBUG_DELTA:
            m._debug(
                m.DEBUG_DELTA,
                f"route_deltas mode={self.mode} hard+={max(0, len(m._hard)-hard_from)} soft+={max(0, len(m._soft)-soft_from)}",
            )
        if self.mode is None:
            return
        if self.mode == "sat":
            # SAT backend owns hard clauses only.
            if soft_from < len(m._soft):
                return
            assert self.sat_solver is not None
            for c in m._hard[hard_from:]:
                self.sat_solver.add_clause(m._clause_to_dimacs_list(c))
            self.hard_routed = len(m._hard)
            self.soft_routed = len(m._soft)
            return
        if self.mode == "maxsat":
            assert self.ip_solver is not None
            for c in m._hard[hard_from:]:
                self.ip_solver.add_clause(m._clause_to_dimacs_list(c))
            for i in range(soft_from, len(m._soft)):
                self._route_soft_index(i)
            self.hard_routed = len(m._hard)
            self.soft_routed = len(m._soft)

    def bind_sat(self, sat_solver_name: str) -> None:
        """Bind an incremental SAT backend on current hard clauses."""
        if self.mode == "sat":
            return
        self.close()
        s = PySATSolver(name=sat_solver_name)
        s.append_formula(self._model.to_cnf().clauses)
        self.mode = "sat"
        self.sat_solver = s
        self.sat_solver_name = sat_solver_name
        self.hard_routed = len(self._model._hard)
        self.soft_routed = len(self._model._soft)

    def bind_maxsat(self, solver, solver_kwargs: dict | None) -> None:
        """Bind an incremental MaxSAT backend and replay current formula."""
        from hermax.core.ipamir_solver_interface import IPAMIRSolver

        if self.mode == "maxsat":
            return
        self.close()
        self.soft_lit_by_id.clear()
        m = self._model
        created = False
        if solver is None:
            solver = HermaxRC2
        if isinstance(solver, IPAMIRSolver):
            ip_solver = solver
        else:
            if solver is None or not callable(solver):
                raise ValueError("incremental MaxSAT requires a solver class/factory or IPAMIRSolver instance.")
            formula = m.to_wcnf()
            ip_solver = solver(formula=formula, **(solver_kwargs or {}))
            created = True
            if not isinstance(ip_solver, IPAMIRSolver):
                if hasattr(ip_solver, "close"):
                    self._safe_call(ip_solver.close)
                raise TypeError("solver callable must return an IPAMIRSolver instance.")

        # replay
        formula = m.to_wcnf()
        self.ip_next_vid = int(formula.nv)
        try:
            for _ in range(int(formula.nv)):
                self.ip_next_vid = int(ip_solver.new_var())
        except NotImplementedError:
            pass
        for c in formula.hard:
            ip_solver.add_clause([int(l) for l in c])
        self.mode = "maxsat"
        self.ip_solver = ip_solver
        self.ip_created = created
        self.solver_factory = solver
        self.solver_kwargs = dict(solver_kwargs or {})
        for i in range(len(m._soft)):
            self._route_soft_index(i)
        self.hard_routed = len(m._hard)
        self.soft_routed = len(m._soft)

    def _solve_live_sat(self, assumptions: Sequence[int], time_limit: Optional[float]) -> SolveResult:
        """Solve on the bound PySAT instance without discarding its state."""
        assert self.sat_solver is not None
        try:
            sat = solve_pysat_with_time_limit(
                self.sat_solver,
                assumptions=assumptions,
                time_limit=time_limit,
            )
        except NotImplementedError as exc:
            raise NotImplementedError(
                f"PySAT backend {self.sat_solver_name!r} does not support live time-limited solving."
            ) from exc
        if sat is None:
            return SolveResult(
                self._model,
                status="interrupted",
                raw_model=None,
                cost=None,
                backend=f"pysat.{self.sat_solver_name}",
            )
        if not sat:
            return SolveResult(
                self._model,
                status="unsat",
                raw_model=None,
                cost=None,
                backend=f"pysat.{self.sat_solver_name}",
            )
        model = self.sat_solver.get_model() or []
        return SolveResult(
            self._model,
            status="sat",
            raw_model=model,
            cost=None,
            backend=f"pysat.{self.sat_solver_name}",
        )

    def update_soft_weight(
        self,
        soft_id: int,
        new_weight: int,
        *,
        allow_zero: bool = False,
        allow_when_sat: bool = False,
    ) -> None:
        """Update one soft weight in bound backend state."""
        m = self._model
        sid = int(soft_id)
        if sid not in m._soft_id_to_index:
            raise KeyError(f"Unknown soft id {soft_id!r}")
        idx = m._soft_id_to_index[sid]
        _old_w, clause = m._soft[idx]
        m._soft[idx] = (int(new_weight), clause)
        if self.mode == "sat":
            if allow_when_sat:
                if m._debug_level >= m.DEBUG_DELTA:
                    m._debug(m.DEBUG_DELTA, f"update_soft route skipped in SAT mode sid={sid}")
                return
            raise ValueError("Cannot update soft weights while bound to SAT incremental backend.")
        if self.mode == "maxsat":
            if self.ip_solver is None:
                return
            lit = self.soft_lit_by_id.get(sid)
            if lit is None:
                self._route_soft_index(idx)
                lit = self.soft_lit_by_id.get(sid)
            if lit is None:
                raise RuntimeError("Soft id is not mapped in incremental MaxSAT backend.")
            if int(new_weight) == 0 and not allow_zero:
                raise ValueError("Cannot set soft weight to zero without allow_zero=True.")
            if m._debug_level >= m.DEBUG_DELTA:
                m._debug(
                    m.DEBUG_DELTA,
                    f"update_soft route maxsat sid={sid} lit={int(lit)} new={int(new_weight)}",
                )
            self.ip_solver.set_soft(int(lit), int(new_weight))

    def solve(
        self,
        *,
        sat_solver_name: str,
        backend: str,
        solver,
        solver_kwargs: dict | None,
        assumptions: Optional[Sequence[object]],
        raise_on_abnormal: bool,
        sat_upgrade: str,
        time_limit: Optional[float],
    ) -> SolveResult:
        """Solve using current incremental state, binding backend if needed."""
        from hermax.core.ipamir_solver_interface import is_feasible

        m = self._model
        assumptions_dimacs = m._coerce_assumptions(assumptions)
        has_soft = len(m._soft) > 0
        b = (backend or "auto").lower()
        if b not in {"auto", "sat", "maxsat"}:
            raise ValueError("backend must be one of: auto, sat, maxsat")
        su = (sat_upgrade or "upgrade").lower()
        if su not in {"upgrade", "error"}:
            raise ValueError("sat_upgrade must be one of: upgrade, error")

        if self.mode is None:
            if b == "sat":
                if has_soft:
                    raise ValueError("Cannot bind SAT backend when model has soft clauses.")
                self.bind_sat(sat_solver_name)
            elif b == "maxsat":
                self.bind_maxsat(solver, solver_kwargs)
            else:  # auto
                if has_soft:
                    self.bind_maxsat(solver, solver_kwargs)
                else:
                    self.bind_sat(sat_solver_name)
        elif self.mode == "sat" and has_soft:
            if su == "upgrade":
                self.bind_maxsat(solver, solver_kwargs)
            else:
                raise ValueError("Model is locked to SAT incremental backend; soft constraints are not allowed after SAT bind.")
        elif self.mode == "sat" and b == "maxsat":
            if su == "upgrade":
                self.bind_maxsat(solver, solver_kwargs)
            else:
                raise ValueError("Cannot change incremental backend from SAT to MaxSAT without soft constraints.")
        elif self.mode == "maxsat" and b == "sat":
            raise ValueError("Cannot change incremental backend from MaxSAT to SAT.")

        m._commit_pb()
        self.route_deltas(len(m._hard), len(m._soft))

        if self.mode == "sat":
            return self._solve_live_sat(assumptions_dimacs, time_limit)

        assert self.mode == "maxsat"
        assert self.ip_solver is not None
        if m._rebuild_on_interrupt:
            if not isinstance(self.ip_solver, InterruptRecovery):
                raise NotImplementedError(
                    "The selected live solver does not support interruption recovery."
                )
            self.ip_solver.set_rebuild_on_interrupt(True)
        self.ip_solver.solve(
            assumptions=assumptions_dimacs,
            raise_on_abnormal=bool(raise_on_abnormal),
            time_limit=time_limit,
        )
        st = self.ip_solver.get_status()
        status = _map_ipamir_status_to_model_status(st)
        feasible = is_feasible(st)
        raw_model = None
        cost = None
        if feasible:
            raw_model = self.ip_solver.get_model()
            c = self.ip_solver.get_cost()
            cost = m._format_objective_cost(int(c) + int(m._objective_constant))
        return SolveResult(m, status=status, raw_model=raw_model, cost=cost, backend=f"hermax.{self.ip_solver.signature()}")


def _map_ipamir_status_to_model_status(status) -> str:
    """Map Hermax/IPAMIR solver statuses to :class:`SolveResult` status strings."""
    # Local import to avoid importing the MaxSAT wrapper stack during module import.
    from hermax.core.ipamir_solver_interface import SolveStatus

    if status == SolveStatus.OPTIMUM:
        return "optimum"
    if status == SolveStatus.UNSAT:
        return "unsat"
    if status == SolveStatus.INTERRUPTED_SAT:
        return "interrupted_sat"
    if status == SolveStatus.INTERRUPTED:
        return "interrupted"
    if status == SolveStatus.ERROR:
        return "error"
    if status == SolveStatus.UNKNOWN:
        return "unknown"
    return "unknown"


class Model:
    """Pure-Python SAT/MaxSAT modeling container.

    ``Model`` is the mutable sink for hard constraints and weighted soft
    constraints. All other modeling objects are immutable-by-operator.
    """
    __slots__ = (
        "_next_id",
        "_registry",
        "_lits_by_id",
        "_intvar_threshold_owner_by_litid",
        "_intvar_eq_owner_by_litid",
        "_container_names",
        "_canonical_internal_lits",
        "_anon_counter",
        "_hard",
        "_soft",
        "_objective_constant",
        "_const_lits",
        "_pending_literal_defs",
        "_realized_literal_defs",
        "_realized_definition_group_ids",
        "_realizing_literal_defs",
        "_soft_ids",
        "_soft_id_to_index",
        "_next_soft_id",
        "_soft_group_to_ids",
        "_soft_id_to_group",
        "_next_soft_group_id",
        "_soft_raw_weight_by_id",
        "_inc_state",
        "_rebuild_on_interrupt",
        "_obj_proxy",
        "_tier_obj_proxy",
        "_pb_clause_cache",
        "_known_amo_groups",
        "_known_eo_groups",
        "_pending_pb_constraints",
        "_auto_commit_pb",
        "_merge_pb_optimization_enabled",
        "_kmerge_config",
        "_allow_negative_objective_offsets",
        "_soft_dedup_enabled",
        "_soft_gcd_opt_enabled",
        "_objective_precision_decimals",
        "_objective_precision_scale",
        "_debug_level",
        "_debug_stream",
        "_encoding_profile",
    )

    # Global default policy (instance copies this value at construction).
    ALLOW_NEGATIVE_OBJECTIVE_OFFSETS = True
    SOFT_DEDUP_ENABLED = True
    SOFT_GCD_OPTIMIZATION_ENABLED = True
    MERGE_PB_OPTIMIZATION_ENABLED = False
    DEBUG_NONE = 0
    DEBUG_DELTA = 1
    DEBUG_COMPILE = 2
    DEBUG_VERBOSE = 3

    def __init__(self):
        self._next_id = 1
        self._registry: dict[str, Literal] = {}
        self._lits_by_id: dict[int, Literal] = {}
        self._intvar_threshold_owner_by_litid: dict[int, tuple["IntVar", int]] = {}
        self._intvar_eq_owner_by_litid: dict[int, tuple["IntVar", int]] = {}
        self._container_names: set[str] = set()
        self._canonical_internal_lits: dict[object, Literal] = {}
        self._anon_counter = 0
        self._hard: list[tuple[int, ...]] = []
        self._soft: list[tuple[int, tuple[int, ...]]] = []
        self._objective_constant = 0
        self._const_lits: dict[bool, Literal] = {}
        self._pending_literal_defs: dict[int, ClauseGroup] = {}
        self._realized_literal_defs: set[int] = set()
        self._realized_definition_group_ids: set[int] = set()
        self._realizing_literal_defs: set[int] = set()
        self._soft_ids: list[int] = []
        self._soft_id_to_index: dict[int, int] = {}
        self._next_soft_id = 1
        self._soft_group_to_ids: dict[int, list[int]] = {}
        self._soft_id_to_group: dict[int, int] = {}
        self._next_soft_group_id = 1
        self._soft_raw_weight_by_id: dict[int, float] = {}
        self._inc_state = _IncrementalCoordinator(self)
        self._rebuild_on_interrupt = False
        self._obj_proxy = _ObjectiveProxy(self)
        self._tier_obj_proxy = _TierObjectiveProxy(self)
        self._pb_clause_cache: dict[tuple, ClauseGroup] = {}
        self._known_amo_groups: dict[tuple[int, ...], tuple[int, ...]] = {}
        self._known_eo_groups: dict[tuple[int, ...], tuple[int, ...]] = {}
        self._pending_pb_constraints: list[_DeferredPBEntry] = []
        self._auto_commit_pb = False
        self._merge_pb_optimization_enabled = bool(self.MERGE_PB_OPTIMIZATION_ENABLED)
        self._kmerge_config = DEFAULT_KMERGE_CONFIG
        self._allow_negative_objective_offsets = bool(self.ALLOW_NEGATIVE_OBJECTIVE_OFFSETS)
        self._soft_dedup_enabled = bool(self.SOFT_DEDUP_ENABLED)
        self._soft_gcd_opt_enabled = bool(self.SOFT_GCD_OPTIMIZATION_ENABLED)
        self._objective_precision_decimals: int | None = None
        self._objective_precision_scale: int = 1
        self._debug_level = 0
        self._debug_stream = None
        self._encoding_profile: EncodingProfile | None = None

    def set_debug(self, level: int = 1, stream=None) -> None:
        """Configure model debug tracing.

        Levels:
            * 0: disabled
            * 1: delta-level logs (hard/soft additions, weight updates)
            * 2: compiler summaries (normalized PB/Card form, cache hit/miss)
            * 3: verbose clause dumps
        """
        if not isinstance(level, int) or int(level) < 0:
            raise ValueError("debug level must be a non-negative integer.")
        self._debug_level = int(level)
        self._debug_stream = stream

    def set_merge_pb_optimization(self, enabled: bool = True) -> None:
        """Enable or disable deferred PB batch merge optimization."""
        self._merge_pb_optimization_enabled = bool(enabled)

    def set_rebuild_on_interrupt(self, enabled: bool = True) -> None:
        """Allow a live incremental backend to rebuild after interruption.

        The setting is forwarded when a MaxSAT backend is bound. It is only
        meaningful for native incremental solvers that explicitly support it.
        """
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool.")
        self._rebuild_on_interrupt = enabled
        if self._inc_state.ip_solver is not None:
            if not isinstance(self._inc_state.ip_solver, InterruptRecovery):
                raise NotImplementedError(
                    "The selected live solver does not support interruption recovery."
                )
            self._inc_state.ip_solver.set_rebuild_on_interrupt(enabled)

    def set_kmerge_config(self, config: KMergeConfig | None = None, **kwargs) -> None:
        """Replace or update the K-MERGE heuristic configuration."""
        cfg = config or self._kmerge_config
        if kwargs:
            cfg = cfg.with_updates(**kwargs)
        self._kmerge_config = cfg

    def _debug(self, level: int, message: str) -> None:
        if int(self._debug_level) < int(level):
            return
        out = self._debug_stream if self._debug_stream is not None else sys.stderr
        out.write(f"[hermax:model:L{int(level)}] {message}\n")
        try:
            out.flush()
        except (OSError, ValueError):
            pass

    def _clause_to_dimacs_list(self, clause: "Clause | Sequence[int]") -> list[int]:
        if isinstance(clause, Clause):
            return list(clause.dimacs)
        return [int(x) for x in clause]

    @staticmethod
    def _safe_close_backend(obj) -> None:
        """Close for backend objects used during solve/bootstrap."""
        close = getattr(obj, "close", None)
        if close is None:
            return
        try:
            close()
        except Exception:
            pass

    def enable_profiling(self, enabled: bool = True) -> None:
        """Enable or disable structured encoding profiling."""
        self._encoding_profile = EncodingProfile() if enabled else None

    def get_encoding_profile(self) -> EncodingProfile | None:
        """Return the current encoding profile object, if enabled."""
        return self._encoding_profile

    @contextmanager
    def profile_scope(
        self,
        kind: str,
        *,
        label: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ):
        """Profile a block of encoding work as a nested event."""
        profile = self._encoding_profile
        if profile is None:
            yield None
            return
        event = profile.begin(self, kind=kind, label=label, metadata=metadata)
        try:
            yield event
        except Exception:
            profile.end(self, event, success=False)
            raise
        profile.end(self, event, success=True)

    def set_objective_offset_policy(self, *, allow_negative: bool) -> None:
        """Set objective constant-offset policy for this model instance.

        Args:
            allow_negative: If ``False``, objective operations that require a
                negative internal constant offset raise ``ValueError``.

        Notes:
            This policy is used by both flat objectives (``model.obj``) and
            tiered objectives (``model.tier_obj``).
        """
        self._allow_negative_objective_offsets = bool(allow_negative)

    def set_soft_dedup(self, enabled: bool) -> None:
        """Enable or disable duplicate soft-clause accumulation on ``add_soft``."""
        self._soft_dedup_enabled = bool(enabled)

    def set_soft_gcd_optimization(self, enabled: bool) -> None:
        """Enable or disable one-shot MaxSAT soft-weight GCD scaling."""
        self._soft_gcd_opt_enabled = bool(enabled)

    def set_auto_pb_commit(self, enabled: bool) -> None:
        """Enable or disable immediate materialization of deferred PB/Card clauses.

        By default, pure Boolean PB/Card fallback encodings are deferred until
        :meth:`_commit_pb`, export, or solve. Enabling this toggle restores eager
        commit behavior for those deferred constraints while leaving the
        defer-capable architecture in place.
        """
        self._auto_commit_pb = bool(enabled)

    def set_objective_precision(self, *, decimals: int) -> None:
        """Enable/adjust decimal precision for objective-side soft weights.

        Notes:
            Precision applies to objective entry points (``model.obj``,
            ``model.tier_obj``, and ``add_soft`` weight parsing).
            PB/Card arithmetic constraints still require integer coefficients
            and constants.
        """
        if isinstance(decimals, bool) or not isinstance(decimals, int) or int(decimals) < 0:
            raise ValueError("decimals must be a non-negative integer.")
        self._objective_precision_decimals = int(decimals)
        self._objective_precision_scale = 10 ** int(decimals)
        # Re-round existing soft weights from stored raw values.
        for sid in list(self._soft_ids):
            raw = float(self._soft_raw_weight_by_id.get(int(sid), 0.0))
            if raw <= 0:
                continue
            scaled = int(round(raw * self._objective_precision_scale))
            if scaled <= 0:
                raise ValueError("Configured precision rounds an existing positive soft weight to zero.")
            self._set_soft_weight_internal(int(sid), int(scaled), allow_zero=False, allow_when_sat=True)

    def _coerce_soft_weight(self, weight, *, allow_zero: bool = False) -> tuple[int, float]:
        if self._objective_precision_decimals is None:
            if isinstance(weight, int):
                w = int(weight)
            else:
                raise ValueError("weight must be a positive int")
            if allow_zero:
                if w < 0:
                    raise ValueError("Soft weight must be non-negative.")
            else:
                if w <= 0:
                    raise ValueError("weight must be a positive int")
            return w, float(w)

        if not isinstance(weight, (int, float)):
            raise ValueError("Soft weight must be int/float when objective precision is enabled.")
        raw = float(weight)
        if allow_zero:
            if raw < 0:
                raise ValueError("Soft weight must be non-negative.")
        else:
            if raw <= 0:
                raise ValueError("Soft weight must be positive.")
        scaled = int(round(raw * self._objective_precision_scale))
        if allow_zero:
            if scaled < 0:
                raise ValueError("Soft weight rounds below zero for current precision.")
        else:
            if scaled <= 0:
                raise ValueError("Soft weight rounds to zero for current precision.")
        return int(scaled), float(raw)

    def _format_objective_cost(self, scaled_cost: int) -> int | float:
        if self._objective_precision_decimals is None:
            return int(scaled_cost)
        return round(float(scaled_cost) / float(self._objective_precision_scale), int(self._objective_precision_decimals))

    @staticmethod
    def _is_integral_number(x) -> bool:
        if isinstance(x, bool):
            return False
        if isinstance(x, int):
            return True
        if isinstance(x, float):
            return x.is_integer()
        return False

    def _validate_integral_pbexpr(self, expr: PBExpr) -> None:
        for t in expr.terms:
            if not self._is_integral_number(t.coefficient):
                raise ValueError("PB/Card constraints require integer coefficients. Use objective precision for fractional objective weights.")
        if not self._is_integral_number(expr.constant):
            raise ValueError("PB/Card constraints require integer constants. Use objective precision for fractional objective weights.")
        for c, _v in expr.int_terms:
            if not self._is_integral_number(c):
                raise ValueError("PB/Card constraints require integer coefficients. Use objective precision for fractional objective weights.")

    @property
    def obj(self) -> _ObjectiveProxy:
        """Objective proxy for additive and replacement objective operations.

        Notes:
            ``model.obj`` and ``model.tier_obj`` are mutually exclusive.
            Clear one objective mode before activating the other.
        """
        return self._obj_proxy

    @obj.setter
    def obj(self, new_expr):
        """Replace the current objective using expression syntax."""
        # Augmented assignment on attributes may rebind back the same proxy.
        if new_expr is self._obj_proxy:
            return
        self._obj_proxy.replace_with(new_expr)

    @property
    def tier_obj(self) -> _TierObjectiveProxy:
        """Lexicographic objective proxy (tiered optimization).

        Notes:
            ``model.tier_obj`` cannot be used together with flat objective
            operations (``model.obj``/``add_soft``).
        """
        return self._tier_obj_proxy

    def _has_active_flat_objective(self) -> bool:
        return any(int(w) > 0 for w, _ in self._soft)

    def _ensure_no_flat_objective_active(self) -> None:
        if self._has_active_flat_objective():
            raise ValueError("model.obj/add_soft and model.tier_obj are mutually exclusive. Clear model.obj first.")

    def _ensure_no_tier_objective_active(self) -> None:
        if self._tier_obj_proxy.is_active():
            raise ValueError("model.obj/add_soft and model.tier_obj are mutually exclusive. Clear model.tier_obj first.")

    def _reserve_name(self, name: Optional[str]) -> str:
        if name is None:
            while True:
                self._anon_counter += 1
                candidate = f"_v{self._anon_counter}"
                if candidate not in self._registry and candidate not in self._container_names:
                    return candidate
        if name.startswith("__"):
            raise ValueError(f"Identifier '{name}' is reserved for internal model constants.")
        if name in self._registry or name in self._container_names:
            raise ValueError(f"Identifier '{name}' is already registered in this model.")
        return name

    def fresh_internal_bool(self, debug_name: Optional[str] = None) -> Literal:
        """Return a fresh internal helper literal.

        Internal helpers are intentionally not added to the public model
        registry. ``debug_name`` is advisory only and does not affect identity.
        """
        del debug_name
        name = self._reserve_name(None)
        return self._new_literal_pair(name)

    def canonical_internal_bool(self, key: object, debug_name: Optional[str] = None) -> Literal:
        """Return a canonical reusable internal helper literal for ``key``.

        Repeated requests with the same semantic ``key`` return the same
        internal literal. The helper remains hidden from the public registry.
        """
        del debug_name
        cached = self._canonical_internal_lits.get(key)
        if cached is not None:
            return cached
        lit = self.fresh_internal_bool()
        self._canonical_internal_lits[key] = lit
        return lit

    def _reserve_container_name(self, name: str) -> None:
        if name in self._registry or name in self._container_names:
            raise ValueError(f"Identifier '{name}' is already registered in this model.")
        self._container_names.add(name)

    def _new_literal_pair(self, name: str, *, var_id: int | None = None) -> Literal:
        id_ = self._next_id if var_id is None else int(var_id)
        if id_ <= 0:
            raise ValueError("Variable id must be positive.")
        if id_ in self._lits_by_id:
            raise ValueError(f"Variable id {id_} is already allocated.")
        self._next_id = max(self._next_id, id_ + 1)
        pos = Literal(self, id_, name, True)
        neg = Literal(self, id_, name, False)
        pos._link_negation(neg)
        neg._link_negation(pos)
        self._lits_by_id[id_] = pos
        return pos

    def _reserve_literal_ids_up_to(self, var_id: int) -> None:
        if int(var_id) > 0:
            self._next_id = max(self._next_id, int(var_id) + 1)

    def _get_bool_constant_literal(self, value: bool) -> Literal:
        cached = self._const_lits.get(bool(value))
        if cached is not None:
            return cached

        name = "__true" if value else "__false"
        # Internal reserved names bypass public reservation checks.
        if name in self._registry or name in self._container_names:
            # Defensive: if a collision exists something already corrupted the model.
            raise ValueError(f"Identifier '{name}' is already registered in this model.")
        lit = self._new_literal_pair(name)
        self._registry[name] = lit
        self._const_lits[bool(value)] = lit

        # Define the literal's truth value in the hard constraints:
        #   __true  is forced true
        #   __false is forced false
        self._hard.append((self._lit_to_dimacs(lit if value else ~lit),))
        return lit

    def _top_id(self) -> int:
        return self._next_id - 1

    def _lit_to_dimacs(self, lit: Literal) -> int:
        return lit.id if lit.polarity else -lit.id

    def _dimacs_to_lit(self, dim: int) -> Literal:
        if not isinstance(dim, int) or dim == 0:
            raise ValueError("DIMACS literal must be a non-zero int.")
        base = self._get_or_make_aux_literal(abs(int(dim)))
        return base if int(dim) > 0 else ~base

    def _coerce_assumption_literal(self, a) -> int:
        if isinstance(a, bool):
            raise TypeError("Assumptions do not accept bool values; use int/literal/term.")
        if isinstance(a, Literal):
            if a._model is not self:
                raise ValueError("Variables belong to different models.")
            return self._lit_to_dimacs(a)
        if isinstance(a, Term):
            lit = a.literal
            if lit._model is not self:
                raise ValueError("Variables belong to different models.")
            c = int(a.coefficient)
            if c == 1:
                return self._lit_to_dimacs(lit)
            if c == -1:
                return self._lit_to_dimacs(~lit)
            raise TypeError("Assumption Term must be a unit term with coefficient +1 or -1.")
        if isinstance(a, int):
            if a == 0:
                raise ValueError("DIMACS assumption literal cannot be 0.")
            return int(a)
        raise TypeError("Each assumption must be an int, Literal, or unit Term.")

    def _coerce_assumptions(self, assumptions: Optional[Sequence[object]]) -> list[int]:
        if assumptions is None:
            return []
        return [self._coerce_assumption_literal(a) for a in assumptions]

    def _get_or_make_aux_literal(self, var_id: int) -> Literal:
        if var_id <= 0:
            raise ValueError("Variable id must be positive")
        if var_id in self._lits_by_id:
            return self._lits_by_id[var_id]
        self._reserve_literal_ids_up_to(var_id)
        name = self._reserve_name(None)
        return self._new_literal_pair(name, var_id=var_id)

    def _equiv_literals_group(self, a: Literal, b: Literal) -> ClauseGroup:
        """Return a constant-folded literal equivalence ``a <-> b``."""
        true_lit = self._const_lits.get(True)
        false_lit = self._const_lits.get(False)
        if a is b:
            return ClauseGroup(self, [])
        if true_lit is not None and a is true_lit:
            if b is true_lit:
                return ClauseGroup(self, [])
            if false_lit is not None and b is false_lit:
                return ClauseGroup(self, [Clause(self, [])])
            return ClauseGroup(self, [Clause(self, [b])])
        if false_lit is not None and a is false_lit:
            if true_lit is not None and b is true_lit:
                return ClauseGroup(self, [Clause(self, [])])
            if b is false_lit:
                return ClauseGroup(self, [])
            return ClauseGroup(self, [Clause(self, [~b])])
        if true_lit is not None and b is true_lit:
            return ClauseGroup(self, [Clause(self, [a])])
        if false_lit is not None and b is false_lit:
            return ClauseGroup(self, [Clause(self, [~a])])
        return ClauseGroup(self, [Clause(self, [~a, b]), Clause(self, [~b, a])])

    def _cnfplus_to_clausegroup(self, cnf) -> ClauseGroup:
        # PySAT returns CNFPlus; for now we only support the clause list part.
        if not hasattr(cnf, "clauses") or not hasattr(cnf, "nv"):
            raise TypeError("CNF-like object must provide 'clauses' and 'nv'.")
        raw_clauses = cnf.clauses
        max_var = int(cnf.nv or 0)
        if max_var <= 0 and len(raw_clauses) > 0:
            raise ValueError("CNF-like object must provide positive 'nv' when clauses are present.")
        if max_var > 0:
            self._reserve_literal_ids_up_to(max_var)
        if self._debug_level >= self.DEBUG_VERBOSE:
            self._debug(self.DEBUG_VERBOSE, f"cnfplus->clauses count={len(raw_clauses)}")
            for i, c in enumerate(raw_clauses):
                self._debug(self.DEBUG_VERBOSE, f"  clause[{i}]={self._clause_to_dimacs_list(c)}")
        return ClauseGroup._from_dimacs_trusted(self, raw_clauses)

    def _register_literal_definition(self, lit: Literal, group: ClauseGroup) -> None:
        """Register deferred definition clauses for ``lit``.

        Definitions are materialized only when a constraint containing ``lit`` is
        added to the model or exported/solved.
        """
        _ensure_same_model(self, lit, group)
        existing = self._pending_literal_defs.get(lit.id)
        if existing is None:
            self._pending_literal_defs[lit.id] = group
            return
        if existing is group:
            return
        # Merge repeated registrations conservatively (should be rare).
        self._pending_literal_defs[lit.id] = ClauseGroup(self, [*existing, *group])

    def _ensure_literal_def_realized(self, lit: Literal) -> None:
        lit_id = lit.id
        if lit_id in self._realized_literal_defs:
            return
        group = self._pending_literal_defs.get(lit_id)
        if group is None:
            return
        if lit_id in self._realizing_literal_defs:
            return
        self._realizing_literal_defs.add(lit_id)
        try:
            group_id = id(group)
            if group_id in self._realized_definition_group_ids:
                self._realized_literal_defs.add(lit_id)
                return
            self._ensure_deferred_defs_in_group(group)
            self._hard.extend(group)
            self._realized_definition_group_ids.add(group_id)
            self._realized_literal_defs.add(lit_id)
        finally:
            self._realizing_literal_defs.discard(lit_id)

    def _ensure_all_pending_literal_defs_realized(self) -> None:
        if not self._pending_literal_defs:
            return
        for lit_id in list(self._pending_literal_defs):
            lit = self._lits_by_id.get(int(lit_id))
            if lit is not None:
                self._ensure_literal_def_realized(lit)

    def _ensure_deferred_defs_in_group(self, group: ClauseGroup) -> None:
        pending_defs = self._pending_literal_defs
        if not pending_defs:
            return
        realized_defs = self._realized_literal_defs
        lits_by_id = self._lits_by_id
        ensure_realized = self._ensure_literal_def_realized
        pending_contains = pending_defs.__contains__
        realized_contains = realized_defs.__contains__
        get_lit = lits_by_id.get
        for clause in group:
            for dim in clause:
                lit_id = dim if dim > 0 else -dim
                if realized_contains(lit_id) or not pending_contains(lit_id):
                    continue
                lit = get_lit(lit_id)
                if lit is not None:
                    ensure_realized(lit)

    def _register_clausegroup_structure(self, group: ClauseGroup) -> None:
        for amo_group in group._amo_groups:
            self._register_amo_group(amo_group, exactly_one=False)
        for eo_group in group._eo_groups:
            self._register_amo_group(eo_group, exactly_one=True)

    def bool(self, name: Optional[str] = None) -> Literal:
        """Create a Boolean variable and return its positive literal.

        Args:
            name: Optional user-facing identifier. If omitted, an anonymous
                variable name is generated.
        """
        final_name = self._reserve_name(name)
        lit = self._new_literal_pair(final_name)
        self._registry[final_name] = lit
        return lit

    def enum(self, name: str, choices: Sequence[str], nullable: bool = False) -> EnumVar:
        """Create an enum variable with the given choices.

        Non-nullable enums are exactly-one; nullable enums are at-most-one and
        decode to ``None`` when no choice is selected.
        """
        self._reserve_container_name(name)
        return EnumVar(self, name, choices=choices, nullable=nullable)

    def int(self, name: str, lb: int, ub: int) -> IntVar:
        """Create a ladder-encoded bounded integer variable over domain ``[lb, ub]``."""
        self._reserve_container_name(name)
        return IntVar(self, name, lb=lb, ub=ub)

    def int_set(
        self,
        name: str,
        *,
        lb: Optional[int] = None,
        ub: Optional[int] = None,
        values: Optional[Sequence[int]] = None,
    ) -> IntSetVar:
        """Create an integer set variable over a finite universe.

        Exactly one domain specification must be provided:
            * ``lb``/``ub`` inclusive range
            * explicit ``values`` sequence
        """
        range_spec = lb is not None or ub is not None
        values_spec = values is not None
        if range_spec == values_spec:
            raise ValueError("int_set() expects exactly one domain specification: (lb, ub) or values.")

        if values_spec:
            if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
                raise TypeError("int_set(values=...) expects a sequence of integers.")
            universe: list[int] = []
            seen: set[int] = set()
            for v in values:
                if isinstance(v, bool) or not isinstance(v, int):
                    raise TypeError("int_set(values=...) expects integers.")
                iv = int(v)
                if iv in seen:
                    continue
                seen.add(iv)
                universe.append(iv)
            universe.sort()
        else:
            if isinstance(lb, bool) or not isinstance(lb, int):
                raise TypeError("int_set(lb=..., ub=...) expects integer bounds.")
            if isinstance(ub, bool) or not isinstance(ub, int):
                raise TypeError("int_set(lb=..., ub=...) expects integer bounds.")
            if int(lb) > int(ub):
                raise ValueError("int_set() requires lb <= ub.")
            universe = list(range(int(lb), int(ub) + 1))

        self._reserve_container_name(name)
        return IntSetVar(self, name, universe)

    def floor_div(self, x: IntVar | _LazyIntExpr, divisor: int, name: Optional[str] = None) -> IntVar:
        """Materialize a quotient integer ``x // divisor`` using ladder threshold ties."""
        if isinstance(x, _LazyIntExpr):
            x = x._realize()
        _ensure_same_model(self, x)
        if isinstance(divisor, bool):
            raise ValueError("Divisor must be strictly positive.")
        if not isinstance(divisor, int):
            raise TypeError("Divisor must be an integer.")
        if divisor <= 0:
            raise ValueError("Divisor must be strictly positive.")

        out_lb = x.lb // divisor
        out_ub = x.ub // divisor
        out_name = self._reserve_name(None) if name is None else name
        self._reserve_container_name(out_name)
        out = IntVar(self, out_name, lb=out_lb, ub=out_ub)

        for q_val in range(out.lb + 1, out.ub + 1):
            q_lit = out.__ge__(q_val)
            x_lit = x.__ge__(q_val * divisor)
            group = self._equiv_literals_group(q_lit, x_lit)
            if not group.is_empty():
                self._register_literal_definition(q_lit, group)
        return out

    def scale(self, x: IntVar | _LazyIntExpr, factor: int, name: Optional[str] = None) -> IntVar:
        """Materialize a scaled integer ``x * factor`` using ladder threshold ties."""
        if isinstance(x, _LazyIntExpr):
            x = x._realize()
        _ensure_same_model(self, x)
        if isinstance(factor, bool):
            raise ValueError("Scale factor must be strictly positive.")
        if not isinstance(factor, int):
            raise TypeError("Scale factor must be an integer.")
        if factor <= 0:
            raise ValueError("Scale factor must be strictly positive.")

        out_lb = x.lb * factor
        out_ub = x.ub * factor
        out_name = self._reserve_name(None) if name is None else name
        self._reserve_container_name(out_name)
        out = IntVar(self, out_name, lb=out_lb, ub=out_ub)

        def ceil_div_pos(n: int, d: int) -> int:
            return -((-n) // d)

        for k in range(x.lb + 1, x.ub + 1):
            xk = x.__ge__(k)

            # Upward: x >= k  =>  out >= factor*k
            up_q = factor * k
            if out.lb < up_q <= out.ub:
                out_up = out.__ge__(up_q)
                self._register_literal_definition(
                    out_up,
                    ClauseGroup(self, [Clause(self, [~xk, out_up])])
                )

            # Gap-forbidding: out >= factor*(k-1)+1  =>  x >= k
            gap_q = factor * (k - 1) + 1
            if out.lb < gap_q <= out.ub:
                out_gap = out.__ge__(gap_q)
                self._register_literal_definition(
                    out_gap,
                    ClauseGroup(self, [Clause(self, [~out_gap, xk])])
                )
        return out

    def _build_int_aggregate_extreme(self, items: Sequence[IntVar], kind: str, name: Optional[str] = None) -> IntVar:
        if not items:
            raise ValueError(f"Cannot compute {kind} of an empty IntVector.")
        if len(items) == 1:
            return items[0]
        _ensure_same_model(self, *items)

        assert kind in {"max", "min"}, f"Unknown extreme kind {kind!r}"
        if kind == "max":
            out_lb = max(x.lb for x in items)
            out_ub = max(x.ub for x in items)
        else:
            out_lb = min(x.lb for x in items)
            out_ub = min(x.ub for x in items)
        out_name = self._reserve_name(None) if name is None else name
        z = self.int(out_name, lb=out_lb, ub=out_ub)
        m = self
        for k in range(z.lb + 1, z.ub + 1):
            zk = z.__ge__(k)
            nonconst_srcs: list[Literal] = []
            saw_true = False
            saw_false = False
            for x in items:
                if k <= x.lb:
                    saw_true = True
                    continue
                if k > x.ub:
                    saw_false = True
                    continue
                nonconst_srcs.append(x.__ge__(k))
            if kind == "max":
                if saw_true:
                    m._hard.append(Clause(m, [zk]))
                    continue
                if not nonconst_srcs:
                    m._hard.append(Clause(m, [~zk]))
                    continue
                if len(nonconst_srcs) == 1:
                    s = nonconst_srcs[0]
                    m._hard.append(Clause(m, [~s, zk]))
                    m._hard.append(Clause(m, [~zk, s]))
                    continue
                for s in nonconst_srcs:
                    m._hard.append(Clause(m, [~s, zk]))
                m._hard.append(Clause(m, [~zk, *nonconst_srcs]))
            else:
                if saw_false:
                    m._hard.append(Clause(m, [~zk]))
                    continue
                if not nonconst_srcs:
                    m._hard.append(Clause(m, [zk]))
                    continue
                if len(nonconst_srcs) == 1:
                    s = nonconst_srcs[0]
                    m._hard.append(Clause(m, [~s, zk]))
                    m._hard.append(Clause(m, [~zk, s]))
                    continue
                for s in nonconst_srcs:
                    m._hard.append(Clause(m, [~zk, s]))
                m._hard.append(Clause(m, [zk, *(~s for s in nonconst_srcs)]))
        return z

    def _build_int_aggregate_bound(self, items: Sequence[IntVar], kind: str, name: Optional[str] = None) -> IntVar:
        if not items:
            raise ValueError(f"Cannot compute {kind} of an empty IntVector.")
        if len(items) == 1:
            return items[0]
        _ensure_same_model(self, *items)
        assert kind in {"upper_bound", "lower_bound"}, f"Unknown one-sided bound kind {kind!r}"
        if kind == "upper_bound":
            out_lb = max(x.lb for x in items)
            out_ub = max(x.ub for x in items)
        else:
            out_lb = min(x.lb for x in items)
            out_ub = min(x.ub for x in items)
        out_name = self._reserve_name(None) if name is None else name
        z = self.int(out_name, lb=out_lb, ub=out_ub)
        m = self
        for k in range(z.lb + 1, z.ub + 1):
            zk = z.__ge__(k)
            if kind == "upper_bound":
                for x in items:
                    if k <= x.lb:
                        m._hard.append(Clause(m, [zk]))
                        break
                    if k > x.ub:
                        continue
                    m._hard.append(Clause(m, [~x.__ge__(k), zk]))
            else:
                active = False
                forced_false = False
                for x in items:
                    if k > x.ub:
                        forced_false = True
                        break
                    if k <= x.lb:
                        continue
                    active = True
                    m._hard.append(Clause(m, [~zk, x.__ge__(k)]))
                if forced_false:
                    m._hard.append(Clause(m, [~zk]))
                elif not active:
                    pass
        return z

    def max(self, vec_or_items, name: Optional[str] = None) -> IntVar:
        """Materialize exact maximum over an IntVector or IntVar sequence."""
        items = tuple(vec_or_items._items) if isinstance(vec_or_items, IntVector) else tuple(vec_or_items)
        return self._build_int_aggregate_extreme(items, "max", name=name)

    def min(self, vec_or_items, name: Optional[str] = None) -> IntVar:
        """Materialize exact minimum over an IntVector or IntVar sequence."""
        items = tuple(vec_or_items._items) if isinstance(vec_or_items, IntVector) else tuple(vec_or_items)
        return self._build_int_aggregate_extreme(items, "min", name=name)

    def upper_bound(self, vec_or_items, name: Optional[str] = None) -> IntVar:
        """Materialize one-sided aggregate constrained to be >= all vector items."""
        items = tuple(vec_or_items._items) if isinstance(vec_or_items, IntVector) else tuple(vec_or_items)
        return self._build_int_aggregate_bound(items, "upper_bound", name=name)

    def lower_bound(self, vec_or_items, name: Optional[str] = None) -> IntVar:
        """Materialize one-sided aggregate constrained to be <= all vector items."""
        items = tuple(vec_or_items._items) if isinstance(vec_or_items, IntVector) else tuple(vec_or_items)
        return self._build_int_aggregate_bound(items, "lower_bound", name=name)

    def bool_vector(self, name: str, length: int) -> BoolVector:
        """Create a vector of Boolean literals."""
        self._reserve_container_name(name)
        return BoolVector(self, name, [self.bool(f"{name}[{i}]") for i in range(length)])

    def int_vector(self, name: str, length: int, lb: int, ub: int) -> IntVector:
        """Create a vector of bounded integers sharing the same domain."""
        self._reserve_container_name(name)
        return IntVector(self, name, [self.int(f"{name}[{i}]", lb=lb, ub=ub) for i in range(length)])

    def enum_vector(self, name: str, length: int, choices: Sequence[str], nullable: bool = False) -> EnumVector:
        """Create a vector of enum variables."""
        self._reserve_container_name(name)
        return EnumVector(self, name, [self.enum(f"{name}[{i}]", choices=choices, nullable=nullable) for i in range(length)])

    def int_set_vector(
        self,
        name: str,
        length: int,
        *,
        lb: Optional[int] = None,
        ub: Optional[int] = None,
        values: Optional[Sequence[int]] = None,
    ) -> IntSetVector:
        """Create a vector of integer set variables with shared universe specification."""
        self._reserve_container_name(name)
        return IntSetVector(
            self,
            name,
            [
                self.int_set(f"{name}[{i}]", lb=lb, ub=ub, values=values)
                for i in range(length)
            ],
        )

    def bool_dict(self, name: str, keys: Sequence) -> BoolDict:
        """Create a keyed dictionary of Boolean literals."""
        self._reserve_container_name(name)
        return BoolDict(self, name, {k: self.bool(f"{name}[{k!r}]") for k in keys})

    def int_dict(self, name: str, keys: Sequence, lb: int, ub: int) -> IntDict:
        """Create a keyed dictionary of bounded integers."""
        self._reserve_container_name(name)
        return IntDict(self, name, {k: self.int(f"{name}[{k!r}]", lb=lb, ub=ub) for k in keys})

    def enum_dict(self, name: str, keys: Sequence, choices: Sequence[str], nullable: bool = False) -> EnumDict:
        """Create a keyed dictionary of enum variables."""
        self._reserve_container_name(name)
        return EnumDict(
            self,
            name,
            {k: self.enum(f"{name}[{k!r}]", choices=choices, nullable=nullable) for k in keys},
        )

    def int_set_dict(
        self,
        name: str,
        keys: Sequence,
        *,
        lb: Optional[int] = None,
        ub: Optional[int] = None,
        values: Optional[Sequence[int]] = None,
    ) -> IntSetDict:
        """Create a keyed dictionary of integer set variables."""
        self._reserve_container_name(name)
        return IntSetDict(
            self,
            name,
            {
                k: self.int_set(f"{name}[{k!r}]", lb=lb, ub=ub, values=values)
                for k in keys
            },
        )

    def int_matrix(self, name: str, rows: int, cols: int, lb: int, ub: int) -> IntMatrix:
        """Create an integer matrix."""
        self._reserve_container_name(name)
        return IntMatrix(self, name, rows=rows, cols=cols, lb=lb, ub=ub)

    def interval(self, name: str, *, start: int, duration: int, end: int) -> IntervalVar:
        """Create a fixed-duration interval with inclusive latest-end horizon.

        Args:
            name: User-facing interval identifier.
            start: Earliest start time (inclusive).
            duration: Positive fixed duration.
            end: Latest end time (inclusive).
        """
        self._reserve_container_name(name)
        return IntervalVar(self, name, start=start, duration=duration, end=end)

    def sum_var(self, items: Sequence[IntVar], name: Optional[str] = None) -> IntVar:
        """Materialize the sum of integer variables as a single IntVar.

        Uses a binary-tree reduction: repeatedly merge the two
        narrowest current partial sums. This keeps intermediate
        widths smaller than a left-fold or,
        while avoiding the ``O(N)`` linear chain.
        """
        items_list = list(items)
        if not items_list:
            raise ValueError("sum_var() cannot sum an empty sequence.")
        _ensure_same_model(self, *items_list)
        if any(not isinstance(x, IntVar) for x in items_list):
            raise TypeError("sum_var() expects IntVar items.")
        if len(items_list) == 1:
            return items_list[0]

        from heapq import heapify, heappop, heappush

        def _ladder_width(v: IntVar) -> int:
            return len(v._threshold_lits)

        heap: list[tuple[int, int, IntVar]] = [
            (_ladder_width(v), idx, v) for idx, v in enumerate(items_list)
        ]
        heapify(heap)
        step = 0
        next_idx = len(heap)
        while len(heap) > 1:
            _wa, _ia, a = heappop(heap)
            _wb, _ib, b = heappop(heap)
            step_name: Optional[str]
            if name is not None:
                step_name = f"{name}_step{step}"
            else:
                step_name = None
            merged_lb = a.lb + b.lb
            merged_ub = a.ub + b.ub
            n = self._reserve_name(step_name)
            merged = self.int(n, lb=merged_lb, ub=merged_ub)
            self &= (merged == (a + b))
            heappush(heap, (_ladder_width(merged), next_idx, merged))
            next_idx += 1
            step += 1

        result = heap[0][2]
        return result

    def cumulative(
        self,
        starts: Sequence[IntVar],
        durations: Sequence[int],
        demands: Sequence[int],
        capacity: int,
        *,
        backend: str = "auto",
    ) -> None:
        """Add a fixed-duration cumulative resource constraint.

        This is an interval scheduling primitive over explicit start
        variables and constant durations/demands.

        Args:
            backend: Encoding strategy for capacity cuts.

                ``"time"`` loops over every integer time tick in the horizon
                and adds a PB capacity constraint at each. Formula size is
                ``O(N × H)`` where ``H`` is the horizon width. Efficient when
                task count ``N`` is very large relative to ``H``.

                ``"task"`` creates ``O(N²)`` pairwise precedence indicator
                variables (one per conflicting pair), then conditionally adds
                capacity cuts **only** at the start-times of active tasks.
                Formula size is ``O(N² × N)``. Efficient when ``H`` is large
                and N is small.

                ``"auto"`` (default) picks ``"task"`` when ``N² < H``,
                otherwise ``"time"``.
        """
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise TypeError("cumulative() expects an integer capacity.")
        if capacity < 0:
            raise ValueError("cumulative() expects nonnegative capacity.")
        if backend not in ("auto", "time", "task"):
            raise ValueError(f"cumulative() backend must be 'auto', 'time', or 'task'; got {backend!r}")

        starts_list = list(starts)
        durs_list = list(durations)
        demands_list = list(demands)
        if not (len(starts_list) == len(durs_list) == len(demands_list)):
            raise ValueError("cumulative() expects starts, durations, and demands of equal length.")
        if not starts_list:
            return
        _ensure_same_model(self, *starts_list)
        if any(not isinstance(s, IntVar) for s in starts_list):
            raise TypeError("cumulative() expects IntVar starts.")
        if any(isinstance(d, bool) or not isinstance(d, int) for d in durs_list):
            raise TypeError("cumulative() expects integer durations.")
        if any(isinstance(r, bool) or not isinstance(r, int) for r in demands_list):
            raise TypeError("cumulative() expects integer demands.")
        if any(d < 0 for d in durs_list):
            raise ValueError("cumulative() does not support negative durations.")
        if any(r < 0 for r in demands_list):
            raise ValueError("cumulative() does not support negative demands.")

        model = self
        true_lit = self._get_bool_constant_literal(True)
        false_lit = self._get_bool_constant_literal(False)

        def _same_lit(a: Literal, b: Literal) -> bool:
            return a.id == b.id and bool(a.polarity) == bool(b.polarity)

        def _and_lits(a: Literal, b: Literal) -> Literal:
            if _same_lit(a, false_lit) or _same_lit(b, false_lit):
                return false_lit
            if _same_lit(a, true_lit):
                return b
            if _same_lit(b, true_lit):
                return a
            if _same_lit(a, b):
                return a
            if a.id == b.id and bool(a.polarity) != bool(b.polarity):
                return false_lit
            out = model.bool()
            model.__iand__(ClauseGroup(
                model,
                [
                    Clause(model, [~out, a]),
                    Clause(model, [~out, b]),
                    Clause(model, [~a, ~b, out]),
                ],
            ))
            return out

        def _order_indicator(left: IntVar, shift: int, right: IntVar) -> Literal:
            rel = left._relop_intvar(right, "<=", shift)
            assert isinstance(rel, IntRelation)
            if len(rel) == 0:
                return true_lit
            if any(len(clause) == 0 for clause in rel):
                return false_lit
            out = model.bool()
            model.__iand__(rel.only_if(out))
            return out

        active_jobs = [(s, int(d), int(r)) for s, d, r in zip(starts_list, durs_list, demands_list) if d > 0 and r > 0]
        if not active_jobs:
            return
        if capacity == 0:
            self &= self._get_bool_constant_literal(False)
            return

        # --- Mandatory conflict disjunctions (shared by all backends) ---
        for i, (si, di, ri) in enumerate(active_jobs):
            for sj, dj, rj in active_jobs[i + 1:]:
                if ri + rj > capacity:
                    left = _order_indicator(si, di, sj)
                    right = _order_indicator(sj, dj, si)
                    self &= Clause(self, [left, right])

        min_t = min(s.lb for s, _, _ in active_jobs)
        max_t_exclusive = max(s.ub + d + 1 for s, d, _ in active_jobs)
        horizon = max_t_exclusive - min_t
        n = len(active_jobs)
        domain_work = sum((s.ub - s.lb + 1) for s, _, _ in active_jobs)

        if backend == "auto":
            backend = "task" if domain_work < horizon else "time"

        if backend == "time":
            # Time-indexed: one PB cut per tick.  O(N × H) constraints.
            for t in range(min_t, max_t_exclusive):
                load_expr = 0
                for start, dur, demand in active_jobs:
                    started = start <= t
                    not_ended = start >= (t - dur + 1)
                    assert isinstance(started, Literal)
                    assert isinstance(not_ended, Literal)
                    active = _and_lits(started, not_ended)
                    if _same_lit(active, false_lit):
                        continue
                    if _same_lit(active, true_lit):
                        load_expr = load_expr + demand
                    else:
                        load_expr = load_expr + demand * active
                self &= (load_expr <= capacity)

        else:  # "task"
            # Task-event-based: capacity cuts only at the possible start times
            # of each job (the only moments when load can increase).
            # For each job i starting at time t in its domain, we check the
            # total demand of all other jobs j that *must* overlap with i at t.
            # We enforce: sum(demand_j * overlap_ij(t)) <= capacity - demand_i
            # only when job i is actually active (start_i == t).
            for i, (si, di, ri) in enumerate(active_jobs):
                # Iterate only over each integer in si's domain as a potential
                # observation point.
                for t in range(si.lb, si.ub + 1):
                    # Indicator: si == t  (exact start of task i)
                    eq_i = (si == t)
                    load_expr = 0
                    for j, (sj, dj, rj) in enumerate(active_jobs):
                        if j == i:
                            continue
                        # Job j overlaps with i starting at t iff:
                        #   sj <= t  (j has started)  AND  sj >= t - dj + 1  (j hasn't ended)
                        started_j = sj <= t
                        not_ended_j = sj >= (t - dj + 1)
                        assert isinstance(started_j, Literal)
                        assert isinstance(not_ended_j, Literal)
                        overlap_j = _and_lits(started_j, not_ended_j)
                        if _same_lit(overlap_j, false_lit):
                            continue
                        if _same_lit(overlap_j, true_lit):
                            load_expr = load_expr + rj
                        else:
                            load_expr = load_expr + rj * overlap_j
                    # Gate the capacity cut on eq_i being true.
                    cap_cut = (load_expr <= (capacity - ri))
                    gated = self._as_clausegroup(cap_cut).only_if(eq_i)
                    self &= gated


    def bool_matrix(self, name: str, rows: int, cols: int) -> BoolMatrix:
        """Create a Boolean matrix."""
        self._reserve_container_name(name)
        return BoolMatrix(self, name, rows=rows, cols=cols)

    def enum_matrix(self, name: str, rows: int, cols: int, choices: Sequence[str], nullable: bool = False) -> EnumMatrix:
        """Create an enum matrix."""
        self._reserve_container_name(name)
        return EnumMatrix(self, name, rows=rows, cols=cols, choices=choices, nullable=nullable)

    def vector(self, items: Sequence, name: str = "_view"):
        """Build a typed vector view from a homogeneous sequence of model objects.

        This is useful for arbitrary subsets (for example, Sudoku subgrids) that
        are not contiguous rows/columns.
        """
        items_list = list(items)
        if not items_list:
            raise ValueError("Model.vector() requires at least one item")
        model = _ensure_same_model(*items_list)
        if model is not self:
            raise ValueError("Vector items must belong to this model.")
        first = items_list[0]
        if all(isinstance(x, Literal) for x in items_list):
            return BoolVector(self, name, items_list)
        if all(isinstance(x, IntVar) for x in items_list):
            return IntVector(self, name, items_list)
        if all(isinstance(x, EnumVar) for x in items_list):
            return EnumVector(self, name, items_list)
        if all(isinstance(x, IntSetVar) for x in items_list):
            return IntSetVector(self, name, items_list)
        raise TypeError("Model.vector() requires homogeneous items of type Literal, IntVar, EnumVar, or IntSetVar.")

    def _as_clausegroup(self, constraint) -> ClauseGroup:
        if isinstance(constraint, bool):
            lit = self._get_bool_constant_literal(constraint)
            return ClauseGroup(self, [Clause(self, [lit])])
        if isinstance(constraint, PBConstraint):
            _ensure_same_model(self, constraint)
            return constraint.clauses()
        if isinstance(constraint, ClauseGroup):
            _ensure_same_model(self, constraint)
            return constraint
        if isinstance(constraint, Clause):
            _ensure_same_model(self, constraint)
            return ClauseGroup(self, [constraint])
        if isinstance(constraint, Literal):
            _ensure_same_model(self, constraint)
            return ClauseGroup(self, [Clause(self, [constraint])])
        raise TypeError("Expected Literal, Clause, or ClauseGroup")

    def _append_soft_entry(
        self,
        weight: int,
        clause: Clause | Sequence[int],
        group_id: Optional[int] = None,
        *,
        raw_weight: Optional[float] = None,
    ) -> int:
        if isinstance(clause, Clause):
            clause_dims = tuple(int(x) for x in clause.dimacs if int(x) != 0)
        else:
            clause_dims = tuple(int(x) for x in clause if int(x) != 0)
        idx = len(self._soft)
        self._soft.append((int(weight), clause_dims))
        sid = self._next_soft_id
        self._next_soft_id += 1
        self._soft_ids.append(sid)
        self._soft_id_to_index[sid] = idx
        self._soft_raw_weight_by_id[sid] = float(int(weight) if raw_weight is None else raw_weight)
        if group_id is not None:
            gid = int(group_id)
            self._soft_group_to_ids.setdefault(gid, []).append(sid)
            self._soft_id_to_group[sid] = gid
        return sid

    def _set_soft_weight_internal(
        self,
        sid: int,
        new_weight: int,
        *,
        allow_zero: bool = False,
        allow_when_sat: bool = False,
    ) -> None:
        sid = int(sid)
        if sid not in self._soft_id_to_index:
            raise KeyError(f"Unknown soft id {sid!r}")
        if isinstance(new_weight, bool) or not isinstance(new_weight, int):
            raise ValueError("Soft weight must be an integer.")
        if allow_zero:
            if int(new_weight) < 0:
                raise ValueError("Soft weight must be non-negative.")
        else:
            if int(new_weight) <= 0:
                raise ValueError("Soft weight must be a positive integer.")
        idx = self._soft_id_to_index[sid]
        old_w, clause = self._soft[idx]
        self._soft[idx] = (int(new_weight), clause)
        if self._debug_level >= self.DEBUG_DELTA:
            self._debug(
                self.DEBUG_DELTA,
                f"update_soft sid={sid} old={int(old_w)} new={int(new_weight)} cl={self._clause_to_dimacs_list(clause)}",
            )
        self._inc_state.update_soft_weight(
            int(sid),
            int(new_weight),
            allow_zero=bool(allow_zero),
            allow_when_sat=bool(allow_when_sat),
        )

    def close_incremental(self) -> None:
        """Close any bound incremental backend for this model."""
        self._inc_state.close()

    def __iand__(self, constraint):
        hard0 = len(self._hard)
        soft0 = len(self._soft)
        scope_kind = "add_hard_pb" if isinstance(constraint, PBConstraint) else "add_hard"
        with self.profile_scope(scope_kind):
            if isinstance(constraint, PBConstraint):
                self._maybe_register_pb_cardinality_structure(constraint)
                compiled = self._prepare_pb_constraint(constraint)
                if isinstance(compiled, PBConstraint):
                    self._defer_pb_constraint(compiled)
                    if self._debug_level >= self.DEBUG_DELTA:
                        self._debug(self.DEBUG_DELTA, "defer_hard_pb count=1")
                    if self._auto_commit_pb:
                        self._commit_pb()
                    return self
                group = compiled
                self._ensure_deferred_defs_in_group(group)
                self._register_clausegroup_structure(group)
                self._hard.extend(group)
                if self._debug_level >= self.DEBUG_DELTA:
                    self._debug(self.DEBUG_DELTA, f"add_hard count={len(group)}")
                    if self._debug_level >= self.DEBUG_VERBOSE:
                        for i, c in enumerate(group):
                            self._debug(self.DEBUG_VERBOSE, f"  hard[{i}]={self._clause_to_dimacs_list(c)}")
                self._inc_state.route_deltas(hard0, soft0)
                return self
            group = self._as_clausegroup(constraint)
            self._ensure_deferred_defs_in_group(group)
            self._register_clausegroup_structure(group)
            self._hard.extend(group)
            if self._debug_level >= self.DEBUG_DELTA:
                self._debug(self.DEBUG_DELTA, f"add_hard count={len(group)}")
                if self._debug_level >= self.DEBUG_VERBOSE:
                    for i, c in enumerate(group):
                        self._debug(self.DEBUG_VERBOSE, f"  hard[{i}]={self._clause_to_dimacs_list(c)}")
            self._inc_state.route_deltas(hard0, soft0)
            return self

    def _add_soft(self, weight: int, constraint, *, dedup: bool = False, raw_weight: Optional[float] = None):
        hard0 = len(self._hard)
        soft0 = len(self._soft)
        group_id = self._next_soft_group_id
        self._next_soft_group_id += 1
        self._soft_group_to_ids[group_id] = []
        sids: list[int] = []

        def _done():
            if self._debug_level >= self.DEBUG_DELTA:
                hard_delta = len(self._hard) - hard0
                soft_delta = len(self._soft) - soft0
                self._debug(self.DEBUG_DELTA, f"add_soft hard_delta={hard_delta} soft_delta={soft_delta}")
                if self._debug_level >= self.DEBUG_VERBOSE:
                    for i, c in enumerate(self._hard[hard0:]):
                        self._debug(self.DEBUG_VERBOSE, f"  hard+[{i}]={self._clause_to_dimacs_list(c)}")
                    for i, (w, c) in enumerate(self._soft[soft0:]):
                        self._debug(
                            self.DEBUG_VERBOSE,
                            f"  soft+[{i}] w={int(w)} cl={self._clause_to_dimacs_list(c)}",
                        )
            self._inc_state.route_deltas(hard0, soft0)
            return sids

        def _soft_clause_signature(clause: Sequence[int]) -> tuple[int, ...]:
            return tuple(sorted(set(int(x) for x in clause)))

        def _find_soft_sid_for_clause(clause: Sequence[int]) -> int | None:
            sig = _soft_clause_signature(clause)
            for i, (_w, c) in enumerate(self._soft):
                if _soft_clause_signature(c) == sig:
                    return int(self._soft_ids[i])
            return None

        def _append_or_merge_soft(
            weight_i: int,
            clause_i: Sequence[int],
            group_id_i: Optional[int],
            raw_weight_i: Optional[float] = None,
        ) -> int:
            if not dedup:
                return self._append_soft_entry(weight_i, clause_i, group_id=group_id_i, raw_weight=raw_weight_i)
            sid_existing = _find_soft_sid_for_clause(clause_i)
            if sid_existing is None:
                return self._append_soft_entry(weight_i, clause_i, group_id=group_id_i, raw_weight=raw_weight_i)
            # Accumulate onto existing soft clause.
            idx_existing = self._soft_id_to_index[sid_existing]
            old_w, _old_clause = self._soft[idx_existing]
            old_raw = float(self._soft_raw_weight_by_id.get(int(sid_existing), float(int(old_w))))
            self._set_soft_weight_internal(
                sid_existing,
                int(old_w) + int(weight_i),
                allow_zero=False,
                allow_when_sat=True,
            )
            self._soft_raw_weight_by_id[int(sid_existing)] = float(old_raw + float(weight_i if raw_weight_i is None else raw_weight_i))
            # Keep per-group membership for SoftRef handles.
            if group_id_i is not None:
                gid = int(group_id_i)
                ids = self._soft_group_to_ids.setdefault(gid, [])
                if sid_existing not in ids:
                    ids.append(sid_existing)
            return sid_existing

        if isinstance(constraint, _LazyIntExpr):
            constraint = constraint._realize()

        if isinstance(constraint, IntVar):
            _ensure_same_model(self, constraint)
            if constraint.lb < 0:
                raise ValueError(
                    "obj[weight] += IntVar currently requires IntVar.lb >= 0 "
                    "(negative objective offsets are temporarily disallowed)."
                )
            # Minimize the actual integer value:
            #   x = lb + sum(threshold_bits)
            # Each threshold bit contributes +1 when true, so add soft (~t) with
            # the same weight to penalize t=True. The constant lb * weight is
            # tracked separately as an objective offset.
            self._objective_constant += weight * constraint.lb
            for t in constraint._threshold_lits:
                sid = _append_or_merge_soft(weight, (self._lit_to_dimacs(~t),), group_id, raw_weight)
                sids.append(sid)
            return group_id, _done()

        if isinstance(constraint, PBExpr):
            if constraint._model is not None and constraint._model is not self:
                raise ValueError("Variables belong to different models.")
            expr = constraint._realize_int_terms(self)
            # Direct objective lowering for linear PB expressions:
            #   c * lit  -> soft unit on (~lit) with weight c        (c > 0)
            #  -c * lit  -> soft unit on ( lit) with weight -c and
            #               objective constant offset -= c
            # This avoids proxy IntVars / equality bindings for piecewise and
            # other PB-valued costs.
            self._objective_constant += weight * int(expr.constant)
            for t in expr.terms:
                coeff = int(t.coefficient)
                if coeff == 0:
                    continue
                if coeff > 0:
                    lit = ~t.literal
                    soft_w = weight * coeff
                else:
                    lit = t.literal
                    soft_w = weight * (-coeff)
                    self._objective_constant -= weight * (-coeff)
                self._ensure_literal_def_realized(lit)
                rw = None if raw_weight is None else float(raw_weight) * (float(soft_w) / float(weight))
                sid = _append_or_merge_soft(soft_w, (self._lit_to_dimacs(lit),), group_id, rw)
                sids.append(sid)
            return group_id, _done()

        def _add_soft_group_targeted(group: ClauseGroup) -> None:
            if group.is_empty():
                return
            c0 = group.single_clause_or_none()
            if c0 is not None:
                self._ensure_deferred_defs_in_group(group)
                sid = _append_or_merge_soft(weight, c0, group_id, raw_weight)
                sids.append(sid)
                return
            # One weighted penalty + gated hard network (targeted relaxation).
            r = self.bool()  # hidden relaxation literal (anonymous)
            sid = _append_or_merge_soft(weight, (self._lit_to_dimacs(~r),), group_id, raw_weight)
            sids.append(sid)
            gated = group.only_if(~r)
            self._ensure_deferred_defs_in_group(gated)
            self._hard.extend(gated)

        # Targeted relaxation for multi-clause structures (including PBConstraint):
        # add one weighted penalty literal and gate the internal network hard.
        if isinstance(constraint, PBConstraint):
            prepared = self._prepare_pb_constraint(constraint)
            if isinstance(prepared, ClauseGroup):
                _add_soft_group_targeted(prepared)
                return group_id, _done()
            r = self.bool()  # hidden relaxation literal (anonymous)
            sid = _append_or_merge_soft(weight, (self._lit_to_dimacs(~r),), group_id, raw_weight)
            sids.append(sid)
            self._defer_pb_constraint(prepared.only_if(~r))
            if self._auto_commit_pb:
                self._commit_pb(route=False)
            return group_id, _done()

        if isinstance(constraint, ClauseGroup):
            _ensure_same_model(self, constraint)
            _add_soft_group_targeted(constraint)
            return group_id, _done()

        group = self._as_clausegroup(constraint)
        self._ensure_deferred_defs_in_group(group)
        for c in group:
            sid = _append_or_merge_soft(weight, c, group_id, raw_weight)
            sids.append(sid)
        return group_id, _done()

    def add_soft(self, constraint, weight: int):
        """Compatibility alias for :meth:`Model.obj.add_soft`."""
        return self.obj.add_soft(constraint, weight)

    def update_soft_weight(self, target, new_weight: int) -> None:
        """Compatibility alias for :meth:`Model.obj.update_soft`."""
        self.obj.update_soft(target, new_weight)

    def _compile_pb_compare(self, lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup:
        with self.profile_scope("compile_pb_compare", metadata={"op": op}):
            _ensure_same_model(self, lhs, rhs)
            lhs_r = lhs._realize_int_terms(self)
            rhs_r = rhs._realize_int_terms(self)
            self._validate_integral_pbexpr(lhs_r)
            self._validate_integral_pbexpr(rhs_r)
            if op == "!=":
                # Encode A != B as (A < B) OR (A > B) via a branch selector.
                sel = self.bool()
                g_lt = self._compile_pb_compare(lhs_r, "<", rhs_r).only_if(sel)
                g_gt = self._compile_pb_compare(lhs_r, ">", rhs_r).only_if(~sel)
                return g_lt & g_gt
            pairs, const = _EncoderDispatch._normalize_pb(lhs_r, rhs_r)
            cmp_op, bound = _EncoderDispatch._bound_from_zero_compare(op, const)
            if self._debug_level >= self.DEBUG_COMPILE:
                terms = ", ".join(f"{int(w)}*{int(self._lit_to_dimacs(l))}" for w, l in pairs)
                self._debug(
                    self.DEBUG_COMPILE,
                    f"pb_normalize raw_op={op} -> op={cmp_op} bound={int(bound)} terms=[{terms}]",
                )
            key = _canonical_pb_cache_key(
                cmp_op,
                int(bound),
                [int(self._lit_to_dimacs(l)) for _, l in pairs],
                [int(w) for w, _ in pairs],
            )
            cached = self._pb_clause_cache.get(key)
            if cached is not None:
                if self._debug_level >= self.DEBUG_COMPILE:
                    self._debug(self.DEBUG_COMPILE, "pb_cache hit")
                return cached
            if self._debug_level >= self.DEBUG_COMPILE:
                self._debug(self.DEBUG_COMPILE, "pb_cache miss")
            group = _EncoderDispatch.compile(self, lhs_r, op, rhs_r)
            self._pb_clause_cache[key] = group
            return group

    def _defer_pb_constraint(self, constraint: PBConstraint) -> None:
        """Register a PB/Card constraint for later clause materialization."""
        _ensure_same_model(self, constraint)
        current = self._encoding_profile.current_event() if self._encoding_profile is not None else None
        self._pending_pb_constraints.append(
            _DeferredPBEntry(
                constraint=constraint,
                origin_event_id=None if current is None else current.event_id,
                origin_kind=None if current is None else current.kind,
                origin_label=None if current is None else current.label,
            )
        )

    def _register_amo_group(self, lits: Sequence[int], *, exactly_one: bool = False) -> None:
        ordered: list[int] = []
        seen: set[int] = set()
        for lit in lits:
            lit_i = int(lit)
            if lit_i in seen:
                continue
            seen.add(lit_i)
            ordered.append(lit_i)
        if len(ordered) <= 1:
            return
        key = tuple(sorted(ordered))
        group = tuple(ordered)
        if bool(exactly_one):
            self._known_amo_groups.pop(key, None)
            self._known_eo_groups.setdefault(key, group)
        else:
            if key in self._known_eo_groups:
                return
            self._known_amo_groups.setdefault(key, group)

    def _register_small_int_eq_family_from_lits(self, lits: Sequence[Literal], *, max_span: int = 8) -> list[list[int]]:
        present: dict[int, tuple[IntVar, set[int]]] = {}
        for lit in lits:
            owner = self._intvar_eq_owner_by_litid.get(int(self._lit_to_dimacs(lit)))
            if owner is None:
                continue
            iv, value = owner
            key = id(iv)
            if key not in present:
                present[key] = (iv, set())
            present[key][1].add(int(value))

        added_groups: list[list[int]] = []
        for iv, seen_values in present.values():
            span = int(iv._span())
            if span <= 1 or span > int(max_span) or len(seen_values) < 2:
                continue
            group = [int(self._lit_to_dimacs(iv == value)) for value in range(int(iv.lb), int(iv.ub) + 1)]
            self._register_amo_group(group, exactly_one=True)
            added_groups.append(group)
        return added_groups

    def _maybe_register_pb_cardinality_structure(self, constraint: PBConstraint) -> None:
        if constraint._conditions or constraint._op not in {"<=", "<", "=="}:
            return

        analyzed = self._analyze_deferred_pb_constraint(constraint)
        cmp_op = str(analyzed["cmp_op"])
        bound = int(analyzed["bound"])
        if cmp_op not in {"<=", "=="} or bound != 1:
            return

        lits = list(analyzed["lits"])
        weights = [int(w) for w in analyzed["weights"]]
        if not lits or any(w <= 0 for w in weights):
            return

        group: list[int] = []
        all_groupable = True
        for lit in lits:
            dim = int(self._lit_to_dimacs(lit))
            if lit.id in self._intvar_threshold_owner_by_litid or dim in self._intvar_eq_owner_by_litid:
                all_groupable = False
                continue
            group.append(dim)

        if len(group) <= 1:
            return

        if cmp_op == "==" and all_groupable and len(group) == len(lits):
            self._register_amo_group(group, exactly_one=True)
            return
        self._register_amo_group(group, exactly_one=False)

    def _analyze_deferred_pb_constraint(self, constraint: PBConstraint) -> dict[str, object]:
        lhs_r = constraint._lhs._realize_int_terms(self)
        rhs_r = constraint._rhs._realize_int_terms(self)
        pairs, const = _EncoderDispatch._normalize_pb(lhs_r, rhs_r)
        cmp_op, bound = _EncoderDispatch._bound_from_zero_compare(constraint._op, const)
        lits = [lit for _, lit in pairs]
        weights = [int(w) for w, _ in pairs]
        g = reduce(math.gcd, weights) if weights else 1
        if g > 1:
            weights = [w // g for w in weights]
            if cmp_op == "<=":
                bound = int(bound) // g
            elif cmp_op == ">=":
                bound = -((-int(bound)) // g)
            elif cmp_op == "==":
                bound = int(bound) // g

        # Normalize >= to <= over negated literals so PBCompiler always sees <= or ==.
        # sum(w_i * x_i) >= k  <==>  sum(w_i * ~x_i) <= sum(w_i) - k
        if cmp_op == ">=":
            total = sum(weights)
            lits = [~lit for lit in lits]
            bound = total - int(bound)
            cmp_op = "<="

        return {
            "constraint": constraint,
            "lits": lits,
            "weights": weights,
            "cmp_op": cmp_op,
            "bound": int(bound),
            "all_unit": bool(weights) and all(w == 1 for w in weights),
        }

    def _prepare_pb_constraint(self, constraint: PBConstraint) -> ClauseGroup | PBConstraint:
        """Compile eager PB fast paths now, but classify PB/Card fallback for deferral."""
        with self.profile_scope("prepare_pb_constraint", metadata={"op": constraint._op}):
            _ensure_same_model(self, constraint)
            # Any comparator that still originates from IntVar / lazy-int arithmetic
            # should keep the historical eager behavior. Those constraints may lower
            # through specialized fast paths or through the generic PB encoder, but
            # callers and existing tests expect their side effects immediately.
            if constraint._lhs.int_terms or constraint._rhs.int_terms:
                group = constraint.clauses()
                return group
            lhs_r = constraint._lhs._realize_int_terms(self)
            rhs_r = constraint._rhs._realize_int_terms(self)
            self._validate_integral_pbexpr(lhs_r)
            self._validate_integral_pbexpr(rhs_r)

            eager_fast = None
            for fast_try in (
                _EncoderDispatch._try_unary_adder_eq_fastpath,
                _EncoderDispatch._try_int_equals_unit_bool_sum_fastpath,
                _EncoderDispatch._try_boolsum_bigm_fastpath,
                _EncoderDispatch._try_mixed_int_boolsum_bigm_fastpath,
                _EncoderDispatch._try_univariate_int_fastpath,
                _EncoderDispatch._try_univariate_with_bool_fastpath,
                _EncoderDispatch._try_nonnegative_zero_leq_fastpath,
                _EncoderDispatch._try_bivariate_with_bool_fastpath,
                _EncoderDispatch._try_trivariate_int_fastpath,
                _EncoderDispatch._try_bivariate_int_fastpath,
            ):
                out = fast_try(self, lhs_r, constraint._op, rhs_r)
                if out is not None:
                    eager_fast = out
                    break
            if eager_fast is not None:
                group = eager_fast
                for cond in constraint._conditions:
                    group = group.only_if(cond)
                return group
            if constraint._op == "!=":
                group = self._compile_pb_compare(lhs_r, constraint._op, rhs_r)
                for cond in constraint._conditions:
                    group = group.only_if(cond)
                return group

            def _uses_int_ladder(expr: PBExpr) -> bool:
                for term in expr.terms:
                    lit = term.literal
                    dim = int(self._lit_to_dimacs(lit))
                    if dim in self._intvar_eq_owner_by_litid:
                        continue
                    if lit.id in self._intvar_threshold_owner_by_litid:
                        return True
                return False

            # IntVar-derived arithmetic is lowered through ladder literals before it
            # reaches this point, so checking ``int_terms`` alone is not sufficient.
            # Keep anything that still touches IntVar ladder structure eager. Only
            # pure-Boolean PB/Card fallback constraints are deferred.
            if lhs_r.int_terms or rhs_r.int_terms or _uses_int_ladder(lhs_r) or _uses_int_ladder(rhs_r):
                group = self._compile_pb_compare(lhs_r, constraint._op, rhs_r)
                for cond in constraint._conditions:
                    group = group.only_if(cond)
                return group

            pairs, const = _EncoderDispatch._normalize_pb(lhs_r, rhs_r)
            cmp_op, bound = _EncoderDispatch._bound_from_zero_compare(constraint._op, const)
            if self._debug_level >= self.DEBUG_COMPILE:
                terms = ", ".join(f"{int(w)}*{int(self._lit_to_dimacs(l))}" for w, l in pairs)
                self._debug(
                    self.DEBUG_COMPILE,
                    f"pb_normalize raw_op={constraint._op} -> op={cmp_op} bound={int(bound)} terms=[{terms}]",
                )

            # Constant-only and trivial short-circuits are kept eager so their
            # immediate side effects and debug traces remain visible.
            if not pairs:
                group = self._compile_pb_compare(lhs_r, constraint._op, rhs_r)
                for cond in constraint._conditions:
                    group = group.only_if(cond)
                return group

            weights = [w for w, _ in pairs]
            g = reduce(math.gcd, weights) if weights else 1
            adj_bound = int(bound)
            adj_weights = list(weights)
            if g > 1:
                adj_weights = [w // g for w in adj_weights]
                if cmp_op == "<=":
                    adj_bound = adj_bound // g
                elif cmp_op == ">=":
                    adj_bound = -((-adj_bound) // g)
                elif cmp_op == "==":
                    if adj_bound % g != 0:
                        group = self._compile_pb_compare(lhs_r, constraint._op, rhs_r)
                        for cond in constraint._conditions:
                            group = group.only_if(cond)
                        return group
                    adj_bound = adj_bound // g
            total_weight = sum(adj_weights)
            trivial = (
                (cmp_op == "<=" and (adj_bound < 0 or adj_bound >= total_weight))
                or (cmp_op == ">=" and (adj_bound <= 0 or adj_bound > total_weight))
                or (cmp_op == "==" and (adj_bound < 0 or adj_bound > total_weight))
            )
            if trivial:
                group = self._compile_pb_compare(lhs_r, constraint._op, rhs_r)
                for cond in constraint._conditions:
                    group = group.only_if(cond)
                return group

            return PBConstraint(self, lhs_r, constraint._op, rhs_r, list(constraint._conditions))

    def _commit_pb(self, *, route: bool = True) -> None:
        """Materialize all deferred PB/Card constraints into hard clauses.

        Idempotent: once pending constraints are flushed, repeated calls are
        no-ops until new PB/Card constraints are added to the model.
        """
        if not self._pending_pb_constraints:
            return
        with self.profile_scope("commit_pb", metadata={"route": bool(route)}):
            hard0 = len(self._hard)
            soft0 = len(self._soft)
            pending, self._pending_pb_constraints = self._pending_pb_constraints, []
            from hermax.encoder import PBCompiler, PBItem

            batch_entries: list[tuple[_DeferredPBEntry, PBItem]] = []

            def _register_post_compile(item: PBItem, *, allow: bool) -> None:
                if not allow:
                    return
                if item.is_cardinality and item.bound == 1:
                    if item.cmp_op == "<=":
                        self._register_amo_group(item.lits, exactly_one=False)
                    elif item.cmp_op == "==":
                        self._register_amo_group(item.lits, exactly_one=True)

            def _integrate_group(group: ClauseGroup, conditions: Sequence[Literal]) -> ClauseGroup:
                final_group = group
                for cond in conditions:
                    final_group = final_group.only_if(cond)
                self._ensure_deferred_defs_in_group(final_group)
                self._hard.extend(final_group)
                return final_group

            def _compile_single(item: PBItem) -> ClauseGroup:
                if self._debug_level >= self.DEBUG_COMPILE:
                    if item.is_cardinality:
                        self._debug(
                            self.DEBUG_COMPILE,
                            f"encode path=structured_card_auto op={item.cmp_op} bound={int(item.bound)} n={len(item.lits)}",
                        )
                    else:
                        self._debug(
                            self.DEBUG_COMPILE,
                            f"encode path=structured_pb_auto op={item.cmp_op} bound={int(item.bound)} n={len(item.lits)} weights_sum={sum(item.get_weights())}",
                        )
                cnfs = PBCompiler.compile_batch_with_options(
                    items=[item],
                    amo_groups=list(self._known_amo_groups.values()),
                    eo_groups=list(self._known_eo_groups.values()),
                    top_id=self._top_id(),
                    merge_pb_optimization=False,
                    kmerge_config=self._kmerge_config,
                )
                assert len(cnfs) == 1
                return self._cnfplus_to_clausegroup(cnfs[0])

            prepared_entries: list[tuple[int, _DeferredPBEntry, PBItem, tuple[str, int, tuple[tuple[int, int], ...]], bool]] = []
            for idx, entry in enumerate(pending):
                analyzed = self._analyze_deferred_pb_constraint(entry.constraint)
                lits = [self._lit_to_dimacs(lit) for lit in analyzed["lits"]]
                weights = [int(w) for w in analyzed["weights"]]
                self._register_small_int_eq_family_from_lits(analyzed["lits"])
                pb_item = PBItem(
                    lits=lits,
                    weights=weights if not analyzed["all_unit"] else None,
                    bound=int(analyzed["bound"]),
                    cmp_op=str(analyzed["cmp_op"]),
                )
                cache_key = _canonical_pb_cache_key(pb_item.cmp_op, pb_item.bound, lits, weights)
                prepared_entries.append((idx, entry, pb_item, cache_key, bool(entry.constraint._conditions)))

            def _priority(item: PBItem) -> tuple[int, int]:
                is_card = item.is_cardinality
                is_amo_eo = is_card and int(item.bound) == 1 and str(item.cmp_op) in {"<=", "=="}
                if is_amo_eo:
                    return (0, 0)
                if is_card:
                    return (1, 0)
                return (2, 0)

            prepared_entries.sort(key=lambda row: (_priority(row[2]), row[0]))

            for _idx, entry, pb_item, cache_key, has_conditions in prepared_entries:
                metadata = {
                    "origin_event_id": entry.origin_event_id,
                    "origin_kind": entry.origin_kind,
                    "origin_label": entry.origin_label,
                }
                with self.profile_scope("commit_pb_constraint", metadata=metadata):
                    cached = self._pb_clause_cache.get(cache_key)
                    if cached is not None:
                        if self._debug_level >= self.DEBUG_COMPILE:
                            self._debug(self.DEBUG_COMPILE, "pb_cache hit")
                        _integrate_group(cached, entry.constraint._conditions if has_conditions else ())
                        _register_post_compile(pb_item, allow=not has_conditions)
                        continue
                    if self._debug_level >= self.DEBUG_COMPILE:
                        self._debug(self.DEBUG_COMPILE, "pb_cache miss")

                    if has_conditions:
                        group = _compile_single(pb_item)
                        self._pb_clause_cache[cache_key] = group
                        _integrate_group(group, entry.constraint._conditions)
                        _register_post_compile(pb_item, allow=False)
                        continue

                    can_batch_merge = (
                        bool(self._merge_pb_optimization_enabled)
                        and not pb_item.is_cardinality
                        and pb_item.cmp_op == "<="
                        and len(pb_item.lits) > 2
                    )
                    if can_batch_merge:
                        batch_entries.append((entry, pb_item))
                        continue

                    group = _compile_single(pb_item)
                    self._pb_clause_cache[cache_key] = group
                    _integrate_group(group, ())
                    _register_post_compile(pb_item, allow=True)

            if batch_entries:
                cnfs = PBCompiler.compile_batch_with_options(
                    items=[item for _entry, item in batch_entries],
                    amo_groups=list(self._known_amo_groups.values()),
                    eo_groups=list(self._known_eo_groups.values()),
                    top_id=self._top_id(),
                    merge_pb_optimization=bool(self._merge_pb_optimization_enabled),
                    kmerge_config=self._kmerge_config,
                )
                for cnf in cnfs:
                    group = self._cnfplus_to_clausegroup(cnf)
                    _integrate_group(group, ())
                for _entry, item in batch_entries:
                    _register_post_compile(item, allow=True)

            if self._debug_level >= self.DEBUG_DELTA:
                self._debug(
                    self.DEBUG_DELTA,
                    f"commit_pb count={len(pending)} hard_delta={len(self._hard) - hard0}",
                )
            if route:
                self._inc_state.route_deltas(hard0, soft0)

    def to_cnf(self) -> CNF:
        """Export the current hard constraints to a PySAT :class:`~pysat.formula.CNF`.

        Raises:
            ValueError: If the model contains soft clauses.
        """
        if self._soft:
            raise ValueError("Model contains soft clauses; use to_wcnf() instead.")
        self._commit_pb()
        self._ensure_all_pending_literal_defs_realized()
        self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard, reserve_aux_ids=False))
        cnf = CNF()
        for clause in self._hard:
            cnf.append(self._clause_to_dimacs_list(clause))
        return cnf

    def to_wcnf(self) -> WCNF:
        """Export hard and soft constraints to a PySAT :class:`~pysat.formula.WCNF`."""
        self._commit_pb()
        self._ensure_all_pending_literal_defs_realized()
        self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard, reserve_aux_ids=False))
        self._ensure_deferred_defs_in_group(ClauseGroup(self, [c for _, c in self._soft], reserve_aux_ids=False))
        wcnf = WCNF()
        for clause in self._hard:
            wcnf.append(self._clause_to_dimacs_list(clause))
        for weight, clause in self._soft:
            if int(weight) <= 0:
                continue
            wcnf.append(self._clause_to_dimacs_list(clause), weight=weight)
        return wcnf

    def _soft_weight_gcd(self) -> int:
        if not bool(self._soft_gcd_opt_enabled):
            return 1
        ws = [int(w) for w, _ in self._soft if int(w) > 0]
        if not ws:
            return 1
        g = reduce(math.gcd, ws)
        return int(g) if int(g) > 1 else 1

    def _to_wcnf_for_solver(self) -> tuple[WCNF, int]:
        """Build solver WCNF plus soft-weight scaling factor for one-shot solve."""
        self._commit_pb()
        self._ensure_all_pending_literal_defs_realized()
        self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard, reserve_aux_ids=False))
        self._ensure_deferred_defs_in_group(ClauseGroup(self, [c for _, c in self._soft], reserve_aux_ids=False))
        g = int(self._soft_weight_gcd())
        wcnf = WCNF()
        for clause in self._hard:
            wcnf.append(self._clause_to_dimacs_list(clause))
        for weight, clause in self._soft:
            if int(weight) <= 0:
                continue
            ww = int(weight) // g if g > 1 else int(weight)
            wcnf.append(self._clause_to_dimacs_list(clause), weight=int(ww))
        return wcnf, g

    def decode_model(self, model_lits: Sequence[int]) -> AssignmentView:
        """Return a decoded assignment view for a raw solver model."""
        return AssignmentView(self, model_lits)

    def _tier_entry_to_pbexpr(self, lit_weights: dict[int, int], offset: int) -> PBExpr:
        terms: list[Term] = []
        for dim, w in lit_weights.items():
            if int(w) <= 0:
                continue
            clause_lit = self._dimacs_to_lit(int(dim))
            # Soft unit clause [clause_lit] contributes when violated:
            # weight * (~clause_lit)
            terms.append(Term(int(w), ~clause_lit))
        return PBExpr(self, terms, int(offset))

    def _tier_entry_to_clausegroup_units(self, lit_weights: dict[int, int]) -> ClauseGroup:
        clauses: list[Clause] = []
        for dim, w in lit_weights.items():
            if int(w) <= 0:
                continue
            lit = self._dimacs_to_lit(int(dim))
            clauses.append(Clause(self, [lit]))
        return ClauseGroup(self, clauses)

    def _tier_hardening_group(self, lit_weights: dict[int, int], offset: int, bound_scaled: int) -> ClauseGroup:
        rhs = int(bound_scaled) - int(offset)
        active = {int(d): int(w) for d, w in lit_weights.items() if int(w) > 0}
        if not active:
            if rhs >= 0:
                return ClauseGroup(self, [])
            return ClauseGroup(self, [Clause(self, [])])
        if len(active) == 1:
            (dim, w), = active.items()
            if rhs < 0:
                return ClauseGroup(self, [Clause(self, [])])
            if rhs >= int(w):
                return ClauseGroup(self, [])
            lit = self._dimacs_to_lit(int(dim))
            return ClauseGroup(self, [Clause(self, [lit])])
        tier_expr = self._tier_entry_to_pbexpr(active, int(offset))
        return self._compile_pb_compare(tier_expr, "<=", PBExpr(self, [], int(bound_scaled)))

    @staticmethod
    def _i64_max() -> int:
        return (1 << 63) - 1

    def _assert_lex_exclusive_usage(self) -> None:
        if self._tier_obj_proxy.is_active() and self._has_active_flat_objective():
            raise ValueError("model.obj/add_soft and model.tier_obj cannot be active simultaneously.")

    def _solve_lex_incremental(
        self,
        *,
        assumptions: Optional[Sequence[object]],
        solver,
        solver_kwargs: dict,
        raise_on_abnormal: bool,
    ) -> SolveResult:
        tiers = self._tier_obj_proxy.iter_active_tiers()
        assumptions_dimacs = self._coerce_assumptions(assumptions)
        tier_costs: list[int | float] = []
        tier_models: list[list[int]] = []
        hardening: list[ClauseGroup] = []
        last_status = "unknown"
        last_raw_model: list[int] | None = None
        last_backend = "hermax.unknown"

        for _tier_idx, lit_weights, offset in tiers:
            # Build temporary one-shot formula from hard + hardening + current tier soft units.
            self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard, reserve_aux_ids=False))
            soft_group = self._tier_entry_to_clausegroup_units(lit_weights)
            self._ensure_deferred_defs_in_group(soft_group)

            formula = WCNF()
            for c in self._hard:
                formula.append(self._clause_to_dimacs_list(c))
            for a in assumptions_dimacs:
                v = abs(int(a))
                if v > 0:
                    formula.append([int(v), -int(v)])
            for g in hardening:
                for c in g:
                    formula.append(self._clause_to_dimacs_list(c))
            for dim, w in lit_weights.items():
                if int(w) > 0:
                    formula.append([int(dim)], weight=int(w))

            res = self._solve_with_hermax_solver(
                solver=solver if solver is not None else HermaxRC2,
                solver_kwargs=solver_kwargs,
                assumptions=assumptions_dimacs,
                raise_on_abnormal=raise_on_abnormal,
                formula_override=formula,
                objective_constant_override=int(offset),
            )
            last_status = res.status
            last_backend = res.backend
            last_raw_model = list(res.raw_model) if res.raw_model is not None else None
            if not res.ok:
                return SolveResult(
                    self,
                    status=res.status,
                    raw_model=res.raw_model,
                    cost=None,
                    backend=res.backend,
                    tier_costs=None,
                    tier_models=None,
                )
            assert res.cost is not None
            tier_costs.append(res.cost)
            tier_models.append(list(res.raw_model or []))

            # Harden current tier optimum for next tiers: tier_expr <= tier_cost_scaled
            if self._objective_precision_decimals is None:
                hard_bound_scaled = int(res.cost)
            else:
                hard_bound_scaled = int(round(float(res.cost) * float(self._objective_precision_scale)))
            hard_group = self._tier_hardening_group(lit_weights, int(offset), int(hard_bound_scaled))
            self._ensure_deferred_defs_in_group(hard_group)
            hardening.append(hard_group)

        final_cost = tier_costs[-1] if tier_costs else None
        return SolveResult(
            self,
            status=last_status,
            raw_model=last_raw_model,
            cost=final_cost,
            backend=last_backend,
            tier_costs=tier_costs or None,
            tier_models=tier_models or None,
        )

    def _solve_lex_stratified(
        self,
        *,
        assumptions: Optional[Sequence[object]],
        solver,
        solver_kwargs: dict,
        raise_on_abnormal: bool,
    ) -> SolveResult:
        tiers = self._tier_obj_proxy.iter_active_tiers()
        assumptions_dimacs = self._coerce_assumptions(assumptions)
        if not tiers:
            return self.solve(
                assumptions=assumptions_dimacs,
                incremental=False,
                solver=solver,
                solver_kwargs=solver_kwargs,
                raise_on_abnormal=raise_on_abnormal,
            )

        max_var: list[int] = []
        offsets: list[int] = []
        for _idx, lit_weights, offset in tiers:
            max_var.append(sum(int(w) for w in lit_weights.values() if int(w) > 0))
            offsets.append(int(offset))

        bases = [1] * len(tiers)
        i64 = self._i64_max()
        for i in range(len(tiers) - 2, -1, -1):
            factor = int(max_var[i + 1]) + 1
            if factor <= 0:
                factor = 1
            if bases[i + 1] > 0 and bases[i + 1] > i64 // factor:
                raise OverflowError("Lexicographic stratification overflow risk detected. Use lex_strategy='incremental'.")
            bases[i] = int(bases[i + 1]) * int(factor)
            if bases[i] > i64:
                raise OverflowError("Lexicographic stratification overflow risk detected. Use lex_strategy='incremental'.")

        flat_lit_weights: dict[int, int] = {}
        flat_offset = 0
        for i, (_idx, lit_weights, offset) in enumerate(tiers):
            b = int(bases[i])
            flat_offset += int(offset) * b
            for dim, w in lit_weights.items():
                ww = int(w) * b
                if ww <= 0:
                    continue
                if ww > i64:
                    raise OverflowError("Lexicographic stratification overflow risk detected. Use lex_strategy='incremental'.")
                flat_lit_weights[int(dim)] = int(flat_lit_weights.get(int(dim), 0)) + int(ww)
                if flat_lit_weights[int(dim)] > i64:
                    raise OverflowError("Lexicographic stratification overflow risk detected. Use lex_strategy='incremental'.")

        self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard, reserve_aux_ids=False))
        soft_group = self._tier_entry_to_clausegroup_units(flat_lit_weights)
        self._ensure_deferred_defs_in_group(soft_group)

        formula = WCNF()
        for c in self._hard:
            formula.append(self._clause_to_dimacs_list(c))
        for a in assumptions_dimacs:
            v = abs(int(a))
            if v > 0:
                formula.append([int(v), -int(v)])
        for dim, w in flat_lit_weights.items():
            if int(w) > 0:
                formula.append([int(dim)], weight=int(w))

        res = self._solve_with_hermax_solver(
            solver=solver if solver is not None else HermaxRC2,
            solver_kwargs=solver_kwargs,
            assumptions=assumptions_dimacs,
            raise_on_abnormal=raise_on_abnormal,
            formula_override=formula,
            objective_constant_override=int(flat_offset),
        )
        if not res.ok:
            return SolveResult(
                self,
                status=res.status,
                raw_model=res.raw_model,
                cost=res.cost,
                backend=res.backend,
                tier_costs=None,
                tier_models=None,
            )

        raw_flat_var = 0
        if self._objective_precision_decimals is None:
            raw_total = int(res.cost or 0)
            raw_flat_var = int(raw_total) - int(flat_offset)
        else:
            raw_total = int(round(float(res.cost or 0.0) * float(self._objective_precision_scale)))
            raw_flat_var = int(raw_total) - int(flat_offset)
        if raw_flat_var < 0:
            raw_flat_var = 0

        tier_costs: list[int | float] = []
        rem = int(raw_flat_var)
        for i in range(len(tiers)):
            b = int(bases[i])
            var_i = rem // b if b > 0 else 0
            rem = rem % b if b > 0 else 0
            scaled_i = int(var_i) + int(offsets[i])
            tier_costs.append(self._format_objective_cost(int(scaled_i)))

        return SolveResult(
            self,
            status=res.status,
            raw_model=res.raw_model,
            cost=res.cost,
            backend=res.backend,
            tier_costs=tier_costs,
            tier_models=None,
        )

    def solve(
        self,
        *,
        sat_solver_name: str = "g4",
        maxsat_backend: str = "rc2",
        solver=None,
        solver_kwargs: Optional[dict] = None,
        assumptions: Optional[Sequence[object]] = None,
        incremental: bool = True,
        backend: str = "auto",
        raise_on_abnormal: bool = False,
        sat_upgrade: str = "upgrade",
        lex_strategy: Optional[str] = None,
        time_limit: Optional[float] = None,
    ) -> SolveResult:
        """Solve the model using built-in convenience backends.

        Behavior:
            * hard-only model -> PySAT SAT solver (``sat_solver_name``)
            * model with soft clauses -> PySAT RC2 (``maxsat_backend='rc2'``)
            * if ``solver`` is provided, use a Hermax ``IPAMIRSolver`` class (or
              instance) with the model exported as WCNF (one-shot solve)

        Notes:
            Assumptions accept ``int`` DIMACS literals, :class:`Literal`, or
            unit :class:`Term` with coefficient ``+1``/``-1``; plain ``bool``
            values are rejected.
            In incremental mode, SAT binding can upgrade to MaxSAT when soft
            clauses appear (controlled by ``sat_upgrade``).
            ``lex_strategy`` is meaningful only when ``model.tier_obj`` is active.
        """
        limit = validate_time_limit(time_limit)
        if not isinstance(incremental, bool):
            raise TypeError("incremental must be a bool.")
        self._assert_lex_exclusive_usage()
        ls = None if lex_strategy is None else str(lex_strategy).lower()
        if ls is not None and ls not in {"incremental", "stratified"}:
            raise ValueError("lex_strategy must be one of: incremental, stratified")

        if self._tier_obj_proxy.is_active():
            if limit is not None:
                raise NotImplementedError(
                    "time_limit with tier_obj is not supported yet because a single "
                    "budget must cover several lexicographic solves."
                )
            self._commit_pb()
            if ls is None:
                ls = "incremental"
            if ls == "incremental":
                return self._solve_lex_incremental(
                    assumptions=assumptions,
                    solver=solver,
                    solver_kwargs=solver_kwargs or {},
                    raise_on_abnormal=raise_on_abnormal,
                )
            return self._solve_lex_stratified(
                assumptions=assumptions,
                solver=solver,
                solver_kwargs=solver_kwargs or {},
                raise_on_abnormal=raise_on_abnormal,
            )

        use_incremental = bool(incremental or self._inc_state.bound)
        # One-shot convenience MaxSAT (PySAT RC2) when no incremental
        # MaxSAT backend is explicitly provided and no backend is bound yet.
        if (
            use_incremental
            and self._inc_state.mode is None
            and self._soft
            and solver is None
            and (backend or "auto").lower() == "auto"
        ):
            use_incremental = False
        # One-shot explicit solver path for backend='auto' when caller
        # passes a concrete solver/factory and no incremental backend is bound.
        if (
            use_incremental
            and self._inc_state.mode is None
            and solver is not None
            and not self._soft
            and (backend or "auto").lower() == "auto"
        ):
            use_incremental = False

        # If incremental backend is already bound, always continue incrementally.
        if use_incremental:
            return self._inc_state.solve(
                sat_solver_name=sat_solver_name,
                backend=backend,
                solver=solver,
                solver_kwargs=solver_kwargs or {},
                assumptions=assumptions,
                raise_on_abnormal=raise_on_abnormal,
                sat_upgrade=sat_upgrade,
                time_limit=limit,
            )

        if solver is not None:
            return self._solve_with_hermax_solver(
                solver=solver,
                solver_kwargs=solver_kwargs or {},
                assumptions=assumptions,
                raise_on_abnormal=raise_on_abnormal,
                time_limit=limit,
            )

        if self._soft:
            if maxsat_backend.lower() != "rc2":
                raise ValueError("Unsupported maxsat backend for Model.solve().")

            return self._solve_with_hermax_solver(
                solver=HermaxRC2,
                solver_kwargs={},
                assumptions=assumptions,
                raise_on_abnormal=raise_on_abnormal,
                time_limit=limit,
            )

        cnf = self.to_cnf()
        sat_solver = PySATReplaySolver(sat_solver_name)
        sat_solver.ensure_var(cnf.nv)
        for clause in cnf.clauses:
            sat_solver.add_clause(clause)
        result = sat_solver.solve(
            assumptions=self._coerce_assumptions(assumptions),
            time_limit=limit,
        )
        return SolveResult(
            self,
            status=result.status,
            raw_model=result.model,
            cost=None,
            backend=f"pysat.{sat_solver_name}",
        )

    def _solve_with_hermax_solver(
        self,
        *,
        solver,
        solver_kwargs: dict,
        assumptions: Optional[Sequence[object]],
        raise_on_abnormal: bool,
        time_limit: Optional[float] = None,
        formula_override: Optional[WCNF] = None,
        objective_constant_override: Optional[int] = None,
    ) -> SolveResult:
        """Solve via a Hermax ``IPAMIRSolver`` backend (including portfolios)."""
        from hermax.core.ipamir_solver_interface import IPAMIRSolver, is_feasible

        if formula_override is None:
            formula, soft_gcd = self._to_wcnf_for_solver()
            objective_constant = int(self._objective_constant)
        else:
            formula = formula_override
            soft_gcd = 1
            objective_constant = int(self._objective_constant if objective_constant_override is None else objective_constant_override)
        if soft_gcd > 1 and self._debug_level >= self.DEBUG_COMPILE:
            self._debug(self.DEBUG_COMPILE, f"soft_gcd optimize factor={soft_gcd}")

        def _replay_into_existing_instance(ip_solver: IPAMIRSolver, formula_obj: WCNF) -> None:

            # Preallocation for wrappers that require explicit variable creation.
            next_vid = 0
            try:
                for _ in range(int(formula_obj.nv)):
                    next_vid = int(ip_solver.new_var())
            except NotImplementedError:
                next_vid = int(formula_obj.nv)

            for c in formula_obj.hard:
                ip_solver.add_clause([int(l) for l in c])

            for w, c in zip(formula_obj.wght, formula_obj.soft):
                clause = [int(l) for l in c]
                weight = int(w)
                if len(clause) == 1:
                    ip_solver.add_soft_unit(clause[0], weight)
                    continue

                # Generic non-unit soft replay through explicit relaxation var.
                relax = None
                try:
                    relax = int(ip_solver.new_var())
                    next_vid = max(next_vid, relax)
                except NotImplementedError:
                    next_vid += 1
                    relax = next_vid
                ip_solver.add_soft_relaxed(clause, weight, relax)

        created = False
        if isinstance(solver, IPAMIRSolver):
            if time_limit is not None:
                raise NotImplementedError(
                    "time_limit with a solver instance is only supported by a live "
                    "backend that implements interruption. Pass a solver class for "
                    "one-shot execution."
                )
            if solver_kwargs:
                raise ValueError("solver_kwargs are only supported when passing a solver class/callable.")
            ip_solver = solver
            _replay_into_existing_instance(ip_solver, formula)
        else:
            if not callable(solver):
                raise TypeError("solver must be an IPAMIRSolver instance, class, or callable factory.")
            if time_limit is not None:
                if solver_kwargs:
                    raise ValueError(
                        "solver_kwargs are not supported for one-shot time-limited execution. "
                        "Configure the solver class directly or use PortfolioSolver."
                    )
                from hermax.portfolio.solver import PortfolioSolver

                ip_solver = PortfolioSolver(
                    [solver],
                    formula=formula,
                    per_solver_time_limit_s=time_limit,
                    overall_time_limit_s=time_limit,
                    max_workers=1,
                )
            else:
                ip_solver = solver(formula=formula, **solver_kwargs)
            created = True
            if not isinstance(ip_solver, IPAMIRSolver):
                if created:
                    self._safe_close_backend(ip_solver)
                raise TypeError("solver callable must return an IPAMIRSolver instance.")

        try:
            ip_solver.solve(
                assumptions=self._coerce_assumptions(assumptions),
                raise_on_abnormal=bool(raise_on_abnormal),
                time_limit=time_limit,
            )
            st = ip_solver.get_status()
            status = _map_ipamir_status_to_model_status(st)
            feasible = is_feasible(st)
            raw_model = None
            cost = None
            if feasible:
                raw_model = ip_solver.get_model()
                c = ip_solver.get_cost()
                cost = self._format_objective_cost(int(c) * int(soft_gcd) + int(objective_constant))
            backend = f"hermax.{ip_solver.signature()}"
            return SolveResult(self, status=status, raw_model=raw_model, cost=cost, backend=backend)
        finally:
            if created:
                self._safe_close_backend(ip_solver)
