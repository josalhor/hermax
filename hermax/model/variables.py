from __future__ import annotations
import math
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from functools import reduce
from typing import Iterable, Mapping, Optional, Sequence
from pysat.formula import CNF, WCNF
from hermax.encoder.card import CardEnc
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
from .expressions import _detection_error, _nonlinear_error, _ensure_same_model, _ensure_same_model_pair_fast, _LazyIntExpr


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
        self._contains_cache: dict[int, Literal] = {}

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
        """Return membership indicator for ``value in self``."""
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            key = id(value)
            cached = self._contains_cache.get(key)
            if cached is not None:
                return cached

            allowed = [value == v for v in self.universe if value.lb <= v <= value.ub]
            if not allowed:
                lit = self._model._get_bool_constant_literal(False)
                self._contains_cache[key] = lit
                return lit
            if len(allowed) == 1:
                lit = allowed[0]
                self._contains_cache[key] = lit
                return lit

            b = self._model.bool()
            clauses = [Clause(self._model, [~b, *allowed])]
            clauses.extend(Clause(self._model, [~eq, b]) for eq in allowed)
            self._model._register_literal_definition(b, ClauseGroup(self._model, clauses))
            self._contains_cache[key] = b
            return b

        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("contains() expects an integer or IntVar.")
        return self._lit_for_value(int(value))

    def cardinality(self) -> PBExpr:
        """Return cardinality expression ``|self|``."""
        return PBExpr(self._model, [Term(1, lit) for lit in self._member_lits.values()], 0)

    def card(self, name: Optional[str] = None) -> "IntVar":
        """Materialize an integer variable constrained to this set's cardinality.

        The binding clauses are registered lazily: they are only flushed into
        the model when a constraint consuming the returned ``IntVar`` is
        actually added to the model.  Calling ``card()`` and discarding the
        result is a no-op with respect to ``model._hard``.
        """
        out_name = self._model._reserve_name(None) if name is None else name
        n = len(self.universe)
        out = self._model.int(out_name, lb=0, ub=n)
        if n == 0:
            return out

        from hermax.utils import batcher_odd_even_sorting_network
        from .encoders import _EncoderDispatch

        bools = [self._lit_for_value(v) for v in self.universe]
        net = batcher_odd_even_sorting_network(n)
        wires: list[bool | Literal] = list(bools)
        clauses: list[Clause] = []

        for i, j in net:
            a = wires[i]
            b = wires[j]
            lo = _EncoderDispatch._lit_and(clauses, self._model, a, b)
            hi = _EncoderDispatch._lit_or(clauses, self._model, a, b)
            wires[i] = lo
            wires[j] = hi

        for k, t_k in enumerate(out._threshold_lits):
            w = wires[n - 1 - k]
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
        vals = sorted(set(self.universe) | set(other.universe))
        clauses = [
            Clause(self._model, [~self._lit_for_value(v), other._lit_for_value(v)])
            for v in vals
        ]
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
        vals = sorted(set(self.universe) | set(other.universe))
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

    def _neq_group_constant(self, values) -> ClauseGroup:
        const_vals = self._coerce_constant_values(values)
        outside = [v for v in const_vals if v not in self._member_lits]
        if outside:
            return ClauseGroup(self._model, [])

        true_lit = self._model._get_bool_constant_literal(True)
        false_lit = self._model._get_bool_constant_literal(False)
        diff_lits: list[Literal] = []
        clauses: list[Clause] = []
        for v in self.universe:
            target = true_lit if v in const_vals else false_lit
            d, defs = self._xor_indicator(self._member_lits[v], target)
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

    def _binary_set_op(self, other: "IntSetVar", op: str, name: Optional[str] = None) -> "IntSetVar":
        if not isinstance(other, IntSetVar):
            raise TypeError("set operation expects IntSetVar.")
        _ensure_same_model_pair_fast(self, other)
        hard0 = len(self._model._hard)
        soft0 = len(self._model._soft)
        vals = sorted(set(self.universe) | set(other.universe))
        out_name = self._model._reserve_name(None) if name is None else name
        self._model._reserve_container_name(out_name)
        out = IntSetVar(self._model, out_name, vals)

        clauses: list[Clause] = []
        for v in vals:
            a = self._lit_for_value(v)
            b = other._lit_for_value(v)
            r = out._member_lits[v]
            if op == "union":
                clauses.append(Clause(self._model, [~r, a, b]))
                clauses.append(Clause(self._model, [~a, r]))
                clauses.append(Clause(self._model, [~b, r]))
            elif op == "intersection":
                clauses.append(Clause(self._model, [~r, a]))
                clauses.append(Clause(self._model, [~r, b]))
                clauses.append(Clause(self._model, [~a, ~b, r]))
            elif op == "difference":
                clauses.append(Clause(self._model, [~r, a]))
                clauses.append(Clause(self._model, [~r, ~b]))
                clauses.append(Clause(self._model, [~a, b, r]))
            elif op == "symdiff":
                clauses.append(Clause(self._model, [a, b, ~r]))
                clauses.append(Clause(self._model, [~a, ~b, ~r]))
                clauses.append(Clause(self._model, [~a, b, r]))
                clauses.append(Clause(self._model, [a, ~b, r]))
            else:  # pragma: no cover - defensive
                raise ValueError(f"Unknown set op {op!r}")
        self._model._hard.extend(clauses)
        self._model._inc_state.route_deltas(hard0, soft0)
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
        return False

    def __ne__(self, other):  # type: ignore[override]
        if isinstance(other, IntSetVar):
            return self._neq_group_set(other)
        if isinstance(other, (set, frozenset, list, tuple)):
            return self._neq_group_constant(other)
        return True


class EnumVar:
    """Finite-domain categorical variable encoded as choice literals."""
    __slots__ = ("_model", "name", "choices", "nullable", "_choice_lits")

    def __init__(self, model: "Model", name: str, choices: Sequence[str], nullable: bool):
        self._model = model
        self.name = name
        self.choices = list(choices)
        self.nullable = bool(nullable)
        if not self.choices and not self.nullable:
            raise ValueError("Non-nullable EnumVar requires at least one choice.")
        self._choice_lits = {c: model.bool(f"{name}::{c}") for c in self.choices}
        self._add_domain_constraints()

    def _add_domain_constraints(self) -> None:
        lits = [self._choice_lits[c] for c in self.choices]
        if not lits:
            return
        dimacs = [self._model._lit_to_dimacs(lit) for lit in lits]
        clauses = []
        for i in range(len(lits)):
            for j in range(i + 1, len(lits)):
                clauses.append(Clause(self._model, [~lits[i], ~lits[j]]))
        if self.nullable:
            group = ClauseGroup(self._model, clauses, amo_groups=[dimacs])
        else:
            clauses.append(Clause(self._model, lits))
            group = ClauseGroup(self._model, clauses, eo_groups=[dimacs])
        self._model._register_clausegroup_structure(group)
        for lit in lits:
            self._model._register_literal_definition(lit, group)

    def is_in(self, choices: Sequence[str]) -> Clause:
        """Return a CNF clause asserting the enum is one of ``choices``.

        This is a fast subset-disjunction helper that directly reuses the
        underlying choice literals and introduces no auxiliary variables.

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
            if c not in self._choice_lits:
                raise ValueError(f"Unknown enum choice {c!r}")
            if c in seen:
                continue
            seen.add(c)
            lits.append(self._choice_lits[c])
        if not lits:
            raise ValueError("EnumVar.is_in() requires at least one valid choice.")
        return Clause.from_iterable(lits)

    def __eq__(self, other):  # type: ignore[override]
        if isinstance(other, str):
            if other not in self._choice_lits:
                raise ValueError(f"Unknown enum choice {other!r}")
            return self._choice_lits[other]
        if isinstance(other, EnumVar):
            _ensure_same_model_pair_fast(self, other)
            if self.choices != other.choices:
                raise ValueError("Enum equality requires matching choices.")
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
            return ClauseGroup(self._model, clauses)
        return False

    def __ne__(self, other):  # type: ignore[override]
        if isinstance(other, str):
            if other not in self._choice_lits:
                raise ValueError(f"Unknown enum choice {other!r}")
            return ~self._choice_lits[other]
        if isinstance(other, EnumVar):
            _ensure_same_model_pair_fast(self, other)
            if self.choices != other.choices:
                raise ValueError("Enum inequality requires matching choices.")
            clauses: list[Clause] = []
            # Enforce different chosen value by forbidding pairwise equal choices.
            for choice in self.choices:
                clauses.append(Clause(self._model, [~self._choice_lits[choice], ~other._choice_lits[choice]]))
            # If both are nullable, also forbid the "both none" case.
            if self.nullable and other.nullable:
                lits = [self._choice_lits[c] for c in self.choices] + [other._choice_lits[c] for c in self.choices]
                clauses.append(Clause(self._model, lits))
            return ClauseGroup(self._model, clauses)
        return True


class _MultiplexerInt:
    """Lazy descriptor for ``array @ int_var`` element-style constraints.

    This holds an array of integer constants and an index :class:`IntVar` and
    compiles comparisons by unrolling across the index domain.
    """

    __slots__ = ("_model", "_array", "_index_var")

    def __init__(self, model: "Model", array: Sequence[int], index_var: "IntVar"):
        self._model = model
        self._array = tuple(int(v) for v in array)
        self._index_var = index_var

    @staticmethod
    def _cmp_int(lhs: int, op: str, rhs: int) -> bool:
        return {
            "<=": lhs <= rhs,
            "<": lhs < rhs,
            ">=": lhs >= rhs,
            ">": lhs > rhs,
            "==": lhs == rhs,
            "!=": lhs != rhs,
        }[op]

    def _rhs_constraint(self, op: str, rhs, array_val: int):
        if isinstance(rhs, int):
            return self._cmp_int(array_val, op, rhs)
        if isinstance(rhs, IntVar):
            _ensure_same_model_pair_fast(self, rhs)
            if op == "<=":
                return rhs >= array_val
            if op == "<":
                return rhs > array_val
            if op == ">=":
                return rhs <= array_val
            if op == ">":
                return rhs < array_val
            if op == "==":
                return rhs == array_val
            if op == "!=":
                return rhs != array_val
            raise ValueError(f"Unsupported comparator {op!r}")
        raise TypeError(f"Multiplexer comparison does not support RHS {type(rhs)!r}")

    def _evaluate_comparator(self, op: str, rhs) -> ClauseGroup:
        clauses: list[Clause] = []
        idx = self._index_var
        for k in range(idx.lb, idx.ub + 1):
            array_pos = k - idx.lb
            array_val = self._array[array_pos]
            branch = self._rhs_constraint(op, rhs, array_val)
            if isinstance(branch, bool):
                if branch:
                    continue
                neq = (idx != k)
                if isinstance(neq, Literal):
                    clauses.append(Clause(self._model, [neq]))
                else:
                    assert isinstance(neq, ClauseGroup), "IntVar.__ne__(int) must return Literal or ClauseGroup"
                    clauses.extend(neq)
                continue

            # (idx == k) -> branch
            idx_eq_k = (idx == k)
            assert isinstance(idx_eq_k, Literal), "IntVar.__eq__(int) must return Literal in-domain"

            if isinstance(branch, PBConstraint):
                clauses.extend(branch.only_if(idx_eq_k).clauses())
            else:
                clauses.extend(self._model._as_clausegroup(branch).only_if(idx_eq_k))
        return ClauseGroup(self._model, clauses)

    def __le__(self, rhs):
        return self._evaluate_comparator("<=", rhs)

    def __lt__(self, rhs):
        return self._evaluate_comparator("<", rhs)

    def __ge__(self, rhs):
        return self._evaluate_comparator(">=", rhs)

    def __gt__(self, rhs):
        return self._evaluate_comparator(">", rhs)

    def __eq__(self, rhs):  # type: ignore[override]
        return self._evaluate_comparator("==", rhs)

    def __ne__(self, rhs):  # type: ignore[override]
        return self._evaluate_comparator("!=", rhs)


class _VectorElementInt:
    """Lazy descriptor for variable-array indexing: ``IntVector[IntVar]``.

    Represents ``V[B]`` where ``V`` is a vector of :class:`IntVar` and ``B`` is
    an index :class:`IntVar`. Comparators are compiled by unrolling index values
    and gating branch constraints:

    ``(B == i) -> (V[i] OP rhs)``.
    """

    __slots__ = ("_model", "_items", "_index_var")

    def __init__(self, model: "Model", items: Sequence["IntVar"], index_var: "IntVar"):
        self._model = model
        self._items = tuple(items)
        self._index_var = index_var

    def _rhs_constraint(self, op: str, rhs, item: "IntVar"):
        if isinstance(rhs, int):
            return {
                "<=": item <= rhs,
                "<": item < rhs,
                ">=": item >= rhs,
                ">": item > rhs,
                "==": item == rhs,
                "!=": item != rhs,
            }[op]
        if isinstance(rhs, IntVar):
            _ensure_same_model_pair_fast(self, rhs)
            return {
                "<=": item <= rhs,
                "<": item < rhs,
                ">=": item >= rhs,
                ">": item > rhs,
                "==": item == rhs,
                "!=": item != rhs,
            }[op]
        raise TypeError(f"Vector element comparison does not support RHS {type(rhs)!r}")

    def _evaluate_comparator(self, op: str, rhs) -> ClauseGroup:
        clauses: list[Clause] = []
        idx = self._index_var
        for k in range(idx.lb, idx.ub + 1):
            item_pos = k
            item = self._items[item_pos]
            branch = self._rhs_constraint(op, rhs, item)

            idx_eq_k = (idx == k)
            assert isinstance(idx_eq_k, Literal), "IntVar.__eq__(int) must return Literal in-domain"

            clauses.extend(self._model._as_clausegroup(branch).only_if(idx_eq_k))
        return ClauseGroup(self._model, clauses)

    def __le__(self, rhs):
        return self._evaluate_comparator("<=", rhs)

    def __lt__(self, rhs):
        return self._evaluate_comparator("<", rhs)

    def __ge__(self, rhs):
        return self._evaluate_comparator(">=", rhs)

    def __gt__(self, rhs):
        return self._evaluate_comparator(">", rhs)

    def __eq__(self, rhs):  # type: ignore[override]
        return self._evaluate_comparator("==", rhs)

    def __ne__(self, rhs):  # type: ignore[override]
        return self._evaluate_comparator("!=", rhs)


class IntVar:
    """Bounded integer variable with ladder/order encoding.

    Domain are ``[lb, ub]`` (upper bound included).
    """
    __slots__ = ("_model", "name", "lb", "ub", "_threshold_lits", "_eq_lits", "_cmp_cache")

    def __init__(self, model: "Model", name: str, lb: int, ub: int):
        if not isinstance(lb, int) or not isinstance(ub, int):
            raise TypeError("lb and ub must be ints")
        if ub < lb:
            raise ValueError("Int domain must satisfy lb <= ub")
        self._model = model
        self.name = name
        self.lb = lb
        self.ub = ub
        span = ub - lb + 1
        # Compact order/ladder representation:
        # for domain [lb, ub], we only need (span - 1) threshold bits.
        # Each bit i encodes (x >= lb + i + 1).
        self._threshold_lits = [model.bool(f"{name}<=#{i}") for i in range(max(0, span - 1))]
        for idx, lit in enumerate(self._threshold_lits):
            model._intvar_threshold_owner_by_litid[lit.id] = (self, idx)
        self._eq_lits: dict[int, Literal] = {}
        self._cmp_cache: dict[tuple[str, int], Literal] = {}
        self._add_domain_constraints()

    def _add_domain_constraints(self) -> None:
        # Prefix-true unary encoding over (span - 1) bits.
        ts = self._threshold_lits
        for i in range(len(ts) - 1):
            # t_{i+1} -> t_i
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

    def __mul__(self, other):
        if isinstance(other, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
            raise _nonlinear_error(self, other)
        if isinstance(other, int):
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

        This is the lazy/holding-tank counterpart of :meth:`Model.scale`.
        """
        if isinstance(factor, bool):
            raise ValueError("Scale factor must be strictly positive.")
        if not isinstance(factor, int):
            raise TypeError("Scale factor must be an integer.")
        if factor <= 0:
            raise ValueError("Scale factor must be strictly positive.")
        return ScaleExpr(self, factor)

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
        try:
            vals = [int(v) for v in array[: (self.ub - self.lb + 1)]]
        except (TypeError, ValueError, OverflowError) as e:
            raise TypeError("Multiplexer array must contain integer constants.") from e
        return _MultiplexerInt(self._model, vals, self)

    def piecewise(self, *, base_value: int, steps: Mapping[int, int]) -> PBExpr:
        """Return a lazy PB expression for a step function of this integer variable.

        ``steps`` maps thresholds to the new function value active for all
        assignments ``self >= threshold``.

        Example:
            ``x.piecewise(base_value=10, steps={10: 25, 50: 100})``

        The returned object is a :class:`PBExpr` and burns no new variables or
        clauses at construction time. Negative deltas are handled by the normal
        PB normalization pipeline when the expression is later constrained.
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
            d = self._model.bool(f"{self.name}!={other.name}")
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

    def _threshold_cuts_with(self, other: "IntVar") -> range:
        # Integer cut values k for predicates (x >= k) that distinguish values in
        # either domain. Cuts are in [min(lb)+1, max(ub)] inclusive.
        start = min(self.lb, other.lb) + 1
        stop = max(self.ub, other.ub) + 1  # range stop is exclusive
        return range(start, stop)

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

        ge_lo = self.__ge__(lo)
        ge_hi1 = self.__ge__(hi + 1)

        # Forbid values in [lo, hi] by forcing a jump:
        #   x >= lo  ->  x >= hi+1
        # Constant-fold any edge cases so we avoid internal __true/__false bloat.
        if ge_lo is m._get_bool_constant_literal(False) or ge_hi1 is m._get_bool_constant_literal(True):
            return Clause(m, [m._get_bool_constant_literal(True)])
        if ge_lo is m._get_bool_constant_literal(True) and ge_hi1 is m._get_bool_constant_literal(False):
            return Clause(m, [])
        if ge_lo is m._get_bool_constant_literal(True):
            return Clause(m, [ge_hi1])
        if ge_hi1 is m._get_bool_constant_literal(False):
            return Clause(m, [~ge_lo])
        return Clause(m, [~ge_lo, ge_hi1])

    def in_range(self, start: int, end: int) -> Literal:
        """Return a lazy indicator literal for inclusive membership ``start <= x <= end``.

        The returned literal is safe to construct and discard: any helper clauses
        defining the indicator are registered lazily and only materialized when
        the literal is consumed by a model sink/export.
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

        b = m.bool(f"{self.name}∈[{lo},{hi}]")
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

        m = self._model
        clauses: list[Clause] = []

        def ge_state(x: "IntVar", k: int) -> tuple[str, Optional[Literal]]:
            # Returns (\"true\"|\"false\"|\"lit\", lit_or_none)
            if k <= x.lb:
                return ("true", None)
            if k > x.ub:
                return ("false", None)
            return ("lit", x.__ge__(k))

        def add_implication(lhs_x: "IntVar", rhs_x: "IntVar", shift: int) -> None:
            # lhs_x <= rhs_x + shift  <=>  (lhs_x >= k) -> (rhs_x >= k-shift)
            start = min(lhs_x.lb + 1, rhs_x.lb + shift + 1)
            stop = max(lhs_x.ub, rhs_x.ub + shift) + 1  # range stop exclusive
            for k in range(start, stop):
                lkind, llit = ge_state(lhs_x, k)
                rkind, rlit = ge_state(rhs_x, k - shift)
                # Constant-fold implication l -> r.
                if lkind == "false" or rkind == "true":
                    continue
                if lkind == "true" and rkind == "false":
                    clauses.append(Clause(m, []))
                    continue
                if lkind == "true" and rkind == "lit":
                    clauses.append(Clause(m, [rlit]))  # type: ignore[list-item]
                    continue
                if lkind == "lit" and rkind == "false":
                    clauses.append(Clause(m, [~llit]))  # type: ignore[arg-type]
                    continue
                if lkind == "lit" and rkind == "lit":
                    clauses.append(Clause(m, [~llit, rlit]))  # type: ignore[arg-type,list-item]
                    continue
                # Remaining case (l true, r true) already continued; this is defensive.

        add_implication(self, other, max_distance)
        add_implication(other, self, max_distance)
        return ClauseGroup(m, clauses)

    def _relop_intvar(self, other: "IntVar", op: str, offset: int = 0) -> ClauseGroup:
        _ensure_same_model_pair_fast(self, other)
        clauses: list[Clause] = []
        m = self._model

        def ge_state(x: "IntVar", k: int) -> tuple[str, Optional[Literal]]:
            if k <= x.lb:
                return ("true", None)
            if k > x.ub:
                return ("false", None)
            return ("lit", x.__ge__(k))

        def add_implication(lhs_x: "IntVar", rhs_x: "IntVar", shift: int) -> None:
            # Enforce lhs_x <= rhs_x + shift  by threshold implications
            # (lhs_x >= k) -> (rhs_x >= k-shift)
            start = min(lhs_x.lb + 1, rhs_x.lb + shift + 1)
            stop = max(lhs_x.ub, rhs_x.ub + shift) + 1
            for k in range(start, stop):
                lkind, llit = ge_state(lhs_x, k)
                rkind, rlit = ge_state(rhs_x, k - shift)
                if lkind == "false" or rkind == "true":
                    continue
                if lkind == "true" and rkind == "false":
                    clauses.append(Clause(m, []))
                    continue
                if lkind == "true" and rkind == "lit":
                    clauses.append(Clause(m, [rlit]))  # type: ignore[list-item]
                    continue
                if lkind == "lit" and rkind == "false":
                    clauses.append(Clause(m, [~llit]))  # type: ignore[arg-type]
                    continue
                if lkind == "lit" and rkind == "lit":
                    clauses.append(Clause(m, [~llit, rlit]))  # type: ignore[arg-type,list-item]
                    continue

        if op == "<=":
            # self + offset <= other  <=>  self <= other - offset
            add_implication(self, other, -offset)
            return IntRelation(m, clauses, self, other, "<=", offset)
        if op == ">=":
            # self + offset >= other  <=>  other <= self + offset
            add_implication(other, self, offset)
            return IntRelation(m, clauses, self, other, ">=", offset)
        if op == "<":
            # self + offset < other  <=>  self + (offset + 1) <= other
            return IntRelation(self._model, list(self._relop_intvar(other, "<=", offset + 1)), self, other, "<", offset)
        if op == ">":
            # self + offset > other  <=>  self + (offset - 1) >= other
            return IntRelation(self._model, list(self._relop_intvar(other, ">=", offset - 1)), self, other, ">", offset)
        if op == "!=":
            if offset != 0:
                raise ValueError("IntVar '!=' with offset is not supported")
            return self != other
        raise ValueError(f"Unsupported IntVar relation {op!r}")

    def _eq_indicator(self, other: "IntVar") -> Literal:
        _ensure_same_model_pair_fast(self, other)
        key = ("==intvar", id(other))
        if key not in self._cmp_cache:
            e = self._model.bool(f"{self.name}=={other.name}")
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
        if isinstance(value, int):
            if value < self.lb or value > self.ub:
                raise ValueError(f"value {value} is outside domain [{self.lb}, {self.ub}]")
            if value not in self._eq_lits:
                k = value - self.lb
                ts = self._threshold_lits
                # Edge cases can reuse direct threshold/constant literals.
                if self._span() == 1:
                    lit = self._model._get_bool_constant_literal(True)
                elif k == 0:
                    lit = ~ts[0]
                elif k == self._span() - 1:
                    lit = ts[k - 1]
                else:
                    lit = self._model.bool(f"{self.name}=={value}")
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
                if self._span() > 1:
                    self._model._intvar_eq_owner_by_litid[self._model._lit_to_dimacs(lit)] = (self, int(value))
            return self._eq_lits[value]
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            clauses: list[Clause] = []
            # Equality in ladder encoding is equivalence of all threshold cuts.
            for k in self._threshold_cuts_with(value):
                sk = self.__ge__(k)
                vk = value.__ge__(k)
                clauses.append(Clause(self._model, [~sk, vk]))
                clauses.append(Clause(self._model, [~vk, sk]))
            return IntRelation(self._model, clauses, self, value, "==", 0)
        if isinstance(value, (Literal, Term, PBExpr, _LazyIntExpr)):
            _ensure_same_model(self, value)
            return PBExpr.from_item(self)._finalize_compare("==", value)
        return False

    def __ne__(self, value):  # type: ignore[override]
        if isinstance(value, int):
            return ~(self == value)
        if isinstance(value, IntVar):
            _ensure_same_model_pair_fast(self, value)
            clauses: list[Clause] = []
            lo = max(self.lb, value.lb)
            hi = min(self.ub, value.ub)
            for v in range(lo, hi + 1):
                # No-new-vars linear encoding: forbid "self == v and other == v"
                # using compact exact-value boundary patterns (clause size <= 4).
                atoms = [*self._exact_value_atoms(v), *value._exact_value_atoms(v)]
                clauses.append(Clause(self._model, [~lit for lit in atoms]))
            return ClauseGroup(self._model, clauses)
        return True


class IntervalVar:
    """Fixed-duration interval variable for scheduling-style constraints.

    The constructor binds two :class:`IntVar` objects, ``start`` and ``end``,
    and enforces ``end == start + duration``. Public horizon is:

    * ``start`` argument = earliest start (inclusive)
    * ``end`` argument = latest end (inclusive)
    """

    __slots__ = ("_model", "name", "start", "end", "duration", "earliest_start", "latest_end")

    def __init__(self, model: "Model", name: str, *, start: int, duration: int, end: int):
        if not isinstance(start, int) or not isinstance(duration, int) or not isinstance(end, int):
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
        # end domain is [start + duration, end] because latest end is inclusive.
        self.end = model.int(f"{name}.end", lb=start + duration, ub=end)

        # Structural identity of the interval.
        #
        # IMPORTANT: Do NOT encode `end == start + duration` through the generic
        # PB/Card encoder pipeline. Both endpoints already use the same ladder
        # width by construction, and the duration shift is absorbed into the
        # endpoint domains (`end.lb = start.lb + duration`), so the identity is
        # exactly a bitwise equivalence of threshold ladders:
        #   start_t[i] <-> end_t[i]
        # This is O(n) binary clauses and introduces zero auxiliary variables.
        if len(self.start._threshold_lits) != len(self.end._threshold_lits):
            raise AssertionError("Interval endpoint ladders must have equal width")
        for s_t, e_t in zip(self.start._threshold_lits, self.end._threshold_lits):
            model._hard.append(Clause(model, [~s_t, e_t]))
            model._hard.append(Clause(model, [~e_t, s_t]))

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
            return ClauseGroup(self._model, [Clause(self._model, [self._model._get_bool_constant_literal(False)])])
        sel = self._model.bool(f"{self.name}≺{other.name}")
        left = self.ends_before(other).only_if(sel)
        right = other.ends_before(self).only_if(~sel)
        return left & right


class _BaseVector:
    """Base class for typed immutable vector containers."""
    __slots__ = ("_model", "name", "_items")
    _item_type = object

    def __init__(self, model: "Model", name: str, items: Sequence):
        self._model = model
        self.name = name
        self._items = list(items)
        expected = type(self)._item_type
        for item in self._items:
            if not isinstance(item, expected):
                raise TypeError(f"{type(self).__name__} expects items of type {expected.__name__}")
            if item._model is not model:
                raise ValueError("Vector items must belong to the same model.")

    def __len__(self):
        return len(self._items)

    def __getitem__(self, i):
        return self._items[i]

    def __iter__(self):
        return iter(self._items)

    def _table_cell_constraint(self, item, value):
        raise NotImplementedError

    def _normalize_table_row(self, row):
        return tuple(row)

    def is_in(self, rows: Sequence[Sequence]):
        """Return an extensional (allowed-combinations) table constraint.

        The vector must match one of the provided rows. This is encoded using
        row-selector literals with an exactly-one constraint plus gated row
        implications.
        """
        rows_list = [tuple(r) for r in rows]
        if not rows_list:
            # Empty table = contradiction.
            return ClauseGroup(self._model, [Clause(self._model, [self._model._get_bool_constant_literal(False)])])
        width = len(self._items)
        norm_rows: list[tuple] = []
        seen = set()
        for row in rows_list:
            if len(row) != width:
                raise ValueError("Table rows must match vector length.")
            nrow = self._normalize_table_row(row)
            if nrow in seen:
                continue
            seen.add(nrow)
            norm_rows.append(nrow)

        clauses: list[Clause] = []
        sels = [self._model.bool() for _ in norm_rows]
        sel_vec = BoolVector(self._model, f"{self.name}.table_sel", sels)
        clauses.extend(self._model._as_clausegroup(sel_vec.exactly_one()))

        for sel, row in zip(sels, norm_rows):
            for item, value in zip(self._items, row):
                c = self._table_cell_constraint(item, value)
                clauses.extend(self._model._as_clausegroup(c).only_if(sel))

        return ClauseGroup(self._model, clauses)


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

    def at_most_one(self):
        """Return a cardinality constraint enforcing at most one true literal."""
        return sum_expr(self._items) <= 1

    def exactly_one(self):
        """Return a cardinality constraint enforcing exactly one true literal."""
        return sum_expr(self._items) == 1

    def at_least_one(self):
        """Return a single clause enforcing at least one true literal."""
        return Clause.from_iterable(self._items)

    def _table_cell_constraint(self, item, value):
        if not isinstance(value, bool):
            raise TypeError("BoolVector.is_in() rows must contain booleans.")
        return item if value else ~item

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
        if not isinstance(value, str):
            raise TypeError("EnumVector.is_in() rows must contain enum labels (or None for nullable enums).")
        return item == value

    def _all_different_pairwise(self) -> ClauseGroup:
        clauses: list[Clause] = []
        for i in range(len(self._items)):
            for j in range(i + 1, len(self._items)):
                neq = self._items[i] != self._items[j]
                if isinstance(neq, ClauseGroup):
                    clauses.extend(neq)
        return ClauseGroup(self._model, clauses)

    def _all_different_bipartite(self) -> ClauseGroup:
        # Column-wise AMO over existing one-hot choice literals. If nullable enums
        # are present, fallback to pairwise for now because `None` is not tracked
        # as a single literal yet.
        if any(ev.nullable for ev in self._items):
            return self._all_different_pairwise()
        clauses: list[Clause] = []
        amo_groups: list[list[int]] = []
        if not self._items:
            return ClauseGroup(self._model, clauses, amo_groups=amo_groups)
        choices = tuple(self._items[0].choices)
        for ev in self._items[1:]:
            if tuple(ev.choices) != choices:
                raise ValueError("EnumVector.all_different() requires matching enum choices.")
        for label in choices:
            col_lits = [ev._choice_lits[label] for ev in self._items]
            col = BoolVector(self._model, f"{self.name}.col_amo[{label}]", col_lits)
            clauses.extend(self._model._as_clausegroup(col.at_most_one()))
            amo_groups.append([self._model._lit_to_dimacs(lit) for lit in col_lits])
        return ClauseGroup(self._model, clauses, amo_groups=amo_groups)

    def all_different(self, backend: str = "auto") -> ClauseGroup:
        """Return an all-different constraint over all enum elements.

        Backends:
            ``auto`` (default): column-wise AMO over enum choice literals.
            ``bipartite``: same as ``auto`` (or pairwise fallback for nullable enums).
            ``pairwise``: pairwise enum inequality constraints.
        """
        if backend == "auto":
            backend = "bipartite"
        if backend == "pairwise":
            return self._all_different_pairwise()
        if backend == "bipartite":
            return self._all_different_bipartite()
        if backend == "sorting":
            raise ValueError("sorting backend is not supported for EnumVector.all_different().")
        raise ValueError("Unknown all_different backend.")


class IntSetVector(_BaseVector):
    """Vector of :class:`IntSetVar` values."""

    _item_type = IntSetVar

    def _table_cell_constraint(self, item, value):
        return item == value


class IntVector(_BaseVector):
    """Vector of :class:`IntVar` values with common global helpers."""
    _item_type = IntVar

    def _table_cell_constraint(self, item, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("IntVector.is_in() rows must contain integers.")
        return item == value

    def __getitem__(self, i):
        """Return item/slice, or a variable-index element view.

        For ``vec[idx]`` with ``idx`` as :class:`IntVar`, the index domain must
        satisfy:
            * ``idx.lb >= 0``
            * ``idx.ub < len(vec)``
        """
        if isinstance(i, IntVar):
            _ensure_same_model_pair_fast(self, i)
            if i.lb < 0:
                raise ValueError("IntVector[IntVar] currently requires index.lb >= 0.")
            if i.ub >= len(self._items):
                raise ValueError(
                    f"IntVector length {len(self._items)} does not cover index domain [{i.lb}, {i.ub}]."
                )
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

        This is a one-sided aggregate (not exact ``max``) and is cheaper than
        :meth:`max` because it only emits upward-pressure clauses.
        """
        if not self._items:
            raise ValueError("Cannot compute upper_bound of an empty IntVector.")
        if len(self._items) == 1:
            return self._items[0]
        return MaxExpr(self._model, self._items, "upper_bound", name=name)

    def lower_bound(self, name: Optional[str] = None):
        """Create an ``IntVar`` constrained to be <= every element in the vector.

        This is a one-sided aggregate (not exact ``min``) and is cheaper than
        :meth:`min` because it only emits downward-pressure clauses.
        """
        if not self._items:
            raise ValueError("Cannot compute lower_bound of an empty IntVector.")
        if len(self._items) == 1:
            return self._items[0]
        return MaxExpr(self._model, self._items, "lower_bound", name=name)

    def running_max(self, name: Optional[str] = None) -> "IntVector":
        """Return prefix maxima as a materialized ``IntVector``.

        ``out[i]`` equals ``max(self[:i+1])``. This uses a cumulative fold with
        :meth:`Model.max` to avoid the common ``O(N^2)`` prefix-max modeling
        trap of recomputing ``max(self[:i])`` independently at each step.
        """
        if not self._items:
            raise ValueError("Cannot compute running_max of an empty IntVector.")
        if name is None:
            out_name = f"{self.name}_running_max"
            self._model._reserve_container_name(out_name)
        else:
            self._model._reserve_container_name(name)
            out_name = name
        out: list[IntVar] = [self._items[0]]
        for i in range(1, len(self._items)):
            step_name = f"{out_name}[{i}]"
            out.append(self._model.max([out[-1], self._items[i]], name=step_name))
        return IntVector(self._model, out_name, out)

    def running_min(self, name: Optional[str] = None) -> "IntVector":
        """Return prefix minima as a materialized ``IntVector``.

        ``out[i]`` equals ``min(self[:i+1])`` using the same cumulative-fold
        construction pattern as :meth:`running_max`.
        """
        if not self._items:
            raise ValueError("Cannot compute running_min of an empty IntVector.")
        if name is None:
            out_name = f"{self.name}_running_min"
            self._model._reserve_container_name(out_name)
        else:
            self._model._reserve_container_name(name)
            out_name = name
        out: list[IntVar] = [self._items[0]]
        for i in range(1, len(self._items)):
            step_name = f"{out_name}[{i}]"
            out.append(self._model.min([out[-1], self._items[i]], name=step_name))
        return IntVector(self._model, out_name, out)

    def running_sum(self, name: Optional[str] = None) -> "IntVector":
        """Return prefix sums as a materialized ``IntVector``.

        ``out[i]`` equals ``sum(self[:i+1])``. This is built as a cumulative
        fold with one fresh integer variable per prefix step, avoiding repeated
        re-materialization of larger and larger PB expressions.
        """
        if not self._items:
            raise ValueError("Cannot compute running_sum of an empty IntVector.")
        if name is None:
            out_name = f"{self.name}_running_sum"
            self._model._reserve_container_name(out_name)
        else:
            self._model._reserve_container_name(name)
            out_name = name

        out: list[IntVar] = [self._items[0]]
        prefix_lb = self._items[0].lb
        prefix_ub = self._items[0].ub
        for i in range(1, len(self._items)):
            xi = self._items[i]
            prefix_lb += xi.lb
            prefix_ub += xi.ub
            step_name = f"{out_name}[{i}]"
            step = self._model.int(step_name, lb=prefix_lb, ub=prefix_ub)
            self._model &= (step == (out[-1] + xi))
            out.append(step)
        return IntVector(self._model, out_name, out)

    def _all_different_pairwise(self) -> ClauseGroup:
        clauses: list[Clause] = []
        for i in range(len(self._items)):
            for j in range(i + 1, len(self._items)):
                neq = self._items[i] != self._items[j]
                if isinstance(neq, ClauseGroup):
                    clauses.extend(neq)
        return ClauseGroup(self._model, clauses)

    def _all_different_bipartite(self) -> ClauseGroup:
        if not self._items:
            return ClauseGroup(self._model, [], amo_groups=[])
        # Require a common domain for the current implementation.
        lb = self._items[0].lb
        ub = self._items[0].ub
        for x in self._items[1:]:
            if x.lb != lb or x.ub != ub:
                raise ValueError("IntVector.bipartite all_different currently requires a common domain.")
        if (ub - lb + 1) < len(self._items):
            raise ValueError("IntVector.bipartite all_different requires domain size >= vector length.")
        clauses: list[Clause] = []
        amo_groups: list[list[int]] = []
        for v in range(lb, ub + 1):
            col_lits = [x == v for x in self._items]
            col = BoolVector(self._model, f"{self.name}.eq_col[{v}]", col_lits)
            clauses.extend(self._model._as_clausegroup(col.at_most_one()))
            amo_groups.append([self._model._lit_to_dimacs(lit) for lit in col_lits])
        return ClauseGroup(self._model, clauses, amo_groups=amo_groups)

    def all_different(self, backend: str = "auto") -> ClauseGroup:
        """Return an all-different constraint over all integer elements.

        Backends:
            ``auto`` (default): currently aliases to ``pairwise``.
            ``pairwise``: pairwise integer inequality constraints.
            ``bipartite``: channel to exact-value indicators + column AMOs.
        """
        if backend == "auto":
            backend = "pairwise"
        if backend == "pairwise":
            return self._all_different_pairwise()
        if backend == "bipartite":
            return self._all_different_bipartite()
        raise ValueError("Unknown all_different backend.")

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
            return ClauseGroup(self._model, [Clause(self._model, [self._model._get_bool_constant_literal(False)])])

        prefix_eq: list[Literal] = [self._model._get_bool_constant_literal(True)]
        lt_inds: list[Literal] = []
        clauses: list[Clause] = []

        for i in range(len(self)):
            xi = self._items[i]
            yi = other._items[i]
            eq_i = xi._eq_indicator(yi)
            lt_i = self._model.bool(f"lex_lt[{self.name},{other.name},{i}]")
            lt_inds.append(lt_i)

            # lt_i == (prefix_eq[i] AND (xi < yi))
            lt_cond = xi._relop_intvar(yi, "<")
            clauses.extend(lt_cond.only_if(lt_i))          # lt_i -> xi<yi
            clauses.append(Clause(self._model, [~lt_i, prefix_eq[i]]))  # lt_i -> prefix

            # (prefix & xi<yi) -> lt_i  encoded by forbidding prefix=true and xi<yi with lt_i=false.
            # Reuse the exact "not(xi<yi)" clauses under ~lt_i to force lt_i when prefix is true.
            ge_cond = xi._relop_intvar(yi, ">=")
            if i == 0:
                clauses.extend(ge_cond.only_if(~lt_i))
            else:
                gate = self._model.bool(f"lex_gate[{self.name},{other.name},{i}]")
                # gate == prefix_eq[i] AND ~lt_i
                clauses.append(Clause(self._model, [~gate, prefix_eq[i]]))
                clauses.append(Clause(self._model, [~gate, ~lt_i]))
                clauses.append(Clause(self._model, [~prefix_eq[i], lt_i, gate]))
                clauses.extend(ge_cond.only_if(gate))

            # Build next prefix equality indicator: prefix_eq[i+1] == prefix_eq[i] AND eq_i
            if i < len(self) - 1:
                pnext = self._model.bool(f"lex_prefix[{self.name},{other.name},{i+1}]")
                clauses.append(Clause(self._model, [~pnext, prefix_eq[i]]))
                clauses.append(Clause(self._model, [~pnext, eq_i]))
                clauses.append(Clause(self._model, [~prefix_eq[i], ~eq_i, pnext]))
                prefix_eq.append(pnext)

        # At least one lex-lt witness must be true.
        clauses.append(Clause(self._model, lt_inds))
        return ClauseGroup(self._model, clauses)

    def __eq__(self, other):  # type: ignore[override]
        raise TypeError("Vector equality is ambiguous; use explicit methods.")

    def __le__(self, other):
        raise TypeError("Vector ordering is ambiguous; use lexicographic_less_than().")

    def __ne__(self, other):  # type: ignore[override]
        if not isinstance(other, IntVector):
            return True
        _ensure_same_model_pair_fast(self, other)
        if len(self) != len(other):
            raise ValueError("Vector lengths differ")
        # Flat disjunction of elementwise differences.
        return Clause.from_iterable([self[i]._neq_indicator(other[i]) for i in range(len(self))])


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


class IntMatrix:
    """Dense matrix of :class:`IntVar` cells."""
    __slots__ = ("_model", "name", "_rows", "_cols", "_grid")

    def __init__(self, model: "Model", name: str, rows: int, cols: int, lb: int, ub: int):
        self._model = model
        self.name = name
        self._rows = rows
        self._cols = cols
        self._grid = [
            [model.int(f"{name}[{r},{c}]", lb=lb, ub=ub) for c in range(cols)]
            for r in range(rows)
        ]

    def row(self, r: int) -> IntVector:
        """Return row ``r`` as an :class:`IntVector`."""
        return IntVector(self._model, f"{self.name}.row({r})", self._grid[r])

    def col(self, c: int) -> IntVector:
        """Return column ``c`` as an :class:`IntVector`."""
        return IntVector(self._model, f"{self.name}.col({c})", [self._grid[r][c] for r in range(self._rows)])

    def flatten(self) -> IntVector:
        """Return all cells in row-major order as an :class:`IntVector`."""
        return IntVector(self._model, f"{self.name}.flatten()", [x for row in self._grid for x in row])

    def __getitem__(self, key):
        return IntMatrixView(self._model, self.name, self._grid)[key]


class BoolMatrix:
    """Dense matrix of Boolean literals."""
    __slots__ = ("_model", "name", "_rows", "_cols", "_grid")

    def __init__(self, model: "Model", name: str, rows: int, cols: int):
        self._model = model
        self.name = name
        self._rows = rows
        self._cols = cols
        self._grid = [
            [model.bool(f"{name}[{r},{c}]") for c in range(cols)]
            for r in range(rows)
        ]

    def row(self, r: int) -> BoolVector:
        """Return row ``r`` as a :class:`BoolVector`."""
        return BoolVector(self._model, f"{self.name}.row({r})", self._grid[r])

    def col(self, c: int) -> BoolVector:
        """Return column ``c`` as a :class:`BoolVector`."""
        return BoolVector(self._model, f"{self.name}.col({c})", [self._grid[r][c] for r in range(self._rows)])

    def flatten(self) -> BoolVector:
        """Return all cells in row-major order as a :class:`BoolVector`."""
        return BoolVector(self._model, f"{self.name}.flatten()", [x for row in self._grid for x in row])

    def __getitem__(self, key):
        return BoolMatrixView(self._model, self.name, self._grid)[key]


class EnumMatrix:
    """Dense matrix of :class:`EnumVar` cells."""
    __slots__ = ("_model", "name", "_rows", "_cols", "_grid")

    def __init__(self, model: "Model", name: str, rows: int, cols: int, choices: Sequence[str], nullable: bool = False):
        self._model = model
        self.name = name
        self._rows = rows
        self._cols = cols
        self._grid = [
            [model.enum(f"{name}[{r},{c}]", choices=choices, nullable=nullable) for c in range(cols)]
            for r in range(rows)
        ]

    def row(self, r: int) -> EnumVector:
        """Return row ``r`` as an :class:`EnumVector`."""
        return EnumVector(self._model, f"{self.name}.row({r})", self._grid[r])

    def col(self, c: int) -> EnumVector:
        """Return column ``c`` as an :class:`EnumVector`."""
        return EnumVector(self._model, f"{self.name}.col({c})", [self._grid[r][c] for r in range(self._rows)])

    def flatten(self) -> EnumVector:
        """Return all cells in row-major order as an :class:`EnumVector`."""
        return EnumVector(self._model, f"{self.name}.flatten()", [x for row in self._grid for x in row])

    def __getitem__(self, key):
        return EnumMatrixView(self._model, self.name, self._grid)[key]


class AssignmentView:
    """Decoded view over a raw SAT/MaxSAT model for a specific :class:`Model`."""
    __slots__ = ("_model", "_raw_model", "_true_vars")

    def __init__(self, model: "Model", raw_model: Sequence[int]):
        self._model = model
        self._raw_model = list(raw_model)
        self._true_vars = {abs(v): (v > 0) for v in self._raw_model if v != 0}

    @property
    def raw(self) -> list[int]:
        """Return a copy of the raw solver model literals."""
        return list(self._raw_model)

    def val(self, obj: Any) -> Any:
        """Decode the value of a model-bound object from the current assignment.

        Args:
            obj: The object to decode. Supported types include:
                - :class:`Literal`: returns a ``bool``.
                - :class:`IntVar`: returns an ``int``.
                - :class:`EnumVar`: returns the chosen ``str`` (or ``None`` if nullable).
                - :class:`IntSetVar`: returns a ``set[int]``.
                - :class:`IntervalVar`: returns a ``dict`` with ``start``, ``end``, and ``duration``.
                - :class:`IntVector`, :class:`BoolVector`, etc.: returns a ``list`` of decoded values.
                - :class:`IntMatrix`, :class:`BoolMatrix`, etc.: returns a nested ``list`` (rows/cols).
                - :class:`IntDict`, :class:`BoolDict`, etc.: returns a ``dict`` with decoded values.
                - Nested ``list`` or ``tuple`` of supported objects.

        Returns:
            The Python-native value representing the variable's state in this model.

        Raises:
            TypeError: if ``obj`` is not a supported target for decoding.
        """
        if isinstance(obj, Literal):
            truth = self._true_vars.get(obj.id, False)
            return truth if obj.polarity else (not truth)
        if isinstance(obj, EnumVar):
            for choice in obj.choices:
                lit = obj._choice_lits[choice]
                if self.val(lit):
                    return choice
            return None
        if isinstance(obj, IntSetVar):
            return {v for v in obj.universe if self.val(obj._member_lits[v])}
        if isinstance(obj, DivExpr):
            return self.val(obj._src) // obj._divisor
        if isinstance(obj, ScaleExpr):
            return self.val(obj._src) * obj._factor
        if isinstance(obj, MaxExpr):
            vals = [self.val(x) for x in obj._items]
            if obj._kind in {"max", "upper_bound"}:
                return max(vals)
            return min(vals)
        if isinstance(obj, _LazyIntExpr):
            obj = obj._realize()
        if isinstance(obj, IntVar):
            for value, lit in obj._eq_lits.items():
                if self.val(lit):
                    return value
            # Fallback: unary-prefix interpretation over threshold literals.
            count_true = sum(1 for lit in obj._threshold_lits if self.val(lit))
            value = obj.lb + count_true
            if value > obj.ub:
                value = obj.ub
            return value
        if isinstance(obj, IntVector):
            return [self.val(x) for x in obj]
        if isinstance(obj, BoolVector):
            return [self.val(x) for x in obj]
        if isinstance(obj, EnumVector):
            return [self.val(x) for x in obj]
        if isinstance(obj, IntSetVector):
            return [self.val(x) for x in obj]
        if isinstance(obj, IntMatrix):
            return [[self.val(x) for x in row] for row in obj._grid]
        if isinstance(obj, BoolMatrix):
            return [[self.val(x) for x in row] for row in obj._grid]
        if isinstance(obj, EnumMatrix):
            return [[self.val(x) for x in row] for row in obj._grid]
        if isinstance(obj, IntMatrixView):
            return [[self.val(x) for x in row] for row in obj._grid]
        if isinstance(obj, BoolMatrixView):
            return [[self.val(x) for x in row] for row in obj._grid]
        if isinstance(obj, EnumMatrixView):
            return [[self.val(x) for x in row] for row in obj._grid]
        if isinstance(obj, BoolDict):
            return {k: self.val(v) for k, v in obj.items()}
        if isinstance(obj, IntDict):
            return {k: self.val(v) for k, v in obj.items()}
        if isinstance(obj, EnumDict):
            return {k: self.val(v) for k, v in obj.items()}
        if isinstance(obj, IntSetDict):
            return {k: self.val(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.val(x) for x in obj]
        if isinstance(obj, tuple):
            return tuple(self.val(x) for x in obj)
        if isinstance(obj, dict):
            return {k: self.val(v) for k, v in obj.items()}
        if isinstance(obj, IntervalVar):
            return {
                "start": self.val(obj.start),
                "end": self.val(obj.end),
                "duration": obj.duration,
            }
        raise TypeError(f"Unsupported decode target: {type(obj)!r}")

    def __getitem__(self, obj: Any) -> Any:
        """Alias for :meth:`val` allowing indexed access ``result[my_var]``."""
        return self.val(obj)



IntMatrixView._matrix_view_type = IntMatrixView

BoolMatrixView._matrix_view_type = BoolMatrixView

EnumMatrixView._matrix_view_type = EnumMatrixView
