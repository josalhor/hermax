from __future__ import annotations
import math
import operator as _operator
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import reduce
from typing import Callable, Iterable, Mapping, Optional, Sequence
from pysat.formula import CNF, WCNF
from ._integer_views import binary_view as _binary_view_for
from hermax.internal.operation_cache import _Identity, cached_operation
from hermax.encoder.card import EncType as CardEncType
from hermax.encoder._packed import CardEnc
from hermax.encoder.pb_enc import PBEnc
from hermax.encoder.pbamo import PBAMOEnc
from hermax.utils import batcher_odd_even_unary_add_network
from pysat.solvers import Solver as PySATSolver
from hermax.non_incremental import RC2 as HermaxRC2

from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from .expressions import *
    from .variables import *
    from .encoders import *
    from .core import *

from .expressions import *
from .expressions import (
    _detection_error,
    _nonlinear_error,
    _ensure_same_model,
    _ensure_same_model_pair_fast,
    _compare_pb_operands,
    _unsupported_comparison_error,
    _LazyIntExpr,
    DeferredClauseGroup,
    _ReifiableClauseGroup,
    _BooleanComposition,
    _PredicateLiteral,
    _deferred_constant_constraint,
)
from ._int_thresholds import ThresholdLiterals


_INTEGER_COMPARISONS = {
    "<=": _operator.le, "<": _operator.lt,
    ">=": _operator.ge, ">": _operator.gt,
    "==": _operator.eq, "!=": _operator.ne,
}


def _integer_runs(values: Sequence[int]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    for value in values:
        if runs and value == runs[-1][1] + 1:
            runs[-1] = runs[-1][0], value
        else:
            runs.append((value, value))
    return runs


class IntSetVar:
    """Finite set variable over integers, encoded as one membership literal per value."""

    __slots__ = ("_model", "name", "universe", "_member_lits", "_contains_cache")

    def __init__(self, model: "Model", name: str, universe: Sequence[int]):
        self._model = model
        self.name = name
        seen: set[int] = set()
        vals: list[int] = []
        for v in universe:
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError("IntSetVar universe values must be integers.")
            iv = int(v)
            if iv in seen:
                continue
            seen.add(iv)
            vals.append(iv)
        vals.sort()
        self.universe = tuple(vals)
        self._member_lits: dict[int, Literal] = {
            v: model.bool(f"{name}::in[{v}]") for v in self.universe
        }
        self._contains_cache: dict[_Identity, Literal] = {}

    def _lit_for_value(self, value: int) -> Literal:
        lit = self._member_lits.get(int(value))
        if lit is not None:
            return lit
        return self._model._get_bool_constant_literal(False)

    @staticmethod
    def _coerce_constant_values(values) -> set[int]:
        if not isinstance(values, (set, frozenset, list, tuple)):
            raise TypeError("Set constants must be a set/list/tuple of integers.")
        out: set[int] = set()
        for v in values:
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError("Set constants must contain integers only.")
            out.add(int(v))
        return out

    def _xor_indicator(self, a: Literal, b: Literal) -> tuple[Literal, list[Clause]]:
        m = self._model
        true_lit = m._get_bool_constant_literal(True)
        false_lit = m._get_bool_constant_literal(False)

        if a is b:
            return false_lit, []
        if a is ~b:
            return true_lit, []
        if a is false_lit:
            return b, []
        if b is false_lit:
            return a, []
        if a is true_lit:
            return ~b, []
        if b is true_lit:
            return ~a, []

        d = m.bool()
        clauses = [
            Clause(m, [a, b, ~d]),       # both false -> d false
            Clause(m, [~a, ~b, ~d]),     # both true -> d false
            Clause(m, [~a, b, d]),       # a=false,b=true -> d true
            Clause(m, [a, ~b, d]),       # a=true,b=false -> d true
        ]
        return d, clauses

    def contains(self, value: int | "IntVar") -> Literal:
        """Return an indicator for membership in the selected set value.

        For an ``IntVar`` argument, the indicator is true exactly when the
        chosen integer is selected by this set variable, not merely when it
        belongs to the set's declared universe.
        """
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            key = _Identity(value)
            cached = self._contains_cache.get(key)
            if cached is not None:
                return cached

            candidate_vals = [v for v in self.universe if value.lb <= v <= value.ub]
            if not candidate_vals:
                lit = self._model._get_bool_constant_literal(False)
                self._contains_cache[key] = lit
                return lit

            if value.lb == value.ub:
                lit = self._member_lits[value.lb]
                self._contains_cache[key] = lit
                return lit

            owner = value._encoding_owner()
            reuse = any(candidate - value.lb + owner.lb in owner._eq_lits
                        for candidate in candidate_vals)
            if reuse:
                equalities = [value == candidate for candidate in candidate_vals]
                guards = ([~equal] for equal in equalities)
            else:
                guards = ([~atom for atom in value._exact_value_atoms(candidate)]
                          for candidate in candidate_vals)

            b = self._model._predicate_bool(lambda result: result[value] in result[self])
            clauses = ([Clause(self._model, [~b, *equalities])] if reuse else
                       list(value._allowed_values(candidate_vals).only_if(b)))
            for candidate, guard in zip(candidate_vals, guards):
                member = self._member_lits[candidate]
                clauses.append(Clause(self._model, [*guard, ~b, member]))
                clauses.append(Clause(self._model, [*guard, ~member, b]))
            self._model._register_literal_definition(b, ClauseGroup(self._model, clauses))
            self._contains_cache[key] = b
            return b

        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("contains() expects an integer or IntVar.")
        return self._lit_for_value(int(value))

    def cardinality(self) -> PBExpr:
        """Return cardinality expression ``|self|``."""
        return PBExpr(self._model, [Term(1, lit) for lit in self._member_lits.values()], 0)

    @cached_operation()
    def card(self, name: Optional[str] = None) -> "IntVar":
        """Return an integer variable equal to this set's cardinality.

        Its clauses are added lazily, when the result is used in a constraint,
        export, or solve.
        """
        out_name = self._model._reserve_name(None) if name is None else name
        n = len(self.universe)
        out = self._model.int(out_name, lb=0, ub=n)
        if n == 0:
            return out

        from .encoders import _EncoderDispatch

        clauses, wires = _EncoderDispatch._build_sequential_ge_counter(
            self._model, list(self._member_lits.values())
        )

        for k, t_k in enumerate(out._threshold_lits):
            w = wires[k + 1]
            _EncoderDispatch._lit_implies(clauses, self._model, w, t_k)
            _EncoderDispatch._lit_implies(clauses, self._model, t_k, w)

        if clauses and out._threshold_lits:
            # Register lazily: trigger on the first threshold literal of `out`.
            # When any clause referencing out._threshold_lits is committed to
            # the model, _ensure_deferred_defs_in_group will realize this group.
            self._model._register_literal_definition(
                out._threshold_lits[0],
                ClauseGroup(self._model, clauses),
            )

        return out

    def subset_of(self, other: "IntSetVar") -> ClauseGroup:
        if not isinstance(other, IntSetVar):
            raise TypeError("subset_of() expects IntSetVar.")
        _ensure_same_model_pair_fast(self, other)
        if self is other:
            return ClauseGroup(self._model, [])
        clauses = []
        for value, left in self._member_lits.items():
            right = other._member_lits.get(value)
            literals = [~left] if right is None else [~left, right]
            clauses.append(Clause(self._model, literals))
        return ClauseGroup(self._model, clauses)

    def superset_of(self, other: "IntSetVar") -> ClauseGroup:
        if not isinstance(other, IntSetVar):
            raise TypeError("superset_of() expects IntSetVar.")
        _ensure_same_model_pair_fast(self, other)
        return other.subset_of(self)

    def _eq_group_set(self, other: "IntSetVar") -> ClauseGroup:
        _ensure_same_model_pair_fast(self, other)
        vals = sorted(set(self.universe) | set(other.universe))
        clauses: list[Clause] = []
        for v in vals:
            a = self._lit_for_value(v)
            b = other._lit_for_value(v)
            clauses.extend(self._model._equiv_literals_group(a, b))
        return ClauseGroup(self._model, clauses)

    def _eq_group_constant(self, values) -> ClauseGroup:
        const_vals = self._coerce_constant_values(values)
        if any(v not in self._member_lits for v in const_vals):
            return ClauseGroup(self._model, [Clause(self._model, [])])
        clauses: list[Clause] = []
        for v in self.universe:
            lit = self._member_lits[v]
            clauses.append(Clause(self._model, [lit if v in const_vals else ~lit]))
        return ClauseGroup(self._model, clauses)

    def _neq_group_set(self, other: "IntSetVar") -> ClauseGroup:
        _ensure_same_model_pair_fast(self, other)
        vals = tuple(sorted(set(self.universe) | set(other.universe)))

        def _build() -> ClauseGroup:
            true_lit = self._model._get_bool_constant_literal(True)
            false_lit = self._model._get_bool_constant_literal(False)
            diff_lits: list[Literal] = []
            clauses: list[Clause] = []
            for v in vals:
                d, defs = self._xor_indicator(self._lit_for_value(v), other._lit_for_value(v))
                clauses.extend(defs)
                if d is true_lit:
                    return ClauseGroup(self._model, clauses)
                if d is false_lit:
                    continue
                diff_lits.append(d)
            if not diff_lits:
                clauses.append(Clause(self._model, []))
            else:
                clauses.append(Clause(self._model, diff_lits))
            return ClauseGroup(self._model, clauses)

        return _ReifiableClauseGroup(self._model, _build, lambda: self._eq_group_set(other))

    def _neq_group_constant(self, values) -> ClauseGroup:
        const_vals = self._coerce_constant_values(values)
        outside = [v for v in const_vals if v not in self._member_lits]
        if outside:
            return ClauseGroup(self._model, [])

        def _build() -> ClauseGroup:
            differences = [~lit if value in const_vals else lit
                           for value, lit in self._member_lits.items()]
            return ClauseGroup(self._model, [Clause(self._model, differences)])

        return _ReifiableClauseGroup(self._model, _build, lambda: self._eq_group_constant(const_vals))

    @cached_operation()
    def _binary_set_op(self, other: "IntSetVar", op: str, name: Optional[str] = None) -> "IntSetVar":
        if not isinstance(other, IntSetVar):
            raise TypeError("set operation expects IntSetVar.")
        _ensure_same_model_pair_fast(self, other)
        if op not in ("union", "intersection", "difference", "symdiff"):
            raise ValueError(f"Unknown set op {op!r}")
        vals = sorted(set(self.universe) | set(other.universe))
        out_name = self._model._reserve_name(None) if name is None else name
        self._model._reserve_container_name(out_name)
        out = IntSetVar(self._model, out_name, vals)
        for v in vals:
            a = self._member_lits.get(v)
            b = other._member_lits.get(v)
            r = out._member_lits[v]
            if a is None or b is None:
                if op == "intersection" or (op == "difference" and a is None):
                    group = ClauseGroup(self._model, [Clause(self._model, [~r])])
                else:
                    source = b if a is None else a
                    group = self._model._equiv_literals_group(r, source)
            elif op == "union":
                group = ClauseGroup(
                    self._model,
                    [
                        Clause(self._model, [~r, a, b]),
                        Clause(self._model, [~a, r]),
                        Clause(self._model, [~b, r]),
                    ],
                )
            elif op == "intersection":
                group = ClauseGroup(
                    self._model,
                    [
                        Clause(self._model, [~r, a]),
                        Clause(self._model, [~r, b]),
                        Clause(self._model, [~a, ~b, r]),
                    ],
                )
            elif op == "difference":
                group = ClauseGroup(
                    self._model,
                    [
                        Clause(self._model, [~r, a]),
                        Clause(self._model, [~r, ~b]),
                        Clause(self._model, [~a, b, r]),
                    ],
                )
            else:
                group = ClauseGroup(
                    self._model,
                    [
                        Clause(self._model, [a, b, ~r]),
                        Clause(self._model, [~a, ~b, ~r]),
                        Clause(self._model, [~a, b, r]),
                        Clause(self._model, [a, ~b, r]),
                    ],
                )
            self._model._register_literal_definition(r, group)
        return out

    def union(self, other: "IntSetVar", *, name: Optional[str] = None) -> "IntSetVar":
        return self._binary_set_op(other, "union", name=name)

    def intersection(self, other: "IntSetVar", *, name: Optional[str] = None) -> "IntSetVar":
        return self._binary_set_op(other, "intersection", name=name)

    def difference(self, other: "IntSetVar", *, name: Optional[str] = None) -> "IntSetVar":
        return self._binary_set_op(other, "difference", name=name)

    def symmetric_difference(self, other: "IntSetVar", *, name: Optional[str] = None) -> "IntSetVar":
        return self._binary_set_op(other, "symdiff", name=name)

    def __or__(self, other):
        return self.union(other)

    def __and__(self, other):
        return self.intersection(other)

    def __sub__(self, other):
        return self.difference(other)

    def __xor__(self, other):
        return self.symmetric_difference(other)

    def __eq__(self, other):  # type: ignore[override]
        if isinstance(other, IntSetVar):
            return self._eq_group_set(other)
        if isinstance(other, (set, frozenset, list, tuple)):
            return self._eq_group_constant(other)
        raise _unsupported_comparison_error(self, other)

    def __ne__(self, other):  # type: ignore[override]
        if isinstance(other, IntSetVar):
            return self._neq_group_set(other)
        if isinstance(other, (set, frozenset, list, tuple)):
            return self._neq_group_constant(other)
        raise _unsupported_comparison_error(self, other)


class _FrozenList(list):
    """List-compatible immutable sequence used for public enum choices."""

    @staticmethod
    def _immutable(*_args, **_kwargs):
        raise TypeError("Enum choices are immutable.")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable


def _is_enum_label(value):
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _validate_enum_choices(choices, nullable):
    if isinstance(choices, (str, bytes)) or not isinstance(choices, Sequence):
        raise TypeError("Enum choices must be a sequence of strings or integers.")
    if not isinstance(nullable, bool):
        raise TypeError("nullable must be a bool.")
    if not (all(isinstance(c, str) for c in choices)
            or all(isinstance(c, int) and not isinstance(c, bool) for c in choices)):
        raise TypeError("Enum choices must be all strings or all integers.")
    if len(set(choices)) != len(choices):
        raise ValueError("Enum choices must be unique.")
    if not choices and not nullable:
        raise ValueError("Non-nullable EnumVar requires at least one choice.")


class EnumVar:
    """Finite-domain categorical variable encoded as choice literals."""
    __slots__ = ("_model", "name", "choices", "nullable", "_choice_lits")

    def __init__(self, model: "Model", name: str, choices: Sequence[str | int], nullable: bool):
        self._model = model
        self.name = name
        _validate_enum_choices(choices, nullable)
        self.choices = _FrozenList(choices)
        self.nullable = nullable
        if not self.choices and not self.nullable:
            raise ValueError("Non-nullable EnumVar requires at least one choice.")
        self._choice_lits = {c: model.bool(f"{name}::{c}") for c in self.choices}
        self._add_domain_constraints()

    def _none_indicator(self) -> Literal:
        if not self.nullable:
            raise ValueError("Enum is not nullable.")

        def definition(indicator):
            choices = list(self._choice_lits.values())
            clauses = [Clause(self._model, [~indicator, ~choice]) for choice in choices]
            clauses.append(Clause(self._model, [*choices, indicator]))
            return ClauseGroup(self._model, clauses)

        return self._model.canonical_internal_bool(
            ("table_enum_none", _Identity(self)), definition=definition
        )

    def _add_domain_constraints(self) -> None:
        lits = [self._choice_lits[c] for c in self.choices]
        if not lits:
            return
        dimacs = [self._model._lit_to_dimacs(lit) for lit in lits]
        if len(lits) <= 8:
            clauses = []
            for i in range(len(lits)):
                for j in range(i + 1, len(lits)):
                    clauses.append(Clause(self._model, [~lits[i], ~lits[j]]))
            if self.nullable:
                group = ClauseGroup(self._model, clauses, amo_groups=[dimacs])
            else:
                clauses.append(Clause(self._model, lits))
                group = ClauseGroup(self._model, clauses, eo_groups=[dimacs])
        else:
            if self.nullable:
                cnf = CardEnc.atmost(lits=dimacs, bound=1, top_id=self._model._top_id(), encoding=CardEncType.seqcounter)
                group = ClauseGroup(self._model, self._model._cnfplus_to_clausegroup(cnf), amo_groups=[dimacs])
            else:
                cnf = CardEnc.equals(lits=dimacs, bound=1, top_id=self._model._top_id(), encoding=CardEncType.seqcounter)
                group = ClauseGroup(self._model, self._model._cnfplus_to_clausegroup(cnf), eo_groups=[dimacs])
        self._model._register_clausegroup_structure(group)
        for lit in lits:
            self._model._register_literal_definition(lit, group)

    def _choice_literal(self, value):
        if value is None:
            raise ValueError("Unknown enum choice None")
        if not _is_enum_label(value):
            raise TypeError("Enum labels must be strings or integers, not bools.")
        if self.choices and isinstance(value, str) != isinstance(self.choices[0], str):
            raise TypeError("Enum labels must match the type of the declared choices.")
        try:
            return self._choice_lits[value]
        except KeyError:
            raise ValueError(f"Unknown enum choice {value!r}") from None

    def is_in(self, choices: Sequence[str | int]) -> Clause:
        """Return a clause asserting that the enum is one of ``choices``.

        The clause reuses the enum's choice literals and adds no variables.

        Args:
            choices: Sequence of allowed enum labels.

        Returns:
            A :class:`Clause` equivalent to ``(self == c1) | (self == c2) | ...``.

        Raises:
            ValueError: If ``choices`` is empty or contains an unknown label.
        """
        seen = set()
        lits: list[Literal] = []
        for c in choices:
            self._choice_literal(c)
            if c in seen:
                continue
            seen.add(c)
            lits.append(self._choice_lits[c])
        if not lits:
            raise ValueError("EnumVar.is_in() requires at least one valid choice.")
        return Clause.from_iterable(lits)

    def is_in_or_none(self, choices: Sequence[str | int]) -> ClauseGroup:
        """Return a nullable constraint allowing ``choices`` or ``None``.

        It is valid only for nullable enums. It may return more than one clause
        and adds no auxiliary variables.

        Args:
            choices: Allowed concrete enum labels. The nullable ``None`` branch
                is always allowed by this method.

        Returns:
            A :class:`ClauseGroup` encoding membership in ``choices`` or
            ``None``.

        Raises:
            ValueError: If the enum is non-nullable, if ``choices`` contains an
                unknown label, or if ``choices`` is empty.
        """
        if not self.nullable:
            raise ValueError("EnumVar.is_in_or_none() requires a nullable enum.")
        seen = set()
        allowed_labels: list[str | int] = []
        for c in choices:
            self._choice_literal(c)
            if c in seen:
                continue
            seen.add(c)
            allowed_labels.append(c)
        if not allowed_labels:
            raise ValueError("EnumVar.is_in_or_none() requires at least one valid choice.")
        excluded = [self._choice_lits[c] for c in self.choices if c not in seen]
        clauses = [Clause(self._model, [~lit]) for lit in excluded]
        return ClauseGroup(self._model, clauses)

    def __eq__(self, other):  # type: ignore[override]
        if _is_enum_label(other):
            return self._choice_literal(other)
        if isinstance(other, EnumVar):
            _ensure_same_model_pair_fast(self, other)
            if self.choices != other.choices:
                raise ValueError("Enum equality requires matching choices.")
            if self is other:
                return ClauseGroup(self._model, [])
            clauses: list[Clause] = []
            for choice in self.choices:
                eq = self._choice_lits[choice] == other._choice_lits[choice]
                if eq is True:
                    continue
                if eq is False:
                    clauses.append(Clause(self._model, []))
                    continue
                if isinstance(eq, ClauseGroup):
                    clauses.extend(eq)
                else:
                    raise TypeError("Enum equality expected literal equivalence ClauseGroup.")
            return _EnumRelation(self._model, clauses, lambda: self != other)
        raise _unsupported_comparison_error(self, other)

    def __ne__(self, other):  # type: ignore[override]
        if _is_enum_label(other):
            return ~self._choice_literal(other)
        if isinstance(other, EnumVar):
            _ensure_same_model_pair_fast(self, other)
            if self.choices != other.choices:
                raise ValueError("Enum inequality requires matching choices.")
            if self is other:
                return ClauseGroup(self._model, [Clause(self._model, [])])
            clauses: list[Clause] = []
            # Enforce different chosen value by forbidding pairwise equal choices.
            for choice in self.choices:
                clauses.append(Clause(self._model, [~self._choice_lits[choice], ~other._choice_lits[choice]]))
            # If both are nullable, also forbid the "both none" case.
            if self.nullable and other.nullable:
                lits = [self._choice_lits[c] for c in self.choices] + [other._choice_lits[c] for c in self.choices]
                clauses.append(Clause(self._model, lits))
            return _EnumRelation(self._model, clauses, lambda: self == other)
        raise _unsupported_comparison_error(self, other)


class _EnumRelation(ClauseGroup):
    """Enum comparison retaining its opposite for explicit iff()."""

    __slots__ = ("_opposite",)

    def __init__(self, model: "Model", clauses: Sequence[Clause], opposite: Callable[[], ClauseGroup]):
        super().__init__(model, clauses)
        self._opposite: Callable[[], ClauseGroup] | None = opposite

    def iff(self, indicator: Literal) -> ClauseGroup:
        if self._opposite is None or not self._clauses:
            return super().iff(indicator)
        if not isinstance(indicator, Literal):
            raise _detection_error()
        _ensure_same_model_pair_fast(self, indicator)

        def build() -> ClauseGroup:
            opposite = self._opposite
            if opposite is None:
                return ClauseGroup.iff(self, indicator)._realize()
            return self.only_if(indicator) & opposite().only_if(~indicator)

        return _ReifiableClauseGroup(
            self._model, build, lambda: self.iff(~indicator)._realize()
        )

    def extend(self, other, *, inplace: bool = False) -> ClauseGroup:
        super().extend(other, inplace=inplace)
        self._opposite = None
        return self


class _IndexedInt:
    """Shared deferred comparisons for integer-valued array lookups."""

    __slots__ = ()

    def _evaluate_comparator(self, op: str, rhs) -> ClauseGroup:
        if not (isinstance(rhs, IntVar) or isinstance(rhs, int) and not isinstance(rhs, bool)):
            raise TypeError(f"{self._comparison_label} comparison does not support RHS {type(rhs)!r}")

        def build() -> ClauseGroup:
            if isinstance(rhs, IntVar):
                _ensure_same_model_pair_fast(self, rhs)
            clauses: list[Clause] = []
            idx = self._index_var
            compare = _INTEGER_COMPARISONS[op]
            for k in range(idx.lb, idx.ub + 1):
                branch = compare(self._item_at(k), rhs)
                if isinstance(branch, bool):
                    if not branch:
                        clauses.extend(self._model._as_clausegroup(idx != k))
                    continue
                condition = idx == k
                if isinstance(branch, PBConstraint):
                    clauses.extend(branch.only_if(condition).clauses())
                else:
                    clauses.extend(self._model._as_clausegroup(branch).only_if(condition))
            return ClauseGroup(self._model, clauses)

        return DeferredClauseGroup(self._model, build)

    def __le__(self, rhs):
        return self._evaluate_comparator("<=", rhs)

    def __lt__(self, rhs):
        return self._evaluate_comparator("<", rhs)

    def __ge__(self, rhs):
        return self._evaluate_comparator(">=", rhs)

    def __gt__(self, rhs):
        return self._evaluate_comparator(">", rhs)

    def __eq__(self, rhs):
        return self._evaluate_comparator("==", rhs)

    def __ne__(self, rhs):
        return self._evaluate_comparator("!=", rhs)


class _MultiplexerInt(_IndexedInt):
    """Constant-array lookup whose positions start at the index's lower bound."""

    __slots__ = ("_model", "_array", "_index_var")
    _comparison_label = "Multiplexer"

    def __init__(self, model: "Model", array: Sequence[int], index_var: "IntVar"):
        self._model = model
        if any(isinstance(v, bool) or not isinstance(v, int) for v in array):
            raise TypeError("Multiplexer array must contain integer constants.")
        self._array = tuple(int(v) for v in array)
        self._index_var = index_var

    def _evaluate_comparator(self, op: str, rhs) -> ClauseGroup:
        if isinstance(rhs, int) and not isinstance(rhs, bool):
            compare = _INTEGER_COMPARISONS[op]
            index = self._index_var
            return DeferredClauseGroup(self._model, lambda: index._allowed_values(
                k for k in range(index.lb, index.ub + 1) if compare(self._item_at(k), rhs)
            )._realize())
        return super()._evaluate_comparator(op, rhs)

    def _item_at(self, index: int) -> int:
        return self._array[index - self._index_var.lb]


class _VectorElementInt(_IndexedInt):
    """Integer-vector lookup using zero-based positions."""

    __slots__ = ("_model", "_items", "_index_var")
    _comparison_label = "Vector element"

    def __init__(self, model: "Model", items: Sequence["IntVar"], index_var: "IntVar"):
        self._model = model
        self._items = tuple(items)
        self._index_var = index_var

    def _item_at(self, index: int) -> "IntVar":
        return self._items[index]


class _VectorElementBool(_BooleanComposition):
    """A Boolean lookup over the index's existing threshold bits."""

    __slots__ = ("_items", "_index_var", "_expected")

    def __init__(self, model, items, index, expected=True):
        self._items = tuple(items)
        self._index_var = index
        self._expected = expected
        super().__init__(model, lambda: self._branch_group(expected),
                         lambda: self._branch_group(not expected))

    def _branch_group(self, expected):
        clauses = []
        for value in range(self._index_var.lb, self._index_var.ub + 1):
            guard = [~atom for atom in self._index_var._exact_value_atoms(value)]
            selected = self._items[value]
            clauses.append(Clause(self._model, [*guard, selected if expected else ~selected]))
        return ClauseGroup(self._model, clauses)

    def _compare_constant(self, other, equal):
        if isinstance(other, bool) or not isinstance(other, int):
            raise TypeError("Use .iff(literal) to relate a Boolean lookup to a literal.")
        if other not in (0, 1):
            return _deferred_constant_constraint(self._model, not equal)
        expected = self._expected if bool(other) == equal else not self._expected
        return _VectorElementBool(self._model, self._items, self._index_var, expected)

    def __eq__(self, other):
        return self._compare_constant(other, True)

    def __ne__(self, other):
        return self._compare_constant(other, False)

    def __invert__(self):
        return _VectorElementBool(
            self._model, self._items, self._index_var, not self._expected
        )


class IntVar:
    """Bounded integer variable with ladder/order encoding.

    The domain is ``[lb, ub]`` and includes both bounds.
    """
    __slots__ = ("_model", "name", "lb", "ub", "_threshold_lits", "_eq_lits", "_cmp_cache", "_is_view", "_binary_view")

    def __init__(self, model: "Model", name: str, lb: int, ub: int):
        if (
            isinstance(lb, bool)
            or isinstance(ub, bool)
            or not isinstance(lb, int)
            or not isinstance(ub, int)
        ):
            raise TypeError("lb and ub must be ints")
        if ub < lb:
            raise ValueError("Int domain must satisfy lb <= ub")
        count = ub - lb
        if not count:
            self._initialize(model, name, lb, ub, [], is_view=False)
            return
        start = model._next_id
        if model._inc_state.bound:
            start = max(start, int(model._inc_state.ip_next_vid) + 1)
        thresholds = ThresholdLiterals(model, name, start, count)
        self._initialize(model, name, lb, ub, thresholds, is_view=False)
        model._reserve_literal_ids_up_to(start + count - 1)
        model._intvar_threshold_owner_by_litid.add(self)
        self._add_domain_constraints()

    def _initialize(
        self, model: "Model", name: str, lb: int, ub: int,
        thresholds: Sequence[Literal], *, is_view: bool,
    ) -> None:
        self._model = model
        self.name = name
        self.lb = lb
        self.ub = ub
        self._threshold_lits = thresholds
        self._is_view = is_view
        self._binary_view: tuple[int, ...] | None = None
        self._eq_lits: dict[int, Literal] = {}
        self._cmp_cache: dict[tuple[str, int], Literal] = {}

    def _get_binary_view(self) -> tuple[int, ...]:
        self._binary_view = _binary_view_for(self._encoding_owner())
        return self._binary_view

    def _encoding_owner(self) -> "IntVar":
        if self._is_view and isinstance(self._threshold_lits, ThresholdLiterals):
            return self._model._intvar_threshold_owner_by_litid[self._threshold_lits.start][0]
        return self

    @classmethod
    def _from_offset(cls, source: "IntVar", offset: int, name: str) -> "IntVar":
        model = source._model
        model._reserve_container_name(name)
        out = cls.__new__(cls)
        out._initialize(
            model, name, source.lb + offset, source.ub + offset,
            source._threshold_lits, is_view=True,
        )
        return out

    @classmethod
    def _from_bool(cls, literal: Literal) -> "IntVar":
        """Interpret a literal as 0/1 without allocating or registering bits.

        Ownership belongs to the original integer, if any. In particular,
        polarity-blind threshold ownership must never describe a negated view.
        Equality indicators of views must preserve ownership for the same reason.
        """
        out = cls.__new__(cls)
        label = literal.name if literal.polarity else f"~{literal.name}"
        out._initialize(
            literal._model, f"as_int({label})", 0, 1, [literal], is_view=True,
        )
        return out

    def _add_domain_constraints(self) -> None:
        # Prefix-true unary encoding over (span - 1) bits.
        ts = self._threshold_lits
        if isinstance(ts, ThresholdLiterals):
            self._model._hard.extend(
                Clause._from_dimacs_trusted(self._model, (-(ts.start + i + 1), ts.start + i))
                for i in range(len(ts) - 1)
            )
        else:
            for i in range(len(ts) - 1):
                self._model._hard.append(Clause(self._model, [~ts[i + 1], ts[i]]))

    def _span(self) -> int:
        return self.ub - self.lb + 1

    def lower_bound(self) -> int:
        """Return the current static lower bound of the integer domain.

        The modeling layer uses closed domains ``[lb, ub]``, so this returns
        ``lb`` exactly.
        """
        return self.lb

    def upper_bound(self) -> int:
        """Return the current static upper bound (inclusive) of the integer domain.
        """
        return self.ub

    def _as_pbexpr(self) -> PBExpr:
        # Ladder/order encoding: sum(threshold bits) == (value - lb).
        # To keep true integer arithmetic in mixed PB expressions, we carry
        # the hidden lower-bound offset internally as a PBExpr constant.
        return PBExpr(self._model, [Term(1, lit) for lit in self._threshold_lits], self.lb)

    def __neg__(self):
        return -1 * self

    def __mul__(self, other):
        if isinstance(other, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
            raise _nonlinear_error(self, other)
        if isinstance(other, int) and not isinstance(other, bool):
            if other == 0:
                return PBExpr(self._model, [], 0)
            expr = self._as_pbexpr()
            return PBExpr(self._model, [Term(other * t.coefficient, t.literal) for t in expr.terms], other * expr.constant)
        raise TypeError("Only integer scaling is supported for Int")

    def __rmul__(self, other):
        return self.__mul__(other)

    def __add__(self, other):
        return self._as_pbexpr().__add__(other)

    def __radd__(self, other):
        return PBExpr.from_item(other).__add__(self._as_pbexpr())

    def __sub__(self, other):
        return self._as_pbexpr().__sub__(other)

    def __rsub__(self, other):
        return PBExpr.from_item(other).__sub__(self._as_pbexpr())

    def __floordiv__(self, divisor: int):
        """Return a lazy derived integer expression for ``self // divisor``.

        Realization is delegated to :meth:`Model.floor_div` when the result is
        actually used in a compiled constraint/PB expression.
        """
        if isinstance(divisor, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
            raise _nonlinear_error(self, divisor, op="//")
        if isinstance(divisor, bool):
            raise ValueError("Divisor must be strictly positive.")
        if not isinstance(divisor, int):
            raise TypeError("Divisor must be an integer.")
        if divisor <= 0:
            raise ValueError("Divisor must be strictly positive.")
        return DivExpr(self, divisor)

    def scale(self, factor: int):
        """Return a lazy derived integer expression for ``self * factor``.

        The expression is built by :meth:`Model.scale` when it is used.
        """
        if isinstance(factor, bool):
            raise ValueError("Scale factor must be strictly positive.")
        if not isinstance(factor, int):
            raise TypeError("Scale factor must be an integer.")
        if factor == 0:
            raise ValueError("Scale factor must be nonzero.")
        return ScaleExpr(self, factor)

    def __mod__(self, divisor: int):
        return _LazyIntExpr.__mod__(self, divisor)

    def __rmatmul__(self, array: Sequence[int]) -> "_MultiplexerInt":
        """Create a lazy element-constraint descriptor for ``array @ int_var``.

        The left operand must be a sequence of integer constants whose length
        covers the integer variable domain. Array position ``i`` corresponds to
        domain value ``lb + i``.
        """
        if not isinstance(array, Sequence) or isinstance(array, (str, bytes)):
            raise TypeError("Multiplexer operator (@) requires a sequence of ints on the left.")
        if self.lb < 0:
            raise ValueError("Multiplexer currently requires IntVar.lb >= 0.")
        if len(array) < (self.ub - self.lb + 1):
            raise ValueError(
                f"Array length {len(array)} does not cover IntVar domain [{self.lb}, {self.ub}]."
            )
        vals = list(array[: (self.ub - self.lb + 1)])
        if any(isinstance(v, bool) or not isinstance(v, int) for v in vals):
            raise TypeError("Multiplexer array must contain integer constants.")
        return _MultiplexerInt(self._model, vals, self)

    def piecewise(self, *, base_value: int, steps: Mapping[int, int]) -> PBExpr:
        """Return a lazy PB expression for a step function of this integer variable.

        ``steps`` maps thresholds to the new function value active for all
        assignments ``self >= threshold``.

        Example:
            ``x.piecewise(base_value=10, steps={10: 25, 50: 100})``

        The returned :class:`PBExpr` creates no variables or clauses until it is
        used in a constraint. Negative changes are handled during PB encoding.
        """
        if isinstance(base_value, bool) or not isinstance(base_value, int):
            raise TypeError("piecewise() requires integer base_value")
        if not isinstance(steps, Mapping):
            raise TypeError("piecewise() requires a mapping for steps")

        # Validate and sort user-provided step points.
        norm_steps: list[tuple[int, int]] = []
        for k, v in steps.items():
            if isinstance(k, bool) or not isinstance(k, int):
                raise TypeError("piecewise() step thresholds must be integers")
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError("piecewise() step values must be integers")
            norm_steps.append((k, v))
        norm_steps.sort(key=lambda kv: kv[0])

        current = int(base_value)
        # Fold steps that are always active over the full domain into the base.
        i = 0
        while i < len(norm_steps) and norm_steps[i][0] <= self.lb:
            current = norm_steps[i][1]
            i += 1

        expr = PBExpr(self._model, [], current)

        # Remaining steps can only affect the domain for thresholds in (lb, ub].
        for threshold, new_value in norm_steps[i:]:
            if threshold > self.ub:
                break  # all subsequent thresholds are outside the domain too
            delta = int(new_value) - current
            if delta != 0:
                expr += delta * self.__ge__(threshold)
            current = int(new_value)

        return expr

    def _cmp_lit(self, tag: str, value: int) -> Literal:
        key = (tag, value)
        cache = self._cmp_cache
        if key in cache:
            return cache[key]

        # Map comparisons to threshold literals when possible.
        span = self._span()
        ts = self._threshold_lits

        def const(v: bool) -> Literal:
            return self._model._get_bool_constant_literal(v)

        if tag == "<":
            lit = self._cmp_lit("<=", value - 1)
            cache[key] = lit
            return lit
        if tag == ">":
            lit = self._cmp_lit(">=", value + 1)
            cache[key] = lit
            return lit
        if tag == "<=":
            if value < self.lb:
                lit = const(False)
            elif value >= self.ub:
                lit = const(True)
            else:
                idx = value - self.lb
                lit = ~ts[idx]
            cache[key] = lit
            return lit
        if tag == ">=":
            if value <= self.lb:
                lit = const(True)
            elif value > self.ub:
                lit = const(False)
            else:
                idx = value - self.lb - 1
                lit = ts[idx]
            cache[key] = lit
            return lit
        raise ValueError(f"Unknown comparison tag {tag!r}")

    def _neq_indicator(self, other: "IntVar") -> Literal:
        _ensure_same_model_pair_fast(self, other)
        key = ("!=intvar", id(other))
        if key not in self._cmp_cache:
            d = self._model._predicate_bool(
                lambda result: result[self] != result[other], f"{self.name}!={other.name}"
            )
            # Make the indicator exact: d=true enforces !=, d=false enforces ==.
            neq = self != other
            eq = self == other
            clauses: list[Clause] = []
            if isinstance(neq, ClauseGroup):
                clauses.extend(neq.only_if(d))
            if isinstance(eq, ClauseGroup):
                clauses.extend(eq.only_if(~d))
            if clauses:
                self._model._register_literal_definition(d, ClauseGroup(self._model, clauses))
            self._cmp_cache[key] = d
        return self._cmp_cache[key]

    def _order_implications(self, other: "IntVar", shift: int = 0) -> list[Clause]:
        """Encode self <= other + shift, skipping constant threshold regions."""
        if self._threshold_lits is other._threshold_lits:
            return [] if self.lb <= other.lb + shift else [Clause(self._model, [])]
        if self.ub <= other.lb + shift:
            return []
        if self.lb > other.ub + shift:
            return [Clause(self._model, [])]
        clauses = []
        # The threshold chains propagate each boundary unit through its region.
        if self.lb > other.lb + shift:
            clauses.append(Clause(self._model, [other.__ge__(self.lb - shift)]))
        lo = max(self.lb, other.lb + shift)
        hi = min(self.ub, other.ub + shift)
        for k in range(lo + 1, hi + 1):
            clauses.append(Clause(self._model, [~self.__ge__(k), other.__ge__(k - shift)]))
        if self.ub > other.ub + shift:
            clauses.append(Clause(self._model, [~self.__ge__(other.ub + shift + 1)]))
        return clauses

    def _exact_value_atoms(self, value: int) -> list[Literal]:
        # Compact exact-value pattern over the ladder bits (at most 2 literals,
        # except span=1 where the only value is tautologically true).
        if value < self.lb or value > self.ub:
            raise ValueError(f"value {value} is outside domain [{self.lb}, {self.ub}]")
        span = self._span()
        if span == 1:
            return []
        k = value - self.lb
        ts = self._threshold_lits
        if k == 0:
            return [~ts[0]]
        if k == span - 1:
            return [ts[k - 1]]
        return [ts[k - 1], ~ts[k]]

    def forbid_value(self, value: int) -> Clause:
        """Return a clause forbidding a single value from the domain.

        This exploits the ladder \"cliff\" representation of exact values and
        compiles to a tiny clause (typically binary, unit on boundaries).
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("forbid_value() requires an integer value")
        m = self._model
        if value < self.lb or value > self.ub:
            # Tautological no-op outside the declared domain.
            return Clause(m, [m._get_bool_constant_literal(True)])
        atoms = self._exact_value_atoms(value)
        if not atoms:
            # Singleton domain and forbidding the only value -> contradiction.
            return Clause(m, [])
        return Clause(m, [~lit for lit in atoms])

    def forbid_interval(self, start: int, end: int) -> Clause:
        """Return a clause forbidding all values in the closed interval ``[start, end]``.

        The interval is clipped to the declared integer domain. The resulting
        clause is typically binary, but can collapse to a unit clause, a
        tautology, or a contradiction at boundaries.
        """
        if isinstance(start, bool) or not isinstance(start, int):
            raise TypeError("forbid_interval() requires integer start")
        if isinstance(end, bool) or not isinstance(end, int):
            raise TypeError("forbid_interval() requires integer end")
        m = self._model
        if end < start:
            return Clause(m, [m._get_bool_constant_literal(True)])

        lo = max(start, self.lb)
        hi = min(end, self.ub)
        if hi < lo:
            return Clause(m, [m._get_bool_constant_literal(True)])
        if lo == self.lb and hi == self.ub:
            return Clause(m, [])

        if lo == self.lb:
            return Clause(m, [self >= hi + 1])
        if hi == self.ub:
            return Clause(m, [self < lo])
        return Clause(m, [self < lo, self >= hi + 1])

    def _allowed_values(self, values: Iterable[int]) -> ClauseGroup:
        """Encode membership in validated domain values using forbidden runs."""
        runs = _integer_runs(sorted(set(values)))
        gaps = []
        start = self.lb
        for lo, hi in runs:
            if start < lo:
                gaps.append((start, lo - 1))
            start = hi + 1
        if start <= self.ub:
            gaps.append((start, self.ub))

        def exclude(intervals):
            return ClauseGroup(self._model, [
                self.forbid_interval(lo, hi) for lo, hi in intervals
            ])

        return _ReifiableClauseGroup(
            self._model, lambda: exclude(gaps), lambda: exclude(runs)
        )

    def in_range(self, start: int, end: int) -> Literal:
        """Return a lazy indicator literal for inclusive membership ``start <= x <= end``.

        Helper clauses are registered lazily and are added only when the literal
        is used in a model constraint, export, or solve.
        """
        if isinstance(start, bool) or not isinstance(start, int):
            raise TypeError("in_range() requires integer start")
        if isinstance(end, bool) or not isinstance(end, int):
            raise TypeError("in_range() requires integer end")
        m = self._model

        # Empty requested range.
        if end < start:
            return m._get_bool_constant_literal(False)

        # Clip against domain [lb, ub].
        lo = max(start, self.lb)
        hi = min(end, self.ub)
        if hi < lo:
            return m._get_bool_constant_literal(False)
        if lo == self.lb and hi == self.ub:
            return m._get_bool_constant_literal(True)

        # Common reductions.
        if lo == hi:
            return self == lo
        if lo == self.lb:
            return self <= hi
        if hi == self.ub:
            return self >= lo

        key = ("in_range", lo, hi)
        cache = self._cmp_cache
        if key in cache:
            return cache[key]

        b = m._predicate_bool(
            lambda result: lo <= result[self] <= hi, f"{self.name}∈[{lo},{hi}]"
        )
        ge_lo = self.__ge__(lo)
        ge_hi1 = self.__ge__(hi + 1)

        # b <-> (ge_lo AND ~ge_hi1)
        # constant-folding happens naturally through ge_* simplifications above,
        # but the interior case here should be non-constant by construction.
        group = ClauseGroup(
            m,
            [
                Clause(m, [~b, ge_lo]),
                Clause(m, [~b, ~ge_hi1]),
                Clause(m, [~ge_lo, ge_hi1, b]),
            ],
        )
        m._register_literal_definition(b, group)
        cache[key] = b
        return b

    def distance_at_most(self, other: "IntVar", max_distance: int) -> ClauseGroup:
        """Return a constraint enforcing ``|self - other| <= max_distance``.

        This uses ladder-native implications and introduces no auxiliary
        variables.
        """
        if not isinstance(other, IntVar):
            raise TypeError("distance_at_most() expects IntVar")
        _ensure_same_model_pair_fast(self, other)
        if isinstance(max_distance, bool) or not isinstance(max_distance, int):
            raise TypeError("distance_at_most() requires an integer max_distance")
        if max_distance < 0:
            raise ValueError("max_distance must be >= 0")

        clauses = self._order_implications(other, max_distance)
        clauses.extend(other._order_implications(self, max_distance))
        if any(not clause.dimacs for clause in clauses):
            clauses = [Clause(self._model, [])]
        return ClauseGroup(self._model, clauses)

    def _relop_intvar(self, other: "IntVar", op: str, offset: int = 0) -> ClauseGroup:
        _ensure_same_model_pair_fast(self, other)
        m = self._model

        if op in ("<=", "<", ">=", ">"):
            shift = offset + (op == "<") - (op == ">")
            clauses = (
                self._order_implications(other, -shift)
                if op in ("<=", "<")
                else other._order_implications(self, shift)
            )
            return IntRelation(m, clauses, self, other, op, offset)
        if op == "!=":
            if offset != 0:
                raise ValueError("IntVar '!=' with offset is not supported")
            return self != other
        raise ValueError(f"Unsupported IntVar relation {op!r}")

    def _eq_indicator(self, other: "IntVar") -> Literal:
        _ensure_same_model_pair_fast(self, other)
        key = ("==intvar", id(other))
        if key not in self._cmp_cache:
            e = self._model._predicate_bool(
                lambda result: result[self] == result[other], f"{self.name}=={other.name}"
            )
            neq = self != other
            eq = self == other
            clauses: list[Clause] = []
            if isinstance(eq, ClauseGroup):
                clauses.extend(eq.only_if(e))
            if isinstance(neq, ClauseGroup):
                clauses.extend(neq.only_if(~e))
            if clauses:
                self._model._register_literal_definition(e, ClauseGroup(self._model, clauses))
            self._cmp_cache[key] = e
        return self._cmp_cache[key]

    def __le__(self, value: int):
        if isinstance(value, bool):
            raise TypeError("Int comparisons require an integer or PB-compatible RHS")
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            return self._relop_intvar(value, "<=")
        if isinstance(value, int):
            return self._cmp_lit("<=", value)
        if isinstance(value, (_LazyIntExpr, Literal, Term, PBExpr)):
            _ensure_same_model(self, value)
            return PBExpr.from_item(self)._finalize_compare("<=", value)
        raise TypeError("Int comparisons require an integer or PB-compatible RHS")

    def __lt__(self, value: int):
        if isinstance(value, bool):
            raise TypeError("Int comparisons require an integer or PB-compatible RHS")
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            return self._relop_intvar(value, "<")
        if isinstance(value, int):
            return self._cmp_lit("<", value)
        if isinstance(value, (_LazyIntExpr, Literal, Term, PBExpr)):
            _ensure_same_model(self, value)
            return PBExpr.from_item(self)._finalize_compare("<", value)
        raise TypeError("Int comparisons require an integer or PB-compatible RHS")

    def __ge__(self, value: int):
        if isinstance(value, bool):
            raise TypeError("Int comparisons require an integer or PB-compatible RHS")
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            return self._relop_intvar(value, ">=")
        if isinstance(value, int):
            return self._cmp_lit(">=", value)
        if isinstance(value, (_LazyIntExpr, Literal, Term, PBExpr)):
            _ensure_same_model(self, value)
            return PBExpr.from_item(self)._finalize_compare(">=", value)
        raise TypeError("Int comparisons require an integer or PB-compatible RHS")

    def __gt__(self, value: int):
        if isinstance(value, bool):
            raise TypeError("Int comparisons require an integer or PB-compatible RHS")
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            return self._relop_intvar(value, ">")
        if isinstance(value, int):
            return self._cmp_lit(">", value)
        if isinstance(value, (_LazyIntExpr, Literal, Term, PBExpr)):
            _ensure_same_model(self, value)
            return PBExpr.from_item(self)._finalize_compare(">", value)
        raise TypeError("Int comparisons require an integer or PB-compatible RHS")

    def __eq__(self, value):  # type: ignore[override]
        if isinstance(value, bool):
            raise TypeError("Int comparisons require an integer or PB-compatible RHS")
        if isinstance(value, int):
            if value < self.lb or value > self.ub:
                return _deferred_constant_constraint(self._model, False)
            if value not in self._eq_lits:
                k = value - self.lb
                ts = self._threshold_lits
                owner = self._encoding_owner()
                # Edge cases can reuse direct threshold/constant literals.
                if owner is not self:
                    lit = owner == value - self.lb + owner.lb
                elif self._span() == 1:
                    lit = self._model._get_bool_constant_literal(True)
                elif k == 0:
                    lit = ~ts[0]
                elif k == self._span() - 1:
                    lit = ts[k - 1]
                else:
                    lit = self._model._predicate_bool(
                        lambda result: result[self] == value, f"{self.name}=={value}"
                    )
                    eq_def = ClauseGroup(
                        self._model,
                        [
                            # lit -> pattern
                            Clause(self._model, [~lit, ts[k - 1]]),
                            Clause(self._model, [~lit, ~ts[k]]),
                            # pattern -> lit
                            Clause(self._model, [~ts[k - 1], ts[k], lit]),
                        ],
                    )
                    self._model._register_literal_definition(lit, eq_def)
                self._eq_lits[value] = lit
                if self._span() > 1 and not self._is_view:
                    self._model._intvar_eq_owner_by_litid[self._model._lit_to_dimacs(lit)] = (self, int(value))
            return self._eq_lits[value]
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            clauses = self._order_implications(value)
            clauses.extend(value._order_implications(self))
            if any(not clause.dimacs for clause in clauses):
                clauses = [Clause(self._model, [])]
            return IntRelation(self._model, clauses, self, value, "==", 0)
        result = _compare_pb_operands(self, "==", value)
        if result is NotImplemented:
            raise _unsupported_comparison_error(self, value)
        return result

    def __ne__(self, value):  # type: ignore[override]
        if isinstance(value, bool):
            raise TypeError("Int comparisons require an integer or PB-compatible RHS")
        if isinstance(value, int):
            if value < self.lb or value > self.ub:
                return _deferred_constant_constraint(self._model, True)
            return ~(self == value)
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            if self._threshold_lits is value._threshold_lits:
                clauses = [] if self.lb != value.lb else [Clause(self._model, [])]
                return IntRelation(self._model, clauses, self, value, "!=", 0)
            clauses: list[Clause] = []
            lo = max(self.lb, value.lb)
            hi = min(self.ub, value.ub)
            for v in range(lo, hi + 1):
                # No-new-vars linear encoding: forbid "self == v and other == v"
                # using compact exact-value boundary patterns (clause size <= 4).
                atoms = [*self._exact_value_atoms(v), *value._exact_value_atoms(v)]
                clauses.append(Clause(self._model, [~lit for lit in atoms]))
            return IntRelation(self._model, clauses, self, value, "!=", 0)
        result = _compare_pb_operands(self, "!=", value)
        if result is NotImplemented:
            raise _unsupported_comparison_error(self, value)
        return result


class IntervalVar:
    """Fixed-duration interval variable for scheduling-style constraints.

    The constructor binds two :class:`IntVar` objects, ``start`` and ``end``,
    and enforces ``end == start + duration``. Public horizon is:

    * ``start`` argument = earliest start (inclusive)
    * ``end`` argument = latest end (inclusive)
    """

    __slots__ = ("_model", "name", "start", "end", "duration", "earliest_start", "latest_end")

    def __init__(self, model: "Model", name: str, *, start: int, duration: int, end: int):
        if (
            isinstance(start, bool)
            or isinstance(duration, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(duration, int)
            or not isinstance(end, int)
        ):
            raise TypeError("Interval bounds and duration must be ints")
        if duration <= 0:
            raise ValueError("Interval duration must be positive")
        if end < start + duration:
            raise ValueError("Interval horizon is too small for the given duration")
        self._model = model
        self.name = name
        self.duration = duration
        self.earliest_start = start
        self.latest_end = end

        # start domain is [start, end - duration] so that start+duration <= end
        start_ub = end - duration
        self.start = model.int(f"{name}.start", lb=start, ub=start_ub)
        self.end = IntVar._from_offset(self.start, duration, f"{name}.end")

    def ends_before(self, other: "IntervalVar") -> ClauseGroup:
        """Return constraint enforcing ``self.end <= other.start``."""
        if not isinstance(other, IntervalVar):
            raise TypeError("ends_before expects IntervalVar")
        _ensure_same_model_pair_fast(self, other)
        return self.end._relop_intvar(other.start, "<=")

    def starts_after(self, other: "IntervalVar") -> ClauseGroup:
        """Return constraint enforcing ``self.start >= other.end``."""
        if not isinstance(other, IntervalVar):
            raise TypeError("starts_after expects IntervalVar")
        _ensure_same_model_pair_fast(self, other)
        return self.start._relop_intvar(other.end, ">=")

    def no_overlap(self, other: "IntervalVar") -> ClauseGroup:
        """Return disjunctive non-overlap: ``self`` before ``other`` OR vice versa."""
        if not isinstance(other, IntervalVar):
            raise TypeError("no_overlap expects IntervalVar")
        _ensure_same_model_pair_fast(self, other)
        if other is self:
            return _deferred_constant_constraint(self._model, False)
        def _build() -> ClauseGroup:
            key = ("interval_no_overlap_sel", _Identity(self), _Identity(other))
            sel = self._model.canonical_internal_bool(key)
            left = self.ends_before(other).only_if(sel)
            right = other.ends_before(self).only_if(~sel)
            return left & right
        def _build_negative() -> ClauseGroup:
            return (self.start < other.end) & (other.start < self.end)

        return _ReifiableClauseGroup(self._model, _build, _build_negative)


def _validate_element_index(vector, index):
    _ensure_same_model_pair_fast(vector, index)
    kind = type(vector).__name__
    if index.lb < 0:
        raise ValueError(f"{kind}[IntVar] currently requires index.lb >= 0.")
    if index.ub >= len(vector._items):
        raise ValueError(f"{kind} length {len(vector._items)} does not cover index domain [{index.lb}, {index.ub}].")


class _BaseVector:
    """Base class for typed immutable vector containers."""
    __slots__ = ("_model", "name", "_items")
    _item_type = object

    def __init__(self, model: "Model", name: str, items: Sequence):
        self._model = model
        self.name = name
        self._items = tuple(items)
        expected = type(self)._item_type
        for item in self._items:
            if not isinstance(item, expected):
                raise TypeError(f"{type(self).__name__} expects items of type {expected.__name__}")
            if item._model is not model:
                raise ValueError("Vector items must belong to the same model.")

    def __len__(self):
        return len(self._items)

    def __getitem__(self, i):
        return list(self._items[i]) if isinstance(i, slice) else self._items[i]

    def __iter__(self):
        return iter(self._items)

    def _table_cell_constraint(self, item, value):
        raise NotImplementedError

    def _validate_table_cell(self, item, value) -> None:
        """Validate one table cell without allocating helper literals."""
        return None

    def _normalize_table_row(self, row):
        return tuple(row)

    def is_in(self, rows: Sequence[Sequence]):
        """Return an extensional (allowed-combinations) table constraint.

        This is the fluent convenience form of :meth:`Model.table`; the
        model-level method is the canonical API because it also supports mixed
        typed columns.
        """
        return self._model.table(self._items, allowed=rows)

    def _all_different_pairwise(self) -> ClauseGroup:
        clauses: list[tuple[int, ...]] = []
        for i, left in enumerate(self._items):
            for right in self._items[i + 1:]:
                clauses.extend(left != right)
        return ClauseGroup._from_dimacs_trusted(self._model, clauses)

    def _not_all_different(self) -> ClauseGroup:
        clauses: list[tuple[int, ...]] = []
        witnesses: list[Literal] = []
        for i, left in enumerate(self._items):
            for right in self._items[i + 1:]:
                if left is right:
                    return ClauseGroup(self._model, [])
                if isinstance(left, IntVar) and (left.ub < right.lb or right.ub < left.lb):
                    continue
                witness = self._model.bool()
                # A witness need only establish equality, not detect it in both directions.
                clauses.extend((left == right).only_if(witness))
                witnesses.append(witness)
        clauses.append(tuple(self._model._lit_to_dimacs(w) for w in witnesses))
        return ClauseGroup._from_dimacs_trusted(self._model, clauses)


class _BaseDict:
    """Base class for typed immutable keyed containers."""
    __slots__ = ("_model", "name", "_map")
    _item_type = object

    def __init__(self, model: "Model", name: str, mapping: dict):
        self._model = model
        self.name = name
        self._map = dict(mapping)
        expected = type(self)._item_type
        for item in self._map.values():
            if not isinstance(item, expected):
                raise TypeError(f"{type(self).__name__} expects values of type {expected.__name__}")
            if item._model is not model:
                raise ValueError("Dictionary values must belong to the same model.")

    def __getitem__(self, key):
        return self._map[key]

    def __iter__(self):
        return iter(self._map)

    def items(self):
        """Return ``(key, value)`` pairs."""
        return self._map.items()

    def keys(self):
        """Return dictionary keys."""
        return self._map.keys()

    def values(self):
        """Return dictionary values."""
        return self._map.values()

    def __len__(self):
        return len(self._map)


class BoolVector(_BaseVector):
    """Vector of Boolean literals."""
    _item_type = Literal

    def __getitem__(self, index):
        if isinstance(index, IntVar):
            _validate_element_index(self, index)
            return _VectorElementBool(self._model, self._items, index)
        return super().__getitem__(index)

    def at_most_one(self):
        """Return a cardinality constraint enforcing at most one true literal."""
        if not self._items:
            return _deferred_constant_constraint(self._model, True)
        return sum_expr(self._items) <= 1

    def exactly_one(self):
        """Return a cardinality constraint enforcing exactly one true literal."""
        if not self._items:
            return _deferred_constant_constraint(self._model, False)
        return sum_expr(self._items) == 1

    def at_least_one(self):
        """Return a single clause enforcing at least one true literal."""
        if not self._items:
            return Clause(self._model, [])
        return Clause.from_iterable(self._items)

    def _table_cell_constraint(self, item, value):
        if not isinstance(value, bool):
            raise TypeError("BoolVector.is_in() rows must contain booleans.")
        return item if value else ~item

    def _validate_table_cell(self, item, value) -> None:
        if not isinstance(value, bool):
            raise TypeError("BoolVector.is_in() rows must contain booleans.")

    def __mul__(self, other):
        """Return a weighted PB expression from vector literals.

        Supported forms:
            ``bool_vector * [w1, w2, ...]``
            ``bool_vector * (w1, w2, ...)``
        """
        if not isinstance(other, (list, tuple)):
            raise TypeError("BoolVector multiplication expects a list/tuple of integer weights.")
        if len(other) != len(self._items):
            raise ValueError("Weights length must match BoolVector length.")
        terms: list[Term] = []
        for lit, w in zip(self._items, other):
            if isinstance(w, bool) or not isinstance(w, int):
                raise TypeError("All BoolVector weights must be integers (bool is not allowed).")
            if w == 0:
                continue
            terms.append(Term(int(w), lit))
        return PBExpr(self._model, terms, 0)

    def __rmul__(self, other):
        return self.__mul__(other)


class EnumVector(_BaseVector):
    """Vector of :class:`EnumVar` values."""
    _item_type = EnumVar

    def _table_cell_constraint(self, item, value):
        if value is None:
            if not item.nullable:
                raise ValueError("EnumVector.is_in() row uses None for non-nullable enum.")
            return ClauseGroup(item._model, [Clause(item._model, [~lit]) for lit in item._choice_lits.values()])
        item._choice_literal(value)
        return item == value

    def _validate_table_cell(self, item, value) -> None:
        if value is None:
            if not item.nullable:
                raise ValueError("EnumVector.is_in() row uses None for non-nullable enum.")
            return
        item._choice_literal(value)

    def _all_different_bipartite(self) -> ClauseGroup:
        clauses: list[Clause] = []
        amo_groups: list[list[int]] = []
        if not self._items:
            return ClauseGroup(self._model, clauses, amo_groups=amo_groups)
        def columns():
            for label in self._items[0].choices:
                yield [item._choice_lits[label] for item in self._items]
            nullable = [item for item in self._items if item.nullable]
            if len(nullable) > 1:
                yield [item._none_indicator() for item in nullable]

        for col_lits in columns():
            col = BoolVector(self._model, f"{self.name}.column", col_lits)
            clauses.extend(self._model._as_clausegroup(col.at_most_one()))
            amo_groups.append([self._model._lit_to_dimacs(lit) for lit in col_lits])
        return ClauseGroup(self._model, clauses, amo_groups=amo_groups)

    def all_different(self, backend: str = "auto") -> ClauseGroup:
        """Return an all-different constraint supporting ``.iff()`` and ``.implies()``.

        Backends:
            ``auto`` (default): pairwise for nullable enums, otherwise column-wise AMO.
            ``bipartite``: column-wise AMO, including the nullable ``None`` value.
            ``pairwise``: pairwise enum inequality constraints.
        """
        if backend == "auto":
            backend = "pairwise" if any(item.nullable for item in self._items) else "bipartite"
        if backend == "pairwise":
            builder = self._all_different_pairwise
        elif backend == "bipartite":
            builder = self._all_different_bipartite
        elif backend == "sorting":
            raise ValueError("sorting backend is not supported for EnumVector.all_different().")
        else:
            raise ValueError("Unknown all_different backend.")
        if self._items and any(ev.choices != self._items[0].choices for ev in self._items[1:]):
            raise ValueError("EnumVector.all_different() requires matching enum choices.")
        return _ReifiableClauseGroup(self._model, builder, self._not_all_different)


class IntSetVector(_BaseVector):
    """Vector of :class:`IntSetVar` values."""

    _item_type = IntSetVar

    @staticmethod
    def _normalize_set_value(value) -> frozenset[int]:
        return frozenset(IntSetVar._coerce_constant_values(value))

    def _normalize_table_row(self, row):
        return tuple(self._normalize_set_value(v) for v in row)

    def _validate_table_cell(self, item, value) -> None:
        self._normalize_set_value(value)

    def _table_cell_constraint(self, item, value):
        return item == self._normalize_set_value(value)

    def is_in(self, rows: Sequence[Sequence]):
        """Return an allowed-combinations table over integer-set values."""
        norm_rows: list[tuple] = []
        seen = set()
        for raw_row in rows:
            row = tuple(raw_row)
            if len(row) != len(self._items):
                raise ValueError("Table rows must match vector length.")
            normalized = self._normalize_table_row(row)
            if any(value not in item._member_lits
                   for item, values in zip(self._items, normalized) for value in values):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            norm_rows.append(normalized)
        if not norm_rows:
            return _deferred_constant_constraint(self._model, False)

        def _row_atoms(row):
            for item, values in zip(self._items, row):
                for value, literal in item._member_lits.items():
                    yield literal if value in values else ~literal

        def _build() -> ClauseGroup:
            selectors = [self._model.bool() for _ in norm_rows]
            clauses = [Clause(self._model, selectors)]
            for selector, row in zip(selectors, norm_rows):
                clauses.extend(Clause(self._model, [~selector, atom]) for atom in _row_atoms(row))
            return ClauseGroup(self._model, clauses)

        def _build_negative() -> ClauseGroup:
            return ClauseGroup(self._model, [
                Clause(self._model, [~atom for atom in _row_atoms(row)]) for row in norm_rows
            ])

        return _ReifiableClauseGroup(self._model, _build, _build_negative)


@cached_operation(normalize={"items": tuple})
def _running_aggregate(model, items, kind, name=None):
    if not items:
        raise ValueError(f"Cannot compute running_{kind} of an empty IntVector.")
    out_name = model._reserve_name(name)
    model._assert_names_available(
        out_name, *(f"{out_name}[{i}]" for i in range(1, len(items)))
    )
    model._reserve_container_name(out_name)
    out = [items[0]]
    for i, item in enumerate(items[1:], start=1):
        step_name = f"{out_name}[{i}]"
        previous = out[-1]
        if kind == "sum":
            step = model.int(step_name, previous.lb + item.lb, previous.ub + item.ub)
            model &= step == previous + item
        elif kind == "max":
            step = model.max([previous, item], name=step_name)
        else:
            step = model.min([previous, item], name=step_name)
        out.append(step)
    return IntVector(model, out_name, out)


class IntVector(_BaseVector):
    """Vector of :class:`IntVar` values with common global helpers."""
    _item_type = IntVar

    def _table_cell_constraint(self, item, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("IntVector.is_in() rows must contain integers.")
        return item == value

    def _validate_table_cell(self, item, value) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("IntVector.is_in() rows must contain integers.")

    def __getitem__(self, i):
        """Return item/slice, or a variable-index element view.

        For ``vec[idx]`` with ``idx`` as :class:`IntVar`, the index domain must
        satisfy:
            * ``idx.lb >= 0``
            * ``idx.ub < len(vec)``
        """
        if isinstance(i, IntVar):
            _validate_element_index(self, i)
            return _VectorElementInt(self._model, self._items, i)
        return super().__getitem__(i)

    def max(self, name: Optional[str] = None):
        """Create and return an ``IntVar`` equal to the maximum of the vector.

        This is encoded directly on ladder threshold bits (bitwise OR across
        ``x >= k`` predicates), avoiding PB/cardinality encoders.
        """
        if not self._items:
            raise ValueError("Cannot compute max of an empty IntVector.")
        if len(self._items) == 1:
            return self._items[0]
        return MaxExpr(self._model, self._items, "max", name=name)

    def min(self, name: Optional[str] = None):
        """Create and return an ``IntVar`` equal to the minimum of the vector.

        This is encoded directly on ladder threshold bits (bitwise AND across
        ``x >= k`` predicates), avoiding PB/cardinality encoders.
        """
        if not self._items:
            raise ValueError("Cannot compute min of an empty IntVector.")
        if len(self._items) == 1:
            return self._items[0]
        return MaxExpr(self._model, self._items, "min", name=name)

    def upper_bound(self, name: Optional[str] = None):
        """Create an ``IntVar`` constrained to be >= every element in the vector.

        It is cheaper than :meth:`max` because it emits only the clauses needed
        for the upper bound.
        """
        if not self._items:
            raise ValueError("Cannot compute upper_bound of an empty IntVector.")
        return MaxExpr(self._model, self._items, "upper_bound", name=name)

    def lower_bound(self, name: Optional[str] = None):
        """Create an ``IntVar`` constrained to be <= every element in the vector.

        It is cheaper than :meth:`min` because it emits only the clauses needed
        for the lower bound.
        """
        if not self._items:
            raise ValueError("Cannot compute lower_bound of an empty IntVector.")
        return MaxExpr(self._model, self._items, "lower_bound", name=name)

    def running_max(self, name: Optional[str] = None) -> "IntVector":
        """Return prefix maxima as an ``IntVector``.

        ``out[i]`` equals ``max(self[:i+1])``. Values are built cumulatively.
        """
        return _running_aggregate(self._model, self._items, "max", name=name)

    def running_min(self, name: Optional[str] = None) -> "IntVector":
        """Return prefix minima as an ``IntVector``.

        ``out[i]`` equals ``min(self[:i+1])`` and is built cumulatively.
        """
        return _running_aggregate(self._model, self._items, "min", name=name)

    def running_sum(self, name: Optional[str] = None) -> "IntVector":
        """Return prefix sums as an ``IntVector``.

        ``out[i]`` equals ``sum(self[:i+1])``. Each step uses one fresh integer
        variable.
        """
        return _running_aggregate(self._model, self._items, "sum", name=name)

    def _all_different_bipartite_domain(self) -> tuple[int, int]:
        if not self._items:
            return (0, -1)
        # Require a common domain for the current implementation.
        lb = self._items[0].lb
        ub = self._items[0].ub
        for x in self._items[1:]:
            if x.lb != lb or x.ub != ub:
                raise ValueError("IntVector.bipartite all_different currently requires a common domain.")
        if (ub - lb + 1) < len(self._items):
            raise ValueError("IntVector.bipartite all_different requires domain size >= vector length.")
        return lb, ub

    def _all_different_bipartite(self) -> ClauseGroup:
        lb, ub = self._all_different_bipartite_domain()
        clauses: list[Clause] = []
        amo_groups: list[list[int]] = []
        if self._model._inc_state.bound:
            self._model._reserve_literal_ids_up_to(int(self._model._inc_state.ip_next_vid))
        for v in range(lb, ub + 1):
            col = [self._model._lit_to_dimacs(x == v) for x in self._items]
            cnf = CardEnc.atmost(lits=col, bound=1, top_id=self._model._top_id(), encoding=CardEncType.seqcounter)
            clauses.extend(self._model._cnfplus_to_clausegroup(cnf))
            amo_groups.append(col)
        return ClauseGroup(self._model, clauses, amo_groups=amo_groups)

    def all_different(self, backend: str = "auto") -> ClauseGroup:
        """Return an all-different constraint supporting ``.iff()`` and ``.implies()``.

        Backends:
            ``auto`` (default): bipartite for 32+ inputs sharing a supported domain; otherwise pairwise.
            ``pairwise``: pairwise integer inequality constraints.
            ``bipartite``: channel to exact-value indicators + column AMOs.
        """
        if backend == "auto":
            common_domain = len(self) >= 32 and all(
                (x.lb, x.ub) == (self[0].lb, self[0].ub) for x in self
            )
            backend = ("bipartite" if common_domain and self[0].ub - self[0].lb + 1 >= len(self)
                       else "pairwise")
        if backend == "pairwise":
            builder = self._all_different_pairwise
        elif backend == "bipartite":
            self._all_different_bipartite_domain()
            builder = self._all_different_bipartite
        else:
            raise ValueError("Unknown all_different backend.")
        return _ReifiableClauseGroup(self._model, builder, self._not_all_different)

    def increasing(self) -> ClauseGroup:
        """Return nondecreasing chain constraints ``x[i] <= x[i+1]``."""
        clauses: list[Clause] = []
        for i in range(len(self._items) - 1):
            rel = self._items[i]._relop_intvar(self._items[i + 1], "<=")
            clauses.extend(rel)
        return ClauseGroup(self._model, clauses)

    def lexicographic_less_than(self, other: "IntVector") -> ClauseGroup:
        """Return strict lexicographic ordering constraint ``self <lex other``."""
        if not isinstance(other, IntVector):
            raise TypeError("lexicographic_less_than expects IntVector")
        _ensure_same_model_pair_fast(self, other)
        if len(self) != len(other):
            raise ValueError("Vector lengths differ")
        if len(self) == 0:
            return _deferred_constant_constraint(self._model, False)

        def definition(root: Literal) -> ClauseGroup:
            # Each signal describes the strict comparison of its remaining suffix.
            flags = [root] + [self._model.fresh_internal_bool() for _ in self._items[1:]]
            clauses = []
            for i, (left, right) in enumerate(zip(self._items, other._items)):
                signal = flags[i]
                if i + 1 == len(flags):
                    clauses.extend((left < right).only_if(signal))
                    clauses.extend((left >= right).only_if(~signal))
                else:
                    following = flags[i + 1]
                    clauses.extend((left <= right).only_if(signal))
                    clauses.extend((left >= right).only_if(~signal))
                    clauses.extend((left < right).only_if(signal).only_if(~following))
                    clauses.extend((left > right).only_if(~signal).only_if(following))
            return ClauseGroup(self._model, clauses)

        def indicator() -> Literal:
            return self._model.canonical_internal_bool(
                ("lex_suffix", _Identity(self), _Identity(other)), definition=definition
            )

        def _build() -> ClauseGroup:
            return ClauseGroup(self._model, [Clause(self._model, [indicator()])])

        def _build_negative() -> ClauseGroup:
            return ClauseGroup(self._model, [Clause(self._model, [~indicator()])])

        return _ReifiableClauseGroup(self._model, _build, _build_negative)

    def __eq__(self, other):  # type: ignore[override]
        raise TypeError("Vector equality is ambiguous; use explicit methods.")

    def __le__(self, other):
        raise TypeError("Vector ordering is ambiguous; use lexicographic_less_than().")

    def __ne__(self, other):  # type: ignore[override]
        if not isinstance(other, IntVector):
            raise _unsupported_comparison_error(self, other)
        _ensure_same_model_pair_fast(self, other)
        if len(self) != len(other):
            raise ValueError("Vector lengths differ")
        if not self:
            return _deferred_constant_constraint(self._model, False)
        def _build() -> ClauseGroup:
            diff_clause = Clause.from_iterable(
                [self[i]._neq_indicator(other[i]) for i in range(len(self))]
            )
            return ClauseGroup(self._model, [diff_clause])

        return DeferredClauseGroup(self._model, _build)


class BoolDict(_BaseDict):
    """Keyed mapping from user keys to Boolean literals."""
    _item_type = Literal


class EnumDict(_BaseDict):
    """Keyed mapping from user keys to :class:`EnumVar` values."""
    _item_type = EnumVar


class IntDict(_BaseDict):
    """Keyed mapping from user keys to :class:`IntVar` values."""
    _item_type = IntVar


class IntSetDict(_BaseDict):
    """Keyed mapping from user keys to :class:`IntSetVar` values."""

    _item_type = IntSetVar


class _BaseMatrixView:
    """Typed matrix view supporting NumPy-like slicing and flattening."""
    __slots__ = ("_model", "name", "_grid", "_rows", "_cols")
    _vector_type = _BaseVector
    _matrix_view_type = None

    def __init__(self, model: "Model", name: str, grid: Sequence[Sequence]):
        self._model = model
        self.name = name
        # Keep a view over the provided grid. This avoids a full matrix copy on
        # every indexing call from matrix containers.
        self._grid = grid
        self._rows = len(self._grid)
        self._cols = len(self._grid[0]) if self._rows else 0

    def row(self, r: int):
        """Return row ``r`` as a typed vector view."""
        return self._vector_type(self._model, f"{self.name}.row({r})", self._grid[r])

    def col(self, c: int):
        """Return column ``c`` as a typed vector view."""
        return self._vector_type(self._model, f"{self.name}.col({c})", [self._grid[r][c] for r in range(self._rows)])

    def flatten(self):
        """Return all cells in row-major order as a typed vector view."""
        return self._vector_type(
            self._model,
            f"{self.name}.flatten()",
            [x for row in self._grid for x in row],
        )

    def _slice_range(self, s: slice, n: int) -> range:
        return range(*s.indices(n))

    def __getitem__(self, key):
        if isinstance(key, int):
            # Allow chained indexing: matrix[i][j].
            return self.row(key)
        if isinstance(key, tuple) and len(key) == 2:
            rk, ck = key
            if isinstance(rk, int) and isinstance(ck, int):
                return self._grid[rk][ck]
            if isinstance(rk, int) and isinstance(ck, IntVar) and self._vector_type is IntVector:
                return self.row(rk)[ck]
            if isinstance(rk, int) and isinstance(ck, slice):
                cols = self._slice_range(ck, self._cols)
                return self._vector_type(self._model, f"{self.name}[{rk},:]", [self._grid[rk][c] for c in cols])
            if isinstance(rk, slice) and isinstance(ck, int):
                rows = self._slice_range(rk, self._rows)
                return self._vector_type(self._model, f"{self.name}[:,{ck}]", [self._grid[r][ck] for r in rows])
            if isinstance(rk, slice) and isinstance(ck, slice):
                rows = self._slice_range(rk, self._rows)
                cols = self._slice_range(ck, self._cols)
                sub = [[self._grid[r][c] for c in cols] for r in rows]
                return self._matrix_view_type(self._model, f"{self.name}[{rk},{ck}]", sub)
            raise TypeError("Matrix indices must be ints or slices.")
        raise TypeError("Use matrix[row, col] or matrix[row][col] indexing for matrix access.")


class IntMatrixView(_BaseMatrixView):
    _vector_type = IntVector
    _matrix_view_type = None


class BoolMatrixView(_BaseMatrixView):
    _vector_type = BoolVector
    _matrix_view_type = None


class EnumMatrixView(_BaseMatrixView):
    _vector_type = EnumVector
    _matrix_view_type = None


class IntMatrix(_BaseMatrixView):
    """Dense matrix of :class:`IntVar` cells."""
    __slots__ = ()
    _vector_type = IntVector
    _matrix_view_type = IntMatrixView

    def __init__(self, model: "Model", name: str, rows: int, cols: int, lb: int, ub: int):
        self._model = model
        self.name = name
        self._rows = rows
        self._cols = cols
        self._grid = [
            [model.int(f"{name}[{r},{c}]", lb=lb, ub=ub) for c in range(cols)]
            for r in range(rows)
        ]


class BoolMatrix(_BaseMatrixView):
    """Dense matrix of Boolean literals."""
    __slots__ = ()
    _vector_type = BoolVector
    _matrix_view_type = BoolMatrixView

    def __init__(self, model: "Model", name: str, rows: int, cols: int):
        self._model = model
        self.name = name
        self._rows = rows
        self._cols = cols
        self._grid = [
            [model.bool(f"{name}[{r},{c}]") for c in range(cols)]
            for r in range(rows)
        ]


class EnumMatrix(_BaseMatrixView):
    """Dense matrix of :class:`EnumVar` cells."""
    __slots__ = ()
    _vector_type = EnumVector
    _matrix_view_type = EnumMatrixView

    def __init__(self, model: "Model", name: str, rows: int, cols: int, choices: Sequence[str | int], nullable: bool = False):
        self._model = model
        self.name = name
        self._rows = rows
        self._cols = cols
        self._grid = [
            [model.enum(f"{name}[{r},{c}]", choices=choices, nullable=nullable) for c in range(cols)]
            for r in range(rows)
        ]


class AssignmentView:
    """Decoded view over a raw SAT/MaxSAT model for a specific :class:`Model`."""
    __slots__ = ("_model", "_raw_model", "_true_vars", "_top_id")

    def __init__(self, model: "Model", raw_model: Sequence[int]):
        self._model = model
        self._top_id = model._top_id()
        normalized: list[int] = []
        truth: dict[int, bool] = {}
        for raw_lit in raw_model:
            if isinstance(raw_lit, bool) or not isinstance(raw_lit, int):
                raise TypeError("Raw model literals must be integers.")
            lit = int(raw_lit)
            if lit == 0:
                raise ValueError("Raw model contains literal 0.")
            var_id = abs(lit)
            if var_id in truth:
                raise ValueError("Raw model contains duplicate or contradictory literals.")
            truth[var_id] = lit > 0
            normalized.append(lit)
        self._raw_model = normalized
        self._true_vars = truth

    @property
    def raw(self) -> list[int]:
        """Return a copy of the raw solver model literals."""
        return list(self._raw_model)

    def val(self, obj: Any) -> Any:
        """Decode a variable, expression, or nested container from this assignment."""
        owner = getattr(obj, "_model", None)
        if owner is not None and owner is not self._model:
            raise ValueError("Decoded objects must belong to the same model.")
        if isinstance(obj, Literal):
            return self._decode_literal(obj)
        if isinstance(obj, IntVar):
            return self._decode_integer(obj)
        if isinstance(obj, (Term, PBExpr, _LazyIntExpr, _MultiplexerInt,
                            _VectorElementBool, _VectorElementInt)):
            return self._evaluate_expression(obj)
        if isinstance(obj, EnumVar):
            return next((choice for choice in obj.choices
                         if self.val(obj._choice_lits[choice])), None)
        if isinstance(obj, IntSetVar):
            return {v for v in obj.universe if self.val(obj._member_lits[v])}
        if isinstance(obj, _BaseVector):
            return [self.val(x) for x in obj]
        if isinstance(obj, (_BaseMatrixView, IntMatrix, BoolMatrix, EnumMatrix)):
            return [[self.val(x) for x in row] for row in obj._grid]
        if isinstance(obj, (_BaseDict, dict)):
            return {key: self.val(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self.val(x) for x in obj]
        if isinstance(obj, tuple):
            return tuple(self.val(x) for x in obj)
        if isinstance(obj, IntervalVar):
            return {"start": self.val(obj.start), "end": self.val(obj.end),
                    "duration": obj.duration}
        raise TypeError(f"Unsupported decode target: {type(obj)!r}")

    def _check_snapshot(self, var_id: int) -> None:
        if var_id > self._top_id:
            raise ValueError("Cannot decode a variable created after this saved assignment.")

    def _decode_literal(self, literal: Literal) -> bool:
        truth = self._true_vars.get(literal.id)
        if truth is None or literal.id > self._top_id:
            if isinstance(literal, _PredicateLiteral):
                truth = bool(literal._evaluate(self))
            else:
                for value, constant in self._model._const_lits.items():
                    if constant.id == literal.id:
                        truth = value
                        break
                else:
                    self._check_snapshot(literal.id)
                    truth = False
        return truth if literal.polarity else not truth

    def _decode_integer(self, integer: IntVar) -> int:
        bits = integer._threshold_lits
        if isinstance(bits, ThresholdLiterals):
            self._check_snapshot(bits.start)
        for value, literal in integer._eq_lits.items():
            # Later helpers may reuse IDs belonging to old solver auxiliaries.
            if literal.id <= self._top_id and literal.id in self._true_vars and self.val(literal):
                return value
        count = self._count_thresholds(bits)
        return min(integer.lb + count, integer.ub)

    def _count_thresholds(self, bits: Sequence[Literal]) -> int:
        if not isinstance(bits, ThresholdLiterals):
            return sum(1 for literal in bits if self.val(literal))
        end = bits.start + len(bits)
        if len(bits) <= len(self._true_vars):
            count = sum(bool(self._true_vars.get(var_id))
                        for var_id in range(bits.start, end))
        else:
            count = sum(1 for var_id, truth in self._true_vars.items()
                        if truth and bits.start <= var_id < end)
        # Preserve the behavior of exposed literal objects if they were modified.
        for index, literal in bits._cache.items():
            original_id = bits.start + index
            if literal.id != original_id or not literal.polarity:
                count -= bool(self._true_vars.get(original_id))
                truth = bool(self._true_vars.get(literal.id))
                count += truth if literal.polarity else not truth
        return count

    def _evaluate_expression(self, expression):
        if isinstance(expression, Term):
            return expression.coefficient * self.val(expression.literal)
        if isinstance(expression, PBExpr):
            return (expression.constant + sum(term.coefficient * self.val(term.literal)
                                              for term in expression.terms)
                    + sum(coefficient * self.val(value)
                          for coefficient, value in expression.int_terms))
        if isinstance(expression, DivExpr):
            return self.val(expression._src) // expression._divisor
        if isinstance(expression, ModExpr):
            return self.val(expression._src) % expression._divisor
        if isinstance(expression, ScaleExpr):
            return self.val(expression._src) * expression._factor
        if isinstance(expression, MaxExpr):
            realized = expression._realized
            if expression._kind in {"upper_bound", "lower_bound"} and realized is not None:
                if realized.lb == realized.ub or realized._threshold_lits[0].id <= self._top_id:
                    return self.val(realized)
            values = [self.val(x) for x in expression._items]
            return max(values) if expression._kind in {"max", "upper_bound"} else min(values)
        if isinstance(expression, _MultiplexerInt):
            index = self.val(expression._index_var) - expression._index_var.lb
            return expression._array[index]
        if isinstance(expression, _VectorElementBool):
            value = self.val(expression._items[self.val(expression._index_var)])
            return value if expression._expected else not value
        if isinstance(expression, _VectorElementInt):
            return self.val(expression._items[self.val(expression._index_var)])
        raise TypeError(f"Unsupported decode target: {type(expression)!r}")

    def __getitem__(self, obj: Any) -> Any:
        """Alias for :meth:`val` allowing indexed access ``result[my_var]``."""
        return self.val(obj)



IntMatrixView._matrix_view_type = IntMatrixView

BoolMatrixView._matrix_view_type = BoolMatrixView

EnumMatrixView._matrix_view_type = EnumMatrixView
