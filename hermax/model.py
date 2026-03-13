from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from functools import reduce
from typing import Iterable, Mapping, Optional, Sequence

from pysat.formula import CNF, WCNF
from hermax.internal.card import CardEnc
from hermax.internal.pb import PBEnc
from hermax.internal.structuredpb import StructuredPBEnc
from hermax.utils import batcher_odd_even_unary_add_network
from pysat.solvers import Solver as PySATSolver
from hermax.non_incremental import RC2 as HermaxRC2


def _detection_error() -> TypeError:
    return TypeError(
        "Conditions for only_if()/implies() must be a Literal."
    )


def _nonlinear_error(lhs=None, rhs=None, op: str = "*") -> TypeError:
    def _label(obj) -> str:
        if obj is None:
            return "<?>"
        typ = type(obj).__name__
        name = getattr(obj, "name", None)
        if isinstance(name, str) and name:
            return f"<{typ}: {name}>"
        return f"<{typ}>"

    return TypeError(
        "Non-linear arithmetic is not supported in Model expressions. "
        f"Unsupported arithmetic: {_label(lhs)} {op} {_label(rhs)}. "
        "Only scalar*Literal and scalar*Int-like products are allowed."
    )


def _ensure_same_model(*objs) -> "Model":
    model = None
    for obj in objs:
        if obj is None:
            continue
        m = getattr(obj, "_model", None)
        if m is None:
            continue
        if model is None:
            model = m
        elif m is not model:
            raise ValueError("Variables belong to different models.")
    return model


def sum_expr(iterable, start=0):
    """Return a linear-time sum over Hermax expression items.

    This is a drop-in replacement for :func:`sum` in Hermax expression code:
    it supports empty iterables the same way as Python ``sum``, and avoids the
    repeated O(n^2) pattern. It's just a faster drop-in.

    Args:
        iterable: Items to accumulate.
        start: Initial value (default ``0``), matching Python ``sum``.

    Returns:
        A plain numeric value when no model-bound items are present; otherwise
        a :class:`PBExpr` bound to the inferred model.
    """

    def _item_model(item):
        if isinstance(item, Term):
            return item.literal._model
        return getattr(item, "_model", None)

    # Keep Python's numeric sum behavior until we encounter a model-bound item.
    model = _item_model(start)
    if model is None:
        numeric_total = start
        expr: PBExpr | None = None
    else:
        numeric_total = 0
        expr = PBExpr.from_item(start)
        # `start` may be model-bound but represented as a neutral PBExpr.
        if expr._model is None:
            expr = PBExpr(model, [], expr.constant)

    for item in iterable:
        item_model = _item_model(item)
        if expr is None and item_model is None:
            numeric_total = numeric_total + item
            continue

        if expr is None:
            model = item_model
            if model is None:
                raise TypeError(f"Unsupported item for sum_expr(): {type(item)!r}")
            expr = PBExpr(model, [], 0)
            if numeric_total != 0:
                expr.add(numeric_total, inplace=True)

        expr.add(item, inplace=True)

    if expr is None:
        return numeric_total
    return expr


class ClauseGroup:
    """Immutable collection of CNF clauses."""

    __slots__ = ("_model", "clauses", "_amo_groups", "_eo_groups")

    def __init__(
        self,
        model: "Model",
        clauses: Sequence["Clause"] | None = None,
        *,
        amo_groups: Sequence[Sequence[int]] | None = None,
        eo_groups: Sequence[Sequence[int]] | None = None,
    ):
        self._model = model
        self.clauses = list(clauses or [])
        self._amo_groups = [list(group) for group in (amo_groups or [])]
        self._eo_groups = [list(group) for group in (eo_groups or [])]

    def _combined_groups(self, other) -> tuple[list[list[int]], list[list[int]]]:
        amo_groups = [*self._amo_groups]
        eo_groups = [*self._eo_groups]
        if isinstance(other, ClauseGroup):
            amo_groups.extend(other._amo_groups)
            eo_groups.extend(other._eo_groups)
        return amo_groups, eo_groups

    def only_if(self, condition: "Literal") -> "ClauseGroup":
        """Return a new clause group gated by one literal."""
        if not isinstance(condition, Literal):
            raise _detection_error()
        _ensure_same_model(self, condition)
        return ClauseGroup(self._model, [c.only_if(condition) for c in self.clauses])

    def implies(self, target):
        """Reject ClauseGroup-as-condition usage in this modeling API."""
        # Using a ClauseGroup as a condition is a detection circuit in this API.
        raise _detection_error()

    def __and__(self, other):
        if isinstance(other, Literal):
            _ensure_same_model(self, other)
            return ClauseGroup(
                self._model,
                [*self.clauses, Clause(self._model, [other])],
                amo_groups=self._amo_groups,
                eo_groups=self._eo_groups,
            )
        if isinstance(other, Clause):
            _ensure_same_model(self, other)
            return ClauseGroup(
                self._model,
                [*self.clauses, other],
                amo_groups=self._amo_groups,
                eo_groups=self._eo_groups,
            )
        if isinstance(other, ClauseGroup):
            _ensure_same_model(self, other)
            amo_groups, eo_groups = self._combined_groups(other)
            return ClauseGroup(self._model, [*self.clauses, *other.clauses], amo_groups=amo_groups, eo_groups=eo_groups)
        raise TypeError("AND only supports Literal, Clause, or ClauseGroup operands.")

    def __iand__(self, other):
        # Immutable-by-operator contract: `x &= y` returns a new ClauseGroup.
        return self.__and__(other)

    def extend(self, other, *, inplace: bool = False) -> "ClauseGroup":
        """Append/merge clauses into this clause group when ``inplace=True``.

        Supported inputs:
            ``Literal``, ``Clause``, or ``ClauseGroup``.

        Warning:
            Mutation requires ``inplace=True``. Prefer ``group & x`` (or
            ``group &= x`` with rebinding semantics) for immutable operator behavior.
        """
        if not inplace:
            raise TypeError("ClauseGroup.extend() requires keyword argument inplace=True to mutate.")
        if isinstance(other, Literal):
            _ensure_same_model(self, other)
            self.clauses.append(Clause(self._model, [other]))
            return self
        if isinstance(other, Clause):
            _ensure_same_model(self, other)
            self.clauses.append(other)
            return self
        if isinstance(other, ClauseGroup):
            _ensure_same_model(self, other)
            self.clauses.extend(other.clauses)
            self._amo_groups.extend(other._amo_groups)
            self._eo_groups.extend(other._eo_groups)
            return self
        raise TypeError("ClauseGroup.extend() only supports Literal, Clause, or ClauseGroup operands.")

    def __repr__(self) -> str:
        return f"ClauseGroup(n={len(self.clauses)})"


class IntRelation(ClauseGroup):
    """ClauseGroup with relation metadata for full Boolean reification.

    This represents a normalized integer relation of the form:
    ``lhs + offset OP rhs`` where ``OP`` is one of ``<=,<,>=,>``.
    """

    __slots__ = ("lhs", "rhs", "op", "offset")

    def __init__(self, model: "Model", clauses: Sequence["Clause"], lhs: "IntVar", rhs: "IntVar", op: str, offset: int = 0):
        super().__init__(model, clauses)
        self.lhs = lhs
        self.rhs = rhs
        self.op = op
        self.offset = int(offset)

    def _negated(self) -> ClauseGroup:
        if self.op == "<=":
            return self.lhs._relop_intvar(self.rhs, ">", self.offset)  # type: ignore[return-value]
        if self.op == "<":
            return self.lhs._relop_intvar(self.rhs, ">=", self.offset)  # type: ignore[return-value]
        if self.op == ">=":
            return self.lhs._relop_intvar(self.rhs, "<", self.offset)  # type: ignore[return-value]
        if self.op == ">":
            return self.lhs._relop_intvar(self.rhs, "<=", self.offset)  # type: ignore[return-value]
        if self.op == "==":
            return self.lhs._relop_intvar(self.rhs, "!=", self.offset)  # type: ignore[return-value]
        raise ValueError(f"Unsupported relation operator {self.op!r}")

    def reify(self, indicator: "Literal") -> ClauseGroup:
        """Return full equivalence ``indicator <-> relation``."""
        _ensure_same_model(self, indicator)
        fwd = self.only_if(indicator)
        rev = self._negated().only_if(~indicator)
        return ClauseGroup(self._model, [*fwd.clauses, *rev.clauses])


class Clause:
    """Single CNF clause (disjunction of literals)."""
    __slots__ = ("_model", "literals")

    def __init__(self, model: "Model", literals: Sequence["Literal"]):
        self._model = model
        self.literals = list(literals)

    @classmethod
    def from_iterable(cls, literals: Iterable["Literal"]) -> "Clause":
        """Build a clause from an iterable of literals.

        Raises:
            ValueError: If the iterable is empty.
            ValueError: If literals belong to different models.
        """
        lits = list(literals)
        if not lits:
            raise ValueError("Clause.from_iterable requires at least one literal")
        model = _ensure_same_model(*lits)
        return cls(model, lits)

    def __or__(self, other):
        if isinstance(other, Literal):
            _ensure_same_model(self, other)
            return Clause(self._model, [*self.literals, other])
        raise TypeError("Clause OR only supports Literal operands.")

    def __ior__(self, other):
        # Immutable-by-operator contract: `x |= y` returns a new Clause.
        return self.__or__(other)

    def append(self, literal: "Literal", *, inplace: bool = False) -> "Clause":
        """Append a literal to this clause when ``inplace=True``.

        Warning:
            Mutation requires ``inplace=True``. Prefer ``clause | lit`` (or
            ``clause |= lit`` with rebinding semantics) for immutable operator behavior.
        """
        if not inplace:
            raise TypeError("Clause.append() requires keyword argument inplace=True to mutate.")
        if not isinstance(literal, Literal):
            raise TypeError("Clause.append() expects a Literal.")
        _ensure_same_model(self, literal)
        self.literals.append(literal)
        return self

    def __invert__(self):
        raise TypeError("Cannot directly negate a Clause. Negate literals individually to maintain strict CNF.")

    def __and__(self, other):
        if isinstance(other, Literal):
            _ensure_same_model(self, other)
            return ClauseGroup(self._model, [self, Clause(self._model, [other])])
        if isinstance(other, Clause):
            _ensure_same_model(self, other)
            return ClauseGroup(self._model, [self, other])
        if isinstance(other, ClauseGroup):
            _ensure_same_model(self, other)
            return ClauseGroup(self._model, [self, *other.clauses])
        raise TypeError("AND only supports Literal, Clause, or ClauseGroup operands.")

    def only_if(self, condition: "Literal") -> "Clause":
        """Return a gated clause enforcing this clause only when ``condition`` is true.

        Semantics: ``condition -> clause``.
        """
        if not isinstance(condition, Literal):
            raise _detection_error()
        _ensure_same_model(self, condition)
        return Clause(self._model, [*self.literals, ~condition])

    def implies(self, target):
        """Return CNF encoding of ``self -> target``.

        Clause implication is distributed over source literals:
        ``(a | b) -> X`` becomes ``(a -> X) & (b -> X)``.
        """
        # (a | b) -> X  == (a -> X) & (b -> X)
        parts: list[Clause] = []
        for lit in self.literals:
            out = lit.implies(target)
            if isinstance(out, Clause):
                parts.append(out)
            elif isinstance(out, ClauseGroup):
                parts.extend(out.clauses)
            elif isinstance(out, PBConstraint):
                parts.extend(out.clauses().clauses)
            else:
                raise TypeError("Unsupported implication target.")
        return ClauseGroup(self._model, parts)

    def __repr__(self) -> str:
        return f"Clause({self.literals!r})"


class Literal:
    """Boolean literal bound to a :class:`Model` variable id and polarity."""
    __slots__ = ("_model", "id", "name", "polarity", "_neg")
    __hash__ = object.__hash__

    def __init__(self, model: "Model", id_: int, name: str, polarity: bool = True):
        self._model = model
        self.id = id_
        self.name = name
        self.polarity = polarity
        self._neg: Optional["Literal"] = None

    def _link_negation(self, other: "Literal") -> None:
        self._neg = other

    def __invert__(self) -> "Literal":
        # Negation objects are created in pairs by Model.
        return self._neg if self._neg is not None else Literal(self._model, self.id, self.name, not self.polarity)

    def __or__(self, other):
        if isinstance(other, Literal):
            _ensure_same_model(self, other)
            return Clause(self._model, [self, other])
        if isinstance(other, Clause):
            return other.__or__(self)
        raise TypeError("OR only supports Literal or Clause.")

    def __and__(self, other):
        if isinstance(other, Literal):
            _ensure_same_model(self, other)
            return ClauseGroup(
                self._model,
                [Clause(self._model, [self]), Clause(self._model, [other])],
            )
        if isinstance(other, Clause):
            _ensure_same_model(self, other)
            return ClauseGroup(self._model, [Clause(self._model, [self]), other])
        if isinstance(other, ClauseGroup):
            _ensure_same_model(self, other)
            return ClauseGroup(self._model, [Clause(self._model, [self]), *other.clauses])
        raise TypeError("AND only supports Literal operands.")

    def __eq__(self, other):  # type: ignore[override]
        if isinstance(other, IntRelation):
            _ensure_same_model(self, other)
            return other.reify(self)
        if not isinstance(other, Literal):
            return False
        if self is other:
            return True
        _ensure_same_model(self, other)
        # Boolean equivalence: (self -> other) & (other -> self)
        return ClauseGroup(
            self._model,
            [
                Clause(self._model, [~self, other]),
                Clause(self._model, [~other, self]),
            ],
        )

    def __ne__(self, other):  # type: ignore[override]
        if isinstance(other, IntRelation):
            _ensure_same_model(self, other)
            return other.reify(~self)
        if not isinstance(other, Literal):
            return True
        # Keep Python inequality boolean-stable for now; modeling inequality can
        # be added explicitly later if needed.
        return not (self is other)

    def __mul__(self, other):
        if isinstance(other, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
            raise _nonlinear_error(self, other)
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            return Term(other, self)
        raise TypeError("Only numeric (int/float) * literal multiplication is allowed.")

    def __rmul__(self, other):
        return self.__mul__(other)

    def __add__(self, other):
        return PBExpr.from_item(self).__add__(other)

    def __radd__(self, other):
        return PBExpr.from_item(other).__add__(self)

    def __sub__(self, other):
        return PBExpr.from_item(self).__sub__(other)

    def __rsub__(self, other):
        return PBExpr.from_item(other).__sub__(self)

    def only_if(self, condition: "Literal") -> Clause:
        """Return a gated unit clause enforcing this literal only if ``condition`` is true."""
        if not isinstance(condition, Literal):
            raise _detection_error()
        _ensure_same_model(self, condition)
        return Clause(self._model, [self, ~condition])

    def implies(self, target):
        """Return encoding of ``self -> target``.

        Supported targets include ``Literal``, ``Clause``, ``ClauseGroup``, and
        lazy :class:`PBConstraint`.
        """
        # source -> target  <=>  target.only_if(source)
        if isinstance(target, Literal):
            _ensure_same_model(self, target)
            return target.only_if(self)
        if isinstance(target, Clause):
            _ensure_same_model(self, target)
            return target.only_if(self)
        if isinstance(target, ClauseGroup):
            _ensure_same_model(self, target)
            return target.only_if(self)
        if isinstance(target, PBConstraint):
            _ensure_same_model(self, target)
            return target.only_if(self)
        raise TypeError("Unsupported implication target.")

    def __repr__(self) -> str:
        sign = "" if self.polarity else "~"
        return f"{sign}{self.name}"


@dataclass(frozen=True)
class Term:
    """Weighted literal term used inside :class:`PBExpr`."""
    coefficient: int | float
    literal: Literal

    def __post_init__(self):
        if isinstance(self.coefficient, bool) or not isinstance(self.coefficient, (int, float)):
            raise TypeError("Term coefficient must be int or float")
        if not isinstance(self.literal, Literal):
            raise TypeError("Term literal must be Literal")

    def __mul__(self, other):
        raise _nonlinear_error(self, other)

    def __rmul__(self, other):
        raise _nonlinear_error(other, self)

    def __add__(self, other):
        return PBExpr.from_item(self).__add__(other)

    def __radd__(self, other):
        return PBExpr.from_item(other).__add__(self)

    def __sub__(self, other):
        return PBExpr.from_item(self).__sub__(other)

    def __rsub__(self, other):
        return PBExpr.from_item(other).__sub__(self)

    def __iadd__(self, other):
        # Immutable-by-operator contract: `x += y` returns a new PBExpr.
        return PBExpr.from_item(self).__add__(other)

    def __isub__(self, other):
        # Immutable-by-operator contract: `x -= y` returns a new PBExpr.
        return PBExpr.from_item(self).__sub__(other)

    def _finalize_compare(self, op: str, rhs) -> "ClauseGroup":
        return PBExpr.from_item(self)._finalize_compare(op, rhs)

    def __le__(self, rhs):
        return self._finalize_compare("<=", rhs)

    def __lt__(self, rhs):
        return self._finalize_compare("<", rhs)

    def __ge__(self, rhs):
        return self._finalize_compare(">=", rhs)

    def __gt__(self, rhs):
        return self._finalize_compare(">", rhs)


class _LazyIntExpr:
    """Lazy derived integer expression that materializes through ``Model`` on demand."""

    __slots__ = ("_model", "_realized")

    def __init__(self, model: "Model"):
        self._model = model
        self._realized: IntVar | None = None

    def _realize(self) -> "IntVar":
        raise NotImplementedError

    def _as_pbexpr(self) -> "PBExpr":
        return PBExpr.from_item(self)

    def __mul__(self, other):
        if isinstance(other, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
            raise _nonlinear_error(self, other)
        if isinstance(other, int):
            return PBExpr(self._model, [], 0, int_terms=[(other, self)])
        raise TypeError("Only integer scaling is supported for Int-like expressions")

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

    def __le__(self, rhs):
        return self._as_pbexpr().__le__(rhs)

    def __lt__(self, rhs):
        return self._as_pbexpr().__lt__(rhs)

    def __ge__(self, rhs):
        return self._as_pbexpr().__ge__(rhs)

    def __gt__(self, rhs):
        return self._as_pbexpr().__gt__(rhs)

    def __floordiv__(self, divisor: int):
        if isinstance(divisor, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
            raise _nonlinear_error(self, divisor, op="//")
        return DivExpr(self, divisor)

    def scale(self, factor: int):
        """Return a lazy derived integer expression for ``self * factor``."""
        if isinstance(factor, bool):
            raise ValueError("Scale factor must be strictly positive.")
        if not isinstance(factor, int):
            raise TypeError("Scale factor must be an integer.")
        if factor <= 0:
            raise ValueError("Scale factor must be strictly positive.")
        return ScaleExpr(self, factor)

    def __eq__(self, rhs):  # type: ignore[override]
        try:
            return self._as_pbexpr().__eq__(rhs)
        except TypeError:
            return False

    @property
    def lb(self) -> int:  # pragma: no cover - overridden by subclasses
        """Lower bound for this lazy integer expression."""
        raise NotImplementedError

    @property
    def ub(self) -> int:  # pragma: no cover - overridden by subclasses
        """Upper bound (exclusive) for this lazy integer expression."""
        raise NotImplementedError


class DivExpr(_LazyIntExpr):
    """Lazy ``IntVar // constant`` derived integer expression."""

    __slots__ = ("_src", "_divisor", "_lb", "_ub")

    def __init__(self, src: "IntVar | _LazyIntExpr", divisor: int):
        super().__init__(src._model)
        self._src = src
        self._divisor = divisor
        self._lb = src.lb // divisor
        self._ub = ((src.ub - 1) // divisor) + 1

    @property
    def lb(self) -> int:
        """Lower bound of this lazy quotient expression."""
        return self._lb

    @property
    def ub(self) -> int:
        """Upper bound (exclusive) of this lazy quotient expression."""
        return self._ub

    def _realize(self) -> "IntVar":
        if self._realized is None:
            self._realized = self._model.floor_div(self._src, self._divisor)
        return self._realized


class ScaleExpr(_LazyIntExpr):
    """Lazy ``IntVar * constant`` derived integer expression."""

    __slots__ = ("_src", "_factor", "_lb", "_ub")

    def __init__(self, src: "IntVar | _LazyIntExpr", factor: int):
        super().__init__(src._model)
        self._src = src
        self._factor = factor
        self._lb = src.lb * factor
        self._ub = ((src.ub - 1) * factor) + 1

    @property
    def lb(self) -> int:
        """Lower bound of this lazy scaled expression."""
        return self._lb

    @property
    def ub(self) -> int:
        """Upper bound (exclusive) of this lazy scaled expression."""
        return self._ub

    def _realize(self) -> "IntVar":
        if self._realized is None:
            self._realized = self._model.scale(self._src, self._factor)
        return self._realized


class MaxExpr(_LazyIntExpr):
    """Lazy vector aggregate/bound derived integer expression."""

    __slots__ = ("_items", "_kind", "_name", "_lb", "_ub")

    def __init__(self, model: "Model", items: Sequence["IntVar"], kind: str, name: Optional[str] = None):
        super().__init__(model)
        self._items = tuple(items)
        self._kind = kind
        self._name = name
        assert kind in {"max", "min", "upper_bound", "lower_bound"}, f"Unknown aggregate kind {kind!r}"
        if kind in {"max", "upper_bound"}:
            self._lb = max(x.lb for x in self._items)
            self._ub = max(x.ub for x in self._items)
        else:
            self._lb = min(x.lb for x in self._items)
            self._ub = min(x.ub for x in self._items)

    @property
    def lb(self) -> int:
        """Lower bound of this lazy aggregate expression."""
        return self._lb

    @property
    def ub(self) -> int:
        """Upper bound (exclusive) of this lazy aggregate expression."""
        return self._ub

    def _realize(self) -> "IntVar":
        if self._realized is None:
            assert self._kind in {"max", "min", "upper_bound", "lower_bound"}, f"Unknown aggregate kind {self._kind!r}"
            if self._kind == "max":
                self._realized = self._model.max(self._items, name=self._name)
            elif self._kind == "min":
                self._realized = self._model.min(self._items, name=self._name)
            elif self._kind == "upper_bound":
                self._realized = self._model.upper_bound(self._items, name=self._name)
            else:
                self._realized = self._model.lower_bound(self._items, name=self._name)
        return self._realized


class PBExpr:
    """Pseudo-Boolean expression (weighted sum of literals / lifted Int variables)."""
    __slots__ = ("_model", "terms", "constant", "int_terms")

    def __init__(
        self,
        model: "Model",
        terms: Sequence[Term] | None = None,
        constant: int = 0,
        int_terms: Sequence[tuple[int, IntVar | _LazyIntExpr]] | None = None,
    ):
        self._model = model
        self.terms = self._collapse_terms(list(terms or []))
        self.constant = int(constant)
        self.int_terms = [(int(c), v) for c, v in (int_terms or []) if int(c) != 0]

    @staticmethod
    def _collapse_terms(terms: list[Term]) -> list[Term]:
        # Collapse repeated identical literals (same var + polarity) by summing
        # coefficients. We intentionally do not fold x and ~x together here since
        # that would introduce an offset; offset normalization is handled later in
        # encoder dispatch.
        if not terms:
            return []
        acc: dict[tuple[int, bool], int | float] = {}
        lit_ref: dict[tuple[int, bool], Literal] = {}
        order: list[tuple[int, bool]] = []
        for t in terms:
            key = (t.literal.id, t.literal.polarity)
            if key not in acc:
                acc[key] = 0
                lit_ref[key] = t.literal
                order.append(key)
            prev = acc[key]
            coeff = t.coefficient
            if isinstance(prev, float) or isinstance(coeff, float):
                acc[key] = float(prev) + float(coeff)
            else:
                acc[key] = int(prev) + int(coeff)
        out: list[Term] = []
        for key in order:
            coeff = acc[key]
            if isinstance(coeff, float):
                if abs(coeff) <= 1e-12:
                    continue
                out.append(Term(coeff, lit_ref[key]))
            elif coeff != 0:
                out.append(Term(coeff, lit_ref[key]))
        return out

    @classmethod
    def from_item(cls, item) -> "PBExpr":
        """Convert a supported item into a ``PBExpr``.

        Supported inputs: ``PBExpr``, ``Term``, ``Literal``, ``IntVar``, and
        integer constants.
        """
        if isinstance(item, PBExpr):
            return item
        if isinstance(item, Term):
            return cls(item.literal._model, [item], 0)
        if isinstance(item, Literal):
            return cls(item._model, [Term(1, item)], 0)
        if isinstance(item, IntVar):
            return item._as_pbexpr()
        if isinstance(item, _LazyIntExpr):
            return cls(item._model, [], 0, int_terms=[(1, item)])
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            # Constants are carried and normalized during PB compilation. This
            # keeps algebraic forms like `a + b + 2 <= 3` equivalent to
            # `a + b <= 1` in the public DSL.
            return cls(None, [], item)  # type: ignore[arg-type]
        raise TypeError(f"Unsupported PB item: {type(item)!r}")

    def _merge(self, other: "PBExpr", sign: int = 1) -> "PBExpr":
        model = _ensure_same_model(self, other)
        terms = [*self.terms, *(Term(sign * t.coefficient, t.literal) for t in other.terms)]
        int_terms = [*self.int_terms, *((sign * c, v) for c, v in other.int_terms)]
        return PBExpr(model, terms, self.constant + sign * other.constant, int_terms=int_terms)

    def _realize_int_terms(self, model: "Model") -> "PBExpr":
        if not self.int_terms:
            return self
        _ensure_same_model(self, model)
        out = PBExpr(model, self.terms, self.constant)
        for coeff, item in self.int_terms:
            if isinstance(item, _LazyIntExpr):
                iv = item._realize()
            else:
                iv = item
            out = out + (coeff * iv)
        return out

    def __add__(self, other):
        return self._merge(PBExpr.from_item(other), +1)

    def __radd__(self, other):
        return PBExpr.from_item(other)._merge(self, +1)

    def __sub__(self, other):
        return self._merge(PBExpr.from_item(other), -1)

    def __rsub__(self, other):
        return PBExpr.from_item(other)._merge(self, -1)

    def __iadd__(self, other):
        # Immutable-by-operator contract: `x += y` returns a new PBExpr.
        return self._merge(PBExpr.from_item(other), +1)

    def __isub__(self, other):
        # Immutable-by-operator contract: `x -= y` returns a new PBExpr.
        return self._merge(PBExpr.from_item(other), -1)

    def __mul__(self, other):
        if isinstance(other, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
            raise _nonlinear_error(self, other)
        if isinstance(other, bool):
            raise TypeError("PBExpr scalar multiplication requires an integer (bool is not allowed)")
        if not isinstance(other, int):
            raise TypeError("PBExpr scalar multiplication requires an integer")
        return PBExpr(
            self._model,
            [Term(other * t.coefficient, t.literal) for t in self.terms],
            other * self.constant,
            int_terms=[(other * c, v) for c, v in self.int_terms],
        )

    def __rmul__(self, other):
        return self.__mul__(other)

    def __floordiv__(self, other):
        if isinstance(other, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
            raise _nonlinear_error(self, other, op="//")
        raise TypeError(
            "Floor division is only supported on IntVar/Int-like expressions with an integer constant divisor."
        )

    def __rfloordiv__(self, other):
        if isinstance(other, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
            raise _nonlinear_error(other, self, op="//")
        raise TypeError(
            "Floor division is only supported on IntVar/Int-like expressions with an integer constant divisor."
        )

    def __neg__(self):
        return PBExpr(
            self._model,
            [Term(-t.coefficient, t.literal) for t in self.terms],
            -self.constant,
            int_terms=[(-c, v) for c, v in self.int_terms],
        )

    def __pos__(self):
        return self

    def add(self, other, *, inplace: bool = False) -> "PBExpr":
        """Add a PB-compatible item to this expression when ``inplace=True``.

        Warning:
            Mutation requires ``inplace=True``. Prefer ``expr + x`` (or
            ``expr += x`` with rebinding semantics) for immutable operator behavior.
        """
        if not inplace:
            raise TypeError("PBExpr.add() requires keyword argument inplace=True to mutate.")
        other_expr = PBExpr.from_item(other)
        model = _ensure_same_model(self, other_expr)
        if self._model is None:
            self._model = model
        if other_expr.terms:
            self.terms = self._collapse_terms([*self.terms, *other_expr.terms])
        self.constant = self.constant + other_expr.constant
        if other_expr.int_terms:
            self.int_terms.extend((int(c), v) for c, v in other_expr.int_terms if int(c) != 0)
            self.int_terms = [(int(c), v) for c, v in self.int_terms if int(c) != 0]
        return self

    def sub(self, other, *, inplace: bool = False) -> "PBExpr":
        """Subtract a PB-compatible item from this expression when ``inplace=True``.

        Warning:
            Mutation requires ``inplace=True``. Prefer ``expr - x`` (or
            ``expr -= x`` with rebinding semantics) for immutable operator behavior.
        """
        if not inplace:
            raise TypeError("PBExpr.sub() requires keyword argument inplace=True to mutate.")
        other_expr = PBExpr.from_item(other)
        model = _ensure_same_model(self, other_expr)
        if self._model is None:
            self._model = model
        if other_expr.terms:
            neg_terms = [Term(-t.coefficient, t.literal) for t in other_expr.terms]
            self.terms = self._collapse_terms([*self.terms, *neg_terms])
        self.constant = self.constant - other_expr.constant
        if other_expr.int_terms:
            self.int_terms.extend((-int(c), v) for c, v in other_expr.int_terms if int(c) != 0)
            self.int_terms = [(int(c), v) for c, v in self.int_terms if int(c) != 0]
        return self

    def _finalize_compare(self, op: str, rhs):
        rhs_expr = PBExpr.from_item(rhs)
        model = _ensure_same_model(self, rhs_expr)
        if model is None:
            raise TypeError("Cannot compare constant-only PB expressions")
        return PBConstraint(model, self, op, rhs_expr)

    def __le__(self, rhs):
        return self._finalize_compare("<=", rhs)

    def __lt__(self, rhs):
        return self._finalize_compare("<", rhs)

    def __ge__(self, rhs):
        return self._finalize_compare(">=", rhs)

    def __gt__(self, rhs):
        return self._finalize_compare(">", rhs)

    def __eq__(self, rhs):  # type: ignore[override]
        try:
            return self._finalize_compare("==", rhs)
        except TypeError:
            return False

    def __repr__(self) -> str:
        return f"PBExpr(terms={self.terms!r}, int_terms={self.int_terms!r}, c={self.constant})"


class PBConstraint:
    """Immutable lazy PB comparator descriptor compiled on demand.

    Instances are produced by comparing :class:`PBExpr` objects (or compatible
    operands) and preserve comparator metadata until compilation.
    """

    __slots__ = ("_model", "_lhs", "_op", "_rhs", "_conditions", "_compiled")

    def __init__(
        self,
        model: "Model",
        lhs: PBExpr,
        op: str,
        rhs: PBExpr,
        conditions: Sequence[Literal] | None = None,
    ):
        self._model = model
        self._lhs = lhs
        self._op = op
        self._rhs = rhs
        self._conditions = tuple(conditions or ())
        self._compiled: ClauseGroup | None = None

    def only_if(self, condition: Literal) -> "PBConstraint":
        """Return a new PB constraint gated by a literal.

        Semantics: ``condition -> PB``.
        """
        if not isinstance(condition, Literal):
            raise _detection_error()
        _ensure_same_model(self, condition)
        return PBConstraint(self._model, self._lhs, self._op, self._rhs, [*self._conditions, condition])

    def _negated(self) -> "PBConstraint | tuple[PBConstraint, PBConstraint]":
        # Logical negation of the PB comparator. Equality negation is a disjunction.
        if self._op == "<=":
            return PBConstraint(self._model, self._lhs, ">", self._rhs)
        if self._op == "<":
            return PBConstraint(self._model, self._lhs, ">=", self._rhs)
        if self._op == ">=":
            return PBConstraint(self._model, self._lhs, "<", self._rhs)
        if self._op == ">":
            return PBConstraint(self._model, self._lhs, "<=", self._rhs)
        if self._op == "==":
            return (
                PBConstraint(self._model, self._lhs, "<", self._rhs),
                PBConstraint(self._model, self._lhs, ">", self._rhs),
            )
        raise ValueError(f"Unsupported comparator {self._op!r}")

    def implies(self, target):
        """Return encoding of ``PB -> literal`` for the supported safe subset.

        The target must be a :class:`Literal`. The implementation uses safe
        contrapositive rewrites (and a selector split for equality antecedents).
        """
        # Safe subset: PB antecedent may imply a Literal via contrapositive.
        if not isinstance(target, Literal):
            raise _detection_error()
        if self._conditions:
            # This object already represents a gated implication-like form.
            # Using it as an antecedent creates a complex source.
            raise _detection_error()
        _ensure_same_model(self, target)
        neg = self._negated()
        if isinstance(neg, PBConstraint):
            return neg.only_if(~target)

        # Equality antecedent: (~target) -> (A OR B), where A/B are PB constraints.
        # Encode the disjunction with a selector and two half-reified branches.
        left, right = neg
        sel = self._model.bool()  # anonymous internal branch selector
        g_left = left.only_if(~target).only_if(sel).clauses()
        g_right = right.only_if(~target).only_if(~sel).clauses()
        return g_left & g_right

    def clauses(self) -> ClauseGroup:
        """Compile to a :class:`ClauseGroup` and cache the result."""
        if self._compiled is not None:
            return self._compiled
        group = self._model._compile_pb_compare(self._lhs, self._op, self._rhs)
        for cond in self._conditions:
            group = group.only_if(cond)
        self._compiled = group
        return group

    def __repr__(self) -> str:
        return f"PBConstraint(op={self._op!r}, gated={len(self._conditions)})"


class _ObjectiveProxy:
    __slots__ = ("_model", "_lit_to_sid", "_offset")

    def __init__(self, model: "Model"):
        self._model = model
        self._lit_to_sid: dict[int, int] = {}
        self._offset: int = 0

    def __getitem__(self, weight: int) -> "_WeightBucket":
        self._model._ensure_no_tier_objective_active()
        scaled, raw = self._model._coerce_soft_weight(weight, allow_zero=False)
        return _WeightBucket(self._model, scaled, raw)

    def __setitem__(self, weight: int, value) -> None:
        # Required for Python's `obj[key] += x` protocol. The mutation is already
        # performed by WeightBucket.__iadd__; this assignment is a no-op.
        return None

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
                if abs(coeff_raw) <= 1e-12:
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
        if float(offset_raw) > 1e-12:
            pos_w = int(offset_raw) if isinstance(offset_raw, int) else float(offset_raw)
            pos_off, _ = self._model._coerce_soft_weight(pos_w, allow_zero=False)
            false_lit = self._model._get_bool_constant_literal(False)
            dim_false = self._model._lit_to_dimacs(false_lit)
            lit_weights[dim_false] = lit_weights.get(dim_false, 0) + int(pos_off)
        elif float(offset_raw) < -1e-12:
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
        for dim, sid in self._lit_to_sid.items():
            idx = m._soft_id_to_index.get(int(sid))
            if idx is None:
                continue
            w, _ = m._soft[idx]
            if int(w) > 0:
                out[int(dim)] = int(w)
        return out

    def _apply_lit_weights(self, lit_weights: dict[int, int], offset: int):
        m = self._model
        hard0 = len(m._hard)
        soft0 = len(m._soft)
        all_lits = set(self._lit_to_sid.keys()) | set(lit_weights.keys())
        for dim in all_lits:
            sid = self._lit_to_sid.get(dim)
            new_w = int(lit_weights.get(dim, 0))
            if sid is None:
                if new_w <= 0:
                    continue
                lit = m._dimacs_to_lit(dim)
                m._ensure_literal_def_realized(lit)
                sid = m._append_soft_entry(new_w, Clause(m, [lit]), group_id=None)
                self._lit_to_sid[dim] = sid
                continue
            idx = m._soft_id_to_index[sid]
            old_w, _cl = m._soft[idx]
            if int(old_w) == new_w:
                continue
            m._set_soft_weight_internal(sid, new_w, allow_zero=True, allow_when_sat=True)

        delta = int(offset) - int(self._offset)
        if delta:
            m._objective_constant += int(delta)
        self._offset = int(offset)
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
        merged = self._current_lit_weights()
        for dim, w in add_map.items():
            merged[int(dim)] = int(merged.get(int(dim), 0)) + int(w)
        merged = {d: int(w) for d, w in merged.items() if int(w) > 0}
        return self._apply_lit_weights(merged, int(self._offset) + int(add_offset))

    def clear(self):
        """Disable all expression-managed objective terms."""
        for sid in list(self._model._soft_ids):
            idx = self._model._soft_id_to_index.get(int(sid))
            if idx is None:
                continue
            old_w, _ = self._model._soft[idx]
            if int(old_w) > 0:
                self._model._set_soft_weight_internal(int(sid), 0, allow_zero=True, allow_when_sat=True)
        self._lit_to_sid.clear()
        if self._offset:
            self._model._objective_constant -= int(self._offset)
        self._offset = 0
        return self

    def replace_with(self, constraint):
        """Replace the currently active objective with ``constraint``."""
        self._model._ensure_no_tier_objective_active()
        # Full objective replacement semantics:
        # disable all currently active soft clauses first, then install the new
        # expression-managed objective.
        for sid in list(self._model._soft_ids):
            idx = self._model._soft_id_to_index.get(int(sid))
            if idx is None:
                continue
            old_w, _ = self._model._soft[idx]
            if int(old_w) > 0:
                self._model._set_soft_weight_internal(int(sid), 0, allow_zero=True, allow_when_sat=True)
        self._lit_to_sid.clear()
        if self._offset:
            self._model._objective_constant -= int(self._offset)
        self._offset = 0
        return self.set(constraint)

    def __iadd__(self, constraint):
        """Add a weighted objective term directly with implicit weight 1.

        Examples:
            ``model.obj += (3 * a + 2 * b)``
            ``model.obj += sum(weights[i] * lits[i] for i in range(n))``
        """
        self._model._ensure_no_tier_objective_active()
        # Preserve legacy soft semantics for literal/clause-style constraints.
        # Route arithmetic-style expressions to linear objective lowering.
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
        # Match ObjectiveProxy.__iadd__ dispatch to keep backward-compatible
        # soft semantics for literal/clause constraints.
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
                if abs(coeff_raw) <= 1e-12:
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
        if float(offset_raw) > 1e-12:
            pos_w = int(offset_raw) if isinstance(offset_raw, int) else float(offset_raw)
            pos_off, _ = self._model._coerce_soft_weight(pos_w, allow_zero=False)
            false_lit = self._model._get_bool_constant_literal(False)
            dim_false = self._model._lit_to_dimacs(false_lit)
            lit_weights[dim_false] = lit_weights.get(dim_false, 0) + int(pos_off)
        elif float(offset_raw) < -1e-12:
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
            if not group.clauses:
                return
            if len(group.clauses) == 1:
                c = group.clauses[0]
                if len(c.literals) == 0:
                    raise TypeError("Tier objective does not support empty soft clauses.")
                if len(c.literals) == 1:
                    lit = c.literals[0]
                else:
                    r = self._model.bool()
                    self._model &= c.only_if(r)
                    lit = ~r
                dim = self._model._lit_to_dimacs(lit)
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


class EnumVar:
    """Finite-domain categorical variable encoded as choice literals."""
    __slots__ = ("_model", "name", "choices", "nullable", "_choice_lits")

    def __init__(self, model: "Model", name: str, choices: Sequence[str], nullable: bool):
        self._model = model
        self.name = name
        self.choices = list(choices)
        self.nullable = bool(nullable)
        self._choice_lits = {c: model.bool(f"{name}::{c}") for c in self.choices}
        self._add_domain_constraints()

    def _add_domain_constraints(self) -> None:
        lits = [self._choice_lits[c] for c in self.choices]
        if not lits:
            return
        # Route enum domains through the same deferred unit-cardinality path used
        # elsewhere so they can be harvested as AMO/EO structure later.
        self._model &= (sum_expr(lits) <= 1)
        if not self.nullable:
            self._model &= (sum_expr(lits) == 1)

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
            _ensure_same_model(self, other)
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
                    clauses.extend(eq.clauses)
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
            _ensure_same_model(self, other)
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
        if op == "<=":
            return lhs <= rhs
        if op == "<":
            return lhs < rhs
        if op == ">=":
            return lhs >= rhs
        if op == ">":
            return lhs > rhs
        if op == "==":
            return lhs == rhs
        if op == "!=":
            return lhs != rhs
        raise ValueError(f"Unsupported comparator {op!r}")

    def _rhs_constraint(self, op: str, rhs, array_val: int):
        if isinstance(rhs, int):
            return self._cmp_int(array_val, op, rhs)
        if isinstance(rhs, IntVar):
            _ensure_same_model(self, rhs)
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
        for k in range(idx.lb, idx.ub):
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
                    clauses.extend(neq.clauses)
                continue

            # (idx == k) -> branch
            idx_eq_k = (idx == k)
            assert isinstance(idx_eq_k, Literal), "IntVar.__eq__(int) must return Literal in-domain"

            if isinstance(branch, PBConstraint):
                clauses.extend(branch.only_if(idx_eq_k).clauses().clauses)
            else:
                clauses.extend(self._model._as_clausegroup(branch).only_if(idx_eq_k).clauses)
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
            if op == "<=":
                return item <= rhs
            if op == "<":
                return item < rhs
            if op == ">=":
                return item >= rhs
            if op == ">":
                return item > rhs
            if op == "==":
                return item == rhs
            if op == "!=":
                return item != rhs
            raise ValueError(f"Unsupported comparator {op!r}")
        if isinstance(rhs, IntVar):
            _ensure_same_model(self, rhs)
            if op == "<=":
                return item <= rhs
            if op == "<":
                return item < rhs
            if op == ">=":
                return item >= rhs
            if op == ">":
                return item > rhs
            if op == "==":
                return item == rhs
            if op == "!=":
                return item != rhs
            raise ValueError(f"Unsupported comparator {op!r}")
        raise TypeError(f"Vector element comparison does not support RHS {type(rhs)!r}")

    def _evaluate_comparator(self, op: str, rhs) -> ClauseGroup:
        clauses: list[Clause] = []
        idx = self._index_var
        for k in range(idx.lb, idx.ub):
            item_pos = k - idx.lb
            item = self._items[item_pos]
            branch = self._rhs_constraint(op, rhs, item)

            idx_eq_k = (idx == k)
            assert isinstance(idx_eq_k, Literal), "IntVar.__eq__(int) must return Literal in-domain"

            clauses.extend(self._model._as_clausegroup(branch).only_if(idx_eq_k).clauses)
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
    """Bounded integer variable with ladder/order encoding semantics.

    Domain semantics are ``[lb, ub)`` (upper bound excluded).
    """
    __slots__ = ("_model", "name", "lb", "ub", "_threshold_lits", "_eq_lits", "_cmp_cache")

    def __init__(self, model: "Model", name: str, lb: int, ub: int):
        if not isinstance(lb, int) or not isinstance(ub, int):
            raise TypeError("lb and ub must be ints")
        if ub <= lb:
            raise ValueError("Int domain must satisfy lb < ub")
        self._model = model
        self.name = name
        self.lb = lb
        self.ub = ub
        span = ub - lb
        # Compact order/ladder representation:
        # for domain [lb, ub), we only need (span - 1) threshold bits.
        # Each bit i encodes (x >= lb + i + 1).
        # This removes one variable and the old "forbid all-true" clause.
        self._threshold_lits = [model.bool(f"{name}<=#{i}") for i in range(max(0, span - 1))]
        for idx, lit in enumerate(self._threshold_lits):
            model._intvar_threshold_owner_by_litid[lit.id] = (self, idx)
        self._eq_lits: dict[int, Literal] = {}
        self._cmp_cache: dict[tuple[str, int], Literal] = {}
        self._add_domain_constraints()

    def _add_domain_constraints(self) -> None:
        # Prefix-true unary encoding over (span - 1) bits.
        # Valid assignments are t0..tk-1 = true, tk.. = false.
        # With (span - 1) bits, count_true is naturally in [0, span-1], matching
        # domain [lb, ub) without an extra "forbid all-true" clause.
        ts = self._threshold_lits
        for i in range(len(ts) - 1):
            # t_{i+1} -> t_i
            self._model._hard.append(Clause(self._model, [~ts[i + 1], ts[i]]))

    def _span(self) -> int:
        return self.ub - self.lb

    def lower_bound(self) -> int:
        """Return the current static lower bound of the integer domain.

        The modeling layer uses half-open domains ``[lb, ub)``, so this returns
        ``lb`` exactly.
        """
        return self.lb

    def upper_bound(self) -> int:
        """Return the current static upper bound (inclusive) of the integer domain.

        Since the internal domain contract is half-open ``[lb, ub)``, the
        greatest admissible integer value is ``ub - 1``.
        """
        return self.ub - 1

    def _as_pbexpr(self) -> PBExpr:
        # Ladder/order encoding semantics: sum(threshold bits) == (value - lb).
        # To preserve true integer arithmetic in mixed PB expressions, we carry
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
        if len(array) < (self.ub - self.lb):
            raise ValueError(
                f"Array length {len(array)} does not cover IntVar domain [{self.lb}, {self.ub})."
            )
        try:
            vals = [int(v) for v in array[: (self.ub - self.lb)]]
        except Exception as e:  # pragma: no cover - defensive conversion failure
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

        # Remaining steps can only affect the domain for thresholds in (lb, ub).
        for threshold, new_value in norm_steps[i:]:
            if threshold >= self.ub:
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
            elif value >= self.ub - 1:
                lit = const(True)
            else:
                idx = value - self.lb
                lit = ~ts[idx]
            cache[key] = lit
            return lit
        if tag == ">=":
            if value <= self.lb:
                lit = const(True)
            elif value >= self.ub:
                lit = const(False)
            else:
                idx = value - self.lb - 1
                lit = ts[idx]
            cache[key] = lit
            return lit
        raise ValueError(f"Unknown comparison tag {tag!r}")

    def _neq_indicator(self, other: "IntVar") -> Literal:
        _ensure_same_model(self, other)
        key = ("!=intvar", id(other))
        if key not in self._cmp_cache:
            d = self._model.bool(f"{self.name}!={other.name}")
            # Make the indicator exact: d=true enforces !=, d=false enforces ==.
            neq = self != other
            eq = self == other
            clauses: list[Clause] = []
            if isinstance(neq, ClauseGroup):
                clauses.extend(neq.only_if(d).clauses)
            if isinstance(eq, ClauseGroup):
                clauses.extend(eq.only_if(~d).clauses)
            if clauses:
                self._model._register_literal_definition(d, ClauseGroup(self._model, clauses))
            self._cmp_cache[key] = d
        return self._cmp_cache[key]

    def _threshold_cuts_with(self, other: "IntVar") -> range:
        # Integer cut values k for predicates (x >= k) that distinguish values in
        # either domain. Cuts are in [min(lb)+1, max(ub)-1] inclusive.
        start = min(self.lb, other.lb) + 1
        stop = max(self.ub, other.ub)  # range stop is exclusive
        return range(start, stop)

    def _exact_value_atoms(self, value: int) -> list[Literal]:
        # Compact exact-value pattern over the ladder bits (at most 2 literals,
        # except span=1 where the only value is tautologically true).
        if value < self.lb or value >= self.ub:
            raise ValueError(f"value {value} is outside domain [{self.lb}, {self.ub})")
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
        if value < self.lb or value >= self.ub:
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
        hi = min(end, self.ub - 1)
        if hi < lo:
            return Clause(m, [m._get_bool_constant_literal(True)])
        if lo == self.lb and hi == self.ub - 1:
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

        # Clip against domain [lb, ub-1].
        lo = max(start, self.lb)
        hi = min(end, self.ub - 1)
        if hi < lo:
            return m._get_bool_constant_literal(False)
        if lo == self.lb and hi == self.ub - 1:
            return m._get_bool_constant_literal(True)

        # Common reductions.
        if lo == hi:
            return self == lo
        if lo == self.lb:
            return self <= hi
        if hi == self.ub - 1:
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
        _ensure_same_model(self, other)
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
            if k >= x.ub:
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
        _ensure_same_model(self, other)
        clauses: list[Clause] = []
        m = self._model

        def ge_state(x: "IntVar", k: int) -> tuple[str, Optional[Literal]]:
            if k <= x.lb:
                return ("true", None)
            if k >= x.ub:
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
            return IntRelation(self._model, self._relop_intvar(other, "<=", offset + 1).clauses, self, other, "<", offset)
        if op == ">":
            # self + offset > other  <=>  self + (offset - 1) >= other
            return IntRelation(self._model, self._relop_intvar(other, ">=", offset - 1).clauses, self, other, ">", offset)
        if op == "==":
            le = self._relop_intvar(other, "<=", offset)
            ge = self._relop_intvar(other, ">=", offset)
            return IntRelation(m, [*le.clauses, *ge.clauses], self, other, "==", offset)
        if op == "!=":
            if offset != 0:
                raise ValueError("IntVar '!=' with offset is not supported")
            return self != other
        raise ValueError(f"Unsupported IntVar relation {op!r}")

    def _eq_indicator(self, other: "IntVar") -> Literal:
        _ensure_same_model(self, other)
        key = ("==intvar", id(other))
        if key not in self._cmp_cache:
            e = self._model.bool(f"{self.name}=={other.name}")
            neq = self != other
            eq = self == other
            clauses: list[Clause] = []
            if isinstance(eq, ClauseGroup):
                clauses.extend(eq.only_if(e).clauses)
            if isinstance(neq, ClauseGroup):
                clauses.extend(neq.only_if(~e).clauses)
            if clauses:
                self._model._register_literal_definition(e, ClauseGroup(self._model, clauses))
            self._cmp_cache[key] = e
        return self._cmp_cache[key]

    def _pattern_for_value(self, value: int) -> list[Literal]:
        if value < self.lb or value >= self.ub:
            raise ValueError(f"value {value} is outside domain [{self.lb}, {self.ub})")
        k = value - self.lb
        ts = self._threshold_lits
        return [*ts[:k], *(~t for t in ts[k:])]

    @staticmethod
    def _forbid_conjunction(model: "Model", left: list[Literal], right: list[Literal]) -> Clause:
        # Forbid all literals in both conjunction patterns from being true together.
        return Clause(model, [*(~lit for lit in left), *(~lit for lit in right)])

    def __le__(self, value: int):
        if isinstance(value, IntVar):
            _ensure_same_model(self, value)
            return self._relop_intvar(value, "<=")
        if isinstance(value, int):
            return self._cmp_lit("<=", value)
        if isinstance(value, (_LazyIntExpr, Literal, Term, PBExpr)):
            _ensure_same_model(self, value)
            return PBExpr.from_item(self)._finalize_compare("<=", value)
        raise TypeError("Int comparisons require an integer or PB-compatible RHS")

    def __lt__(self, value: int):
        if isinstance(value, IntVar):
            _ensure_same_model(self, value)
            return self._relop_intvar(value, "<")
        if isinstance(value, int):
            return self._cmp_lit("<", value)
        if isinstance(value, (_LazyIntExpr, Literal, Term, PBExpr)):
            _ensure_same_model(self, value)
            return PBExpr.from_item(self)._finalize_compare("<", value)
        raise TypeError("Int comparisons require an integer or PB-compatible RHS")

    def __ge__(self, value: int):
        if isinstance(value, IntVar):
            _ensure_same_model(self, value)
            return self._relop_intvar(value, ">=")
        if isinstance(value, int):
            return self._cmp_lit(">=", value)
        if isinstance(value, (_LazyIntExpr, Literal, Term, PBExpr)):
            _ensure_same_model(self, value)
            return PBExpr.from_item(self)._finalize_compare(">=", value)
        raise TypeError("Int comparisons require an integer or PB-compatible RHS")

    def __gt__(self, value: int):
        if isinstance(value, IntVar):
            _ensure_same_model(self, value)
            return self._relop_intvar(value, ">")
        if isinstance(value, int):
            return self._cmp_lit(">", value)
        if isinstance(value, (_LazyIntExpr, Literal, Term, PBExpr)):
            _ensure_same_model(self, value)
            return PBExpr.from_item(self)._finalize_compare(">", value)
        raise TypeError("Int comparisons require an integer or PB-compatible RHS")

    def __eq__(self, value):  # type: ignore[override]
        if isinstance(value, int):
            if value < self.lb or value >= self.ub:
                raise ValueError(f"value {value} is outside domain [{self.lb}, {self.ub})")
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
            _ensure_same_model(self, value)
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
            _ensure_same_model(self, value)
            clauses: list[Clause] = []
            lo = max(self.lb, value.lb)
            hi = min(self.ub, value.ub)
            for v in range(lo, hi):
                # No-new-vars linear encoding: forbid "self == v and other == v"
                # using compact exact-value boundary patterns (clause size <= 4).
                atoms = [*self._exact_value_atoms(v), *value._exact_value_atoms(v)]
                clauses.append(Clause(self._model, [~lit for lit in atoms]))
            return ClauseGroup(self._model, clauses)
        return True


class IntervalVar:
    """Fixed-duration interval variable for scheduling-style constraints.

    The constructor binds two :class:`IntVar` objects, ``start`` and ``end``,
    and enforces ``end == start + duration``. Public horizon semantics are:

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

        # start domain is [start, end - duration + 1) so that start+duration <= end
        start_ub_excl = end - duration + 1
        self.start = model.int(f"{name}.start", lb=start, ub=start_ub_excl)
        # end domain is [start + duration, end + 1) because latest end is inclusive.
        self.end = model.int(f"{name}.end", lb=start + duration, ub=end + 1)

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
        _ensure_same_model(self, other)
        return self.end._relop_intvar(other.start, "<=")

    def starts_after(self, other: "IntervalVar") -> ClauseGroup:
        """Return constraint enforcing ``self.start >= other.end``."""
        if not isinstance(other, IntervalVar):
            raise TypeError("starts_after expects IntervalVar")
        _ensure_same_model(self, other)
        return self.start._relop_intvar(other.end, ">=")

    def no_overlap(self, other: "IntervalVar") -> ClauseGroup:
        """Return disjunctive non-overlap: ``self`` before ``other`` OR vice versa."""
        if not isinstance(other, IntervalVar):
            raise TypeError("no_overlap expects IntervalVar")
        _ensure_same_model(self, other)
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
        expected = getattr(self, "_item_type", object)
        for item in self._items:
            if not isinstance(item, expected):
                raise TypeError(f"{type(self).__name__} expects items of type {expected.__name__}")
            if getattr(item, "_model", model) is not model:
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
        clauses.extend(self._model._as_clausegroup(sel_vec.exactly_one()).clauses)

        for sel, row in zip(sels, norm_rows):
            for item, value in zip(self._items, row):
                c = self._table_cell_constraint(item, value)
                clauses.extend(self._model._as_clausegroup(c).only_if(sel).clauses)

        return ClauseGroup(self._model, clauses)


class _BaseDict:
    """Base class for typed immutable keyed containers."""
    __slots__ = ("_model", "name", "_map")
    _item_type = object

    def __init__(self, model: "Model", name: str, mapping: dict):
        self._model = model
        self.name = name
        self._map = dict(mapping)
        expected = getattr(self, "_item_type", object)
        for item in self._map.values():
            if not isinstance(item, expected):
                raise TypeError(f"{type(self).__name__} expects values of type {expected.__name__}")
            if getattr(item, "_model", model) is not model:
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
                    clauses.extend(neq.clauses)
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
            clauses.extend(self._model._as_clausegroup(col.at_most_one()).clauses)
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
            * ``(idx.ub - idx.lb) <= len(vec)``
        """
        if isinstance(i, IntVar):
            _ensure_same_model(self, i)
            if i.lb < 0:
                raise ValueError("IntVector[IntVar] currently requires index.lb >= 0.")
            if (i.ub - i.lb) > len(self._items):
                raise ValueError(
                    f"IntVector length {len(self._items)} does not cover index domain [{i.lb}, {i.ub})."
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

    def _all_different_pairwise(self) -> ClauseGroup:
        clauses: list[Clause] = []
        for i in range(len(self._items)):
            for j in range(i + 1, len(self._items)):
                neq = self._items[i] != self._items[j]
                if isinstance(neq, ClauseGroup):
                    clauses.extend(neq.clauses)
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
        if (ub - lb) < len(self._items):
            raise ValueError("IntVector.bipartite all_different requires domain size >= vector length.")
        clauses: list[Clause] = []
        amo_groups: list[list[int]] = []
        for v in range(lb, ub):
            col_lits = [x == v for x in self._items]
            col = BoolVector(self._model, f"{self.name}.eq_col[{v}]", col_lits)
            clauses.extend(self._model._as_clausegroup(col.at_most_one()).clauses)
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
            clauses.extend(rel.clauses)
        return ClauseGroup(self._model, clauses)

    def lexicographic_less_than(self, other: "IntVector") -> ClauseGroup:
        """Return strict lexicographic ordering constraint ``self <lex other``."""
        if not isinstance(other, IntVector):
            raise TypeError("lexicographic_less_than expects IntVector")
        _ensure_same_model(self, other)
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
            clauses.extend(lt_cond.only_if(lt_i).clauses)          # lt_i -> xi<yi
            clauses.append(Clause(self._model, [~lt_i, prefix_eq[i]]))  # lt_i -> prefix

            # (prefix & xi<yi) -> lt_i  encoded by forbidding prefix=true and xi<yi with lt_i=false.
            # Reuse the exact "not(xi<yi)" clauses under ~lt_i to force lt_i when prefix is true.
            ge_cond = xi._relop_intvar(yi, ">=")
            if i == 0:
                clauses.extend(ge_cond.only_if(~lt_i).clauses)
            else:
                gate = self._model.bool(f"lex_gate[{self.name},{other.name},{i}]")
                # gate == prefix_eq[i] AND ~lt_i
                clauses.append(Clause(self._model, [~gate, prefix_eq[i]]))
                clauses.append(Clause(self._model, [~gate, ~lt_i]))
                clauses.append(Clause(self._model, [~prefix_eq[i], lt_i, gate]))
                clauses.extend(ge_cond.only_if(gate).clauses)

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
        _ensure_same_model(self, other)
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


IntMatrixView._matrix_view_type = IntMatrixView
BoolMatrixView._matrix_view_type = BoolMatrixView
EnumMatrixView._matrix_view_type = EnumMatrixView


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

    def val(self, obj):
        """Decode a model value for a supported object.

        Supported objects include literals, typed vars, vectors, matrices,
        matrix views, and typed dict containers.
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
        if isinstance(obj, _LazyIntExpr):
            obj = obj._realize()
        if isinstance(obj, IntVar):
            for value, lit in obj._eq_lits.items():
                if self.val(lit):
                    return value
            # Fallback: unary-prefix interpretation over threshold literals.
            count_true = sum(1 for lit in obj._threshold_lits if self.val(lit))
            value = obj.lb + count_true
            if value >= obj.ub:
                value = obj.ub - 1
            return value
        if isinstance(obj, IntVector):
            return [self.val(x) for x in obj]
        if isinstance(obj, BoolVector):
            return [self.val(x) for x in obj]
        if isinstance(obj, EnumVector):
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
        if isinstance(obj, list):
            return [self.val(x) for x in obj]
        if isinstance(obj, tuple):
            return tuple(self.val(x) for x in obj)
        if isinstance(obj, IntervalVar):
            return {
                "start": self.val(obj.start),
                "end": self.val(obj.end),
                "duration": obj.duration,
            }
        raise TypeError(f"Unsupported decode target: {type(obj)!r}")

    def __getitem__(self, obj):
        return self.val(obj)


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
        """Return ``True`` for feasible statuses (``sat`` or ``optimum``)."""
        return self.status in {"sat", "optimum"}

    def __getitem__(self, obj):
        return self.assignment[obj]


class SoftRef:
    """Reference handle returned by :meth:`Model.add_soft`."""

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

    @property
    def bound(self) -> bool:
        """Whether an incremental backend is currently bound."""
        return self.mode is not None

    def close(self) -> None:
        """Close and clear the currently bound incremental backend."""
        if self.sat_solver is not None:
            try:
                self.sat_solver.delete()
            except Exception:
                pass
        if self.ip_solver is not None and self.ip_created:
            try:
                self.ip_solver.close()
            except Exception:
                pass
        self.mode = None
        self.sat_solver = None
        self.sat_solver_name = None
        self.ip_solver = None
        self.ip_created = False
        self.solver_factory = None
        self.solver_kwargs = {}
        self.ip_next_vid = 0
        self.soft_lit_by_id.clear()

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
        lits = [m._lit_to_dimacs(l) for l in clause.literals]
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
        if m._debug_level >= m.DEBUG_DELTA:
            m._debug(
                m.DEBUG_DELTA,
                f"route_deltas mode={self.mode} hard+={max(0, len(m._hard)-hard_start)} soft+={max(0, len(m._soft)-soft_start)}",
            )
        if self.mode is None:
            return
        if self.mode == "sat":
            # SAT backend owns hard clauses only.
            if soft_start < len(m._soft):
                return
            assert self.sat_solver is not None
            for c in m._hard[hard_start:]:
                self.sat_solver.add_clause([m._lit_to_dimacs(l) for l in c.literals])
            return
        if self.mode == "maxsat":
            assert self.ip_solver is not None
            for c in m._hard[hard_start:]:
                self.ip_solver.add_clause([m._lit_to_dimacs(l) for l in c.literals])
            for i in range(soft_start, len(m._soft)):
                self._route_soft_index(i)

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
                    try:
                        ip_solver.close()
                    except Exception:
                        pass
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

        if self.mode == "sat":
            assert self.sat_solver is not None
            sat = self.sat_solver.solve(assumptions=assumptions_dimacs)
            if not sat:
                return SolveResult(m, status="unsat", raw_model=None, cost=None, backend=f"pysat.{self.sat_solver_name}")
            model = self.sat_solver.get_model() or []
            return SolveResult(m, status="sat", raw_model=model, cost=None, backend=f"pysat.{self.sat_solver_name}")

        assert self.mode == "maxsat"
        assert self.ip_solver is not None
        self.ip_solver.solve(
            assumptions=assumptions_dimacs,
            raise_on_abnormal=bool(raise_on_abnormal),
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
        raise ValueError(f"Unsupported comparator {op!r}")

    @staticmethod
    def _ceil_div(n: int, d: int) -> int:
        assert d > 0
        return -((-n) // d)

    @staticmethod
    def _int_cmp_constraint(x: IntVar, op: str, k: int) -> bool | Literal:
        if op == "==":
            if k < x.lb or k >= x.ub:
                return False
            return x == k
        if op == "<=":
            if k < x.lb:
                return False
            if k >= x.ub - 1:
                return True
            return x <= k
        if op == "<":
            if k <= x.lb:
                return False
            if k > x.ub - 1:
                return True
            return x < k
        if op == ">=":
            if k <= x.lb:
                return True
            if k >= x.ub:
                return False
            return x >= k
        if op == ">":
            if k < x.lb:
                return True
            if k >= x.ub - 1:
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
        # Compact ladder uses (ub-lb-1) threshold bits.
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
        width = int(getattr(net, "n", 0))
        if width <= 0:
            return None
        p2 = width // 2
        if 2 * p2 != width:
            return None

        # Network expects each half sorted ascending; IntVar ladders are descending.
        left_bits_asc: list[bool | Literal] = list(reversed(x._threshold_lits))
        right_bits_asc: list[bool | Literal] = list(reversed(y._threshold_lits))
        wires: list[bool | Literal] = [
            *([False] * (p2 - nx)),
            *left_bits_asc,
            *([False] * (p2 - ny)),
            *right_bits_asc,
        ]
        if len(wires) != width:
            return None

        clauses: list[Clause] = []
        for i, j in net:
            a = wires[i]
            b = wires[j]
            lo = _EncoderDispatch._lit_and(clauses, model, a, b)
            hi = _EncoderDispatch._lit_or(clauses, model, a, b)
            wires[i] = lo
            wires[j] = hi

        nsum = nx + ny
        # Channel boundary-inclusive cuts for exact equality with affine shift.
        # sum_ge(r) <-> z_count_ge(r - c_target), for r in [0, nsum+1]
        for r in range(0, nsum + 2):
            if r <= 0:
                sum_ge_r: bool | Literal = True
            elif r > nsum:
                sum_ge_r = False
            else:
                sum_ge_r = wires[width - r]

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
    def _try_boolsum_bigm_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile bool-sum Big-M forms without PB/Card encoders.

        Supported oriented forms:
            * ``sum(unit_bools) <= k + m*lit``
            * ``sum(unit_bools) >= k + m*lit``
        plus strict variants via bound shift.
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
                    cmp_op = ">="
                    rhs_const += 1
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
                if cmp_op == ">=":
                    _EncoderDispatch._emit_sum_ge_gated(clauses, model, True, lits, k, ge_cache)
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
                cmp_op = ">="
                rhs_const += 1

            # sum(lits) + sum_const OP rhs_const + mcoef * ind_lit
            # -> sum(lits) OP (rhs_const - sum_const) + mcoef * ind_lit
            k = rhs_const - sum_const

            bound_false = k + (mcoef if not ind_lit.polarity else 0)
            bound_true = k + (0 if not ind_lit.polarity else mcoef)

            clauses: list[Clause] = []
            ge_cache: list[bool | Literal] | None = None
            if cmp_op == "<=":
                ge_cache = _EncoderDispatch._emit_sum_le_gated(clauses, model, ~ind_lit, lits, bound_false, ge_cache)
                ge_cache = _EncoderDispatch._emit_sum_le_gated(clauses, model, ind_lit, lits, bound_true, ge_cache)
                return ClauseGroup(model, clauses)
            if cmp_op == ">=":
                ge_cache = _EncoderDispatch._emit_sum_ge_gated(clauses, model, ~ind_lit, lits, bound_false, ge_cache)
                ge_cache = _EncoderDispatch._emit_sum_ge_gated(clauses, model, ind_lit, lits, bound_true, ge_cache)
                return ClauseGroup(model, clauses)
            return None

        # Primary orientation: sum_expr OP affine_expr
        out = compile_oriented(lhs, op, rhs)
        if out is not None:
            return out

        # Swapped orientation:
        #   affine <= sum  <=> sum >= affine
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
        for k in range(x.lb, x.ub + 1):
            x_ge_k = _EncoderDispatch._int_cmp_constraint(x, ">=", k)
            if a > 0:
                cond = x_ge_k
                rhs_bound = bound - a * k
            else:
                cond = _EncoderDispatch._negate_bool_or_lit(x_ge_k)
                rhs_bound = bound - a * (k - 1)
            gate = _EncoderDispatch._lit_and(clauses, model, antecedent, cond)
            ge_cache = _EncoderDispatch._emit_sum_le_gated(
                clauses, model, gate, bool_lits, rhs_bound, ge_cache
            )
        return ge_cache

    @staticmethod
    def _try_mixed_int_boolsum_bigm_fastpath(
        model: "Model", lhs: PBExpr, op: str, rhs: PBExpr
    ) -> ClauseGroup | None:
        """Detect and compile ``a*x + sum(unit-bools) OP k + m*lit``.

        Supported comparators: ``<=, <, >=, >``.
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
            b_false = base + (mcoef if not lit.polarity else 0)
            b_true = base + (0 if not lit.polarity else mcoef)

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
                # LHS >= RHS  <=>  RHS <= LHS, then reuse oriented <= encoder.
                return None
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
    def _build_sequential_ge_counter(model: "Model", lits: Sequence[Literal]) -> tuple[list[Clause], list[bool | Literal]]:
        """Build ``count >= r`` literals for a sequence of booleans.

        Returns:
            ``(clauses, ge)`` where ``ge[r]`` encodes ``sum(lits) >= r`` for
            ``r in [0, len(lits)]`` and ``ge[0]`` is ``True``.
        """
        n = len(lits)
        clauses: list[Clause] = []
        if n == 0:
            return clauses, [True]

        # s[i][j] means: among first i literals, count >= j (1-indexed i,j).
        s: list[list[Literal | None]] = [[None] * (n + 1) for _ in range(n + 1)]

        for i in range(1, n + 1):
            li = lits[i - 1]
            for j in range(1, i + 1):
                sij = model.bool()
                s[i][j] = sij

                prev_j = s[i - 1][j] if j <= i - 1 else None
                prev_jm1 = s[i - 1][j - 1] if j > 1 else None

                # Forward:
                #   prev_j -> sij
                if prev_j is not None:
                    clauses.append(Clause(model, [~prev_j, sij]))

                #   li & prev_{j-1} -> sij
                if j == 1:
                    clauses.append(Clause(model, [~li, sij]))
                else:
                    assert prev_jm1 is not None
                    clauses.append(Clause(model, [~li, ~prev_jm1, sij]))

                # Backward:
                #   sij -> prev_j OR li
                if prev_j is None:
                    clauses.append(Clause(model, [~sij, li]))
                else:
                    clauses.append(Clause(model, [~sij, prev_j, li]))

                #   sij -> prev_j OR prev_{j-1}
                if j > 1:
                    if prev_j is None:
                        assert prev_jm1 is not None
                        clauses.append(Clause(model, [~sij, prev_jm1]))
                    else:
                        assert prev_jm1 is not None
                        clauses.append(Clause(model, [~sij, prev_j, prev_jm1]))
                elif j == 1:
                    # prev_{j-1} is the constant True, so this implication is tautological.
                    pass

        ge: list[bool | Literal] = [True]
        for r in range(1, n + 1):
            lit = s[n][r]
            if lit is None:
                ge.append(False)
            else:
                ge.append(lit)
        return clauses, ge

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

        Uses a sequential counter for ``sum>=r`` states and channels these with
        ladder thresholds. Avoids PB/Card encoders for this pattern.
        """
        if op not in ("==", "<=", ">=", "<", ">"):
            return None

        def try_orient(int_items: list[tuple[IntVar, int]], int_off: int, bool_expr: PBExpr) -> ClauseGroup | None:
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
            eff_op = op
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

            # Channel all threshold cuts including implicit boundaries:
            #   k = lb  (always true) and k = ub (always false).
            # This is required for exact equality when domains are shifted.
            for k in range(x.lb, x.ub + 1):
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
            out = try_orient(litems, loff, rhs)
            if out is not None:
                return out

        right = _EncoderDispatch._extract_multi_int_affine(model, rhs)
        if right is not None:
            ritems, roff = right
            out = try_orient(ritems, roff, lhs)
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
        if op == "!=":
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

            # Iterate all boundary cuts needed to reconstruct every exact value
            # via monotone implications. Boundary cuts constant-fold away.
            for k in range(xx.lb, xx.ub + 1):
                if k <= xx.lb:
                    x_ge_k: bool | Literal = True
                elif k >= xx.ub:
                    x_ge_k = False
                else:
                    x_ge_k = xx.__ge__(k)
                # Branch condition and conservative substitution on xx for the <= obligation.
                if aa > 0:
                    antecedent: bool | Literal = x_ge_k
                    V = c1 - aa * k
                else:
                    antecedent = _EncoderDispatch._negate_bool_or_lit(x_ge_k)
                    V = c1 - aa * (k - 1)

                # Solve b*y <= V into a y-comparator.
                if bb > 0:
                    limit = V // bb
                    consequent = _EncoderDispatch._int_cmp_constraint(yy, "<=", limit)
                else:
                    limit = -((-V) // bb)  # ceil(V / bb), works for negative bb too
                    consequent = _EncoderDispatch._int_cmp_constraint(yy, ">=", limit)

                _EncoderDispatch._lit_implies(clauses, model, antecedent, consequent)
        return ClauseGroup(model, clauses)

    @staticmethod
    def _try_trivariate_int_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile canonical ternary sum constraints without PB/Card.

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
        clauses: list[Clause] = []

        # For all i,j:
        #   (x >= i) & (y >= j) -> (z >= i + j - c_target)
        for i in range(x.lb, x.ub):
            xi = _EncoderDispatch._int_cmp_constraint(x, ">=", i)
            if xi is False:
                continue
            for j in range(y.lb, y.ub):
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
    def _try_univariate_int_fastpath(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup | None:
        """Detect and compile ``a*x OP c`` using a single ladder comparator literal.

        Introduces zero auxiliary variables. Unsupported comparators/shapes return ``None``.
        """
        if op == "!=":
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
        if op == "!=":
            return None
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
    def compile(model: "Model", lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup:
        """Compile a PB comparison with fast paths and PB/Card fallback."""
        lhs = lhs._realize_int_terms(model)
        rhs = rhs._realize_int_terms(model)
        unary_adder_eq_fast = _EncoderDispatch._try_unary_adder_eq_fastpath(model, lhs, op, rhs)
        if unary_adder_eq_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_unary_adder_eq op={op} clauses={len(unary_adder_eq_fast.clauses)}")
            return unary_adder_eq_fast
        boolsum_fast = _EncoderDispatch._try_int_equals_unit_bool_sum_fastpath(model, lhs, op, rhs)
        if boolsum_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_boolsum op={op} clauses={len(boolsum_fast.clauses)}")
            return boolsum_fast
        boolsum_bigm_fast = _EncoderDispatch._try_boolsum_bigm_fastpath(model, lhs, op, rhs)
        if boolsum_bigm_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_boolsum_bigm op={op} clauses={len(boolsum_bigm_fast.clauses)}")
            return boolsum_bigm_fast
        mixed_bigm_fast = _EncoderDispatch._try_mixed_int_boolsum_bigm_fastpath(model, lhs, op, rhs)
        if mixed_bigm_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_mixed_bigm op={op} clauses={len(mixed_bigm_fast.clauses)}")
            return mixed_bigm_fast
        uni_fast = _EncoderDispatch._try_univariate_int_fastpath(model, lhs, op, rhs)
        if uni_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_univariate op={op} clauses={len(uni_fast.clauses)}")
            return uni_fast
        uni_bool_fast = _EncoderDispatch._try_univariate_with_bool_fastpath(model, lhs, op, rhs)
        if uni_bool_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_univariate_bool op={op} clauses={len(uni_bool_fast.clauses)}")
            return uni_bool_fast
        tri_fast = _EncoderDispatch._try_trivariate_int_fastpath(model, lhs, op, rhs)
        if tri_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_trivariate op={op} clauses={len(tri_fast.clauses)}")
            return tri_fast
        bivar_fast = _EncoderDispatch._try_bivariate_int_fastpath(model, lhs, op, rhs)
        if bivar_fast is not None:
            model._debug(model.DEBUG_COMPILE, f"encode path=fast_bivariate op={op} clauses={len(bivar_fast.clauses)}")
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
            model._debug(model.DEBUG_COMPILE, f"encode path=card op={cmp_op} bound={bound} n={len(lits)}")
            if cmp_op == "<=":
                cnf = CardEnc.atmost(lits=lits, bound=bound, top_id=model._top_id())
            elif cmp_op == ">=":
                cnf = CardEnc.atleast(lits=lits, bound=bound, top_id=model._top_id())
            elif cmp_op == "==":
                cnf = CardEnc.equals(lits=lits, bound=bound, top_id=model._top_id())
            else:
                raise ValueError(f"Unsupported cardinality op {cmp_op!r}")
            return model._cnfplus_to_clausegroup(cnf)

        # General weighted PB path.
        model._debug(
            model.DEBUG_COMPILE,
            f"encode path=pb op={cmp_op} bound={bound} n={len(lits)} weights_sum={sum(weights)}",
        )
        if cmp_op == "<=":
            cnf = PBEnc.leq(lits=lits, weights=weights, bound=bound, top_id=model._top_id())
        elif cmp_op == ">=":
            cnf = PBEnc.geq(lits=lits, weights=weights, bound=bound, top_id=model._top_id())
        elif cmp_op == "==":
            cnf = PBEnc.equals(lits=lits, weights=weights, bound=bound, top_id=model._top_id())
        else:
            raise ValueError(f"Unsupported PB op {cmp_op!r}")
        return model._cnfplus_to_clausegroup(cnf)


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
        "_anon_counter",
        "_hard",
        "_soft",
        "_objective_constant",
        "_const_lits",
        "_pending_literal_defs",
        "_realized_literal_defs",
        "_realizing_literal_defs",
        "_soft_ids",
        "_soft_id_to_index",
        "_next_soft_id",
        "_soft_group_to_ids",
        "_soft_id_to_group",
        "_next_soft_group_id",
        "_soft_raw_weight_by_id",
        "_inc_state",
        "_obj_proxy",
        "_tier_obj_proxy",
        "_pb_clause_cache",
        "_known_amo_groups",
        "_known_eo_groups",
        "_pending_pb_constraints",
        "_auto_commit_pb",
        "_allow_negative_objective_offsets",
        "_soft_dedup_enabled",
        "_soft_gcd_opt_enabled",
        "_objective_precision_decimals",
        "_objective_precision_scale",
        "_debug_level",
        "_debug_stream",
    )

    # Global default policy (instance copies this value at construction).
    ALLOW_NEGATIVE_OBJECTIVE_OFFSETS = True
    SOFT_DEDUP_ENABLED = True
    SOFT_GCD_OPTIMIZATION_ENABLED = True
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
        self._anon_counter = 0
        self._hard: list[Clause] = []
        self._soft: list[tuple[int, Clause]] = []
        self._objective_constant = 0
        self._const_lits: dict[bool, Literal] = {}
        self._pending_literal_defs: dict[int, ClauseGroup] = {}
        self._realized_literal_defs: set[int] = set()
        self._realizing_literal_defs: set[int] = set()
        self._soft_ids: list[int] = []
        self._soft_id_to_index: dict[int, int] = {}
        self._next_soft_id = 1
        self._soft_group_to_ids: dict[int, list[int]] = {}
        self._soft_id_to_group: dict[int, int] = {}
        self._next_soft_group_id = 1
        self._soft_raw_weight_by_id: dict[int, float] = {}
        self._inc_state = _IncrementalCoordinator(self)
        self._obj_proxy = _ObjectiveProxy(self)
        self._tier_obj_proxy = _TierObjectiveProxy(self)
        self._pb_clause_cache: dict[tuple, ClauseGroup] = {}
        self._known_amo_groups: set[tuple[int, ...]] = set()
        self._known_eo_groups: set[tuple[int, ...]] = set()
        self._pending_pb_constraints: list[PBConstraint] = []
        self._auto_commit_pb = False
        self._allow_negative_objective_offsets = bool(self.ALLOW_NEGATIVE_OBJECTIVE_OFFSETS)
        self._soft_dedup_enabled = bool(self.SOFT_DEDUP_ENABLED)
        self._soft_gcd_opt_enabled = bool(self.SOFT_GCD_OPTIMIZATION_ENABLED)
        self._objective_precision_decimals: int | None = None
        self._objective_precision_scale: int = 1
        self._debug_level = 0
        self._debug_stream = None

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

    def _debug(self, level: int, message: str) -> None:
        if int(self._debug_level) < int(level):
            return
        out = self._debug_stream if self._debug_stream is not None else sys.stderr
        out.write(f"[hermax:model:L{int(level)}] {message}\n")
        try:
            out.flush()
        except Exception:
            pass

    def _clause_to_dimacs_list(self, clause: "Clause") -> list[int]:
        return [self._lit_to_dimacs(l) for l in clause.literals]

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

    def _reserve_container_name(self, name: str) -> None:
        if name in self._registry or name in self._container_names:
            raise ValueError(f"Identifier '{name}' is already registered in this model.")
        self._container_names.add(name)

    def _new_literal_pair(self, name: str) -> Literal:
        id_ = self._next_id
        self._next_id += 1
        pos = Literal(self, id_, name, True)
        neg = Literal(self, id_, name, False)
        pos._link_negation(neg)
        neg._link_negation(pos)
        self._lits_by_id[id_] = pos
        return pos

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
        self._hard.append(Clause(self, [lit if value else ~lit]))
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
        # Ensure contiguous id allocation remains monotonic.
        while self._next_id <= var_id:
            name = self._reserve_name(None)
            self._new_literal_pair(name)
        return self._lits_by_id[var_id]

    def _clause_from_dimacs(self, ints: Sequence[int]) -> Clause:
        lits = []
        for x in ints:
            if x == 0:
                continue
            base = self._get_or_make_aux_literal(abs(int(x)))
            lits.append(base if x > 0 else ~base)
        return Clause(self, lits)

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
        clauses = [self._clause_from_dimacs(cl) for cl in getattr(cnf, "clauses", [])]
        if self._debug_level >= self.DEBUG_VERBOSE:
            self._debug(self.DEBUG_VERBOSE, f"cnfplus->clauses count={len(clauses)}")
            for i, c in enumerate(clauses):
                self._debug(self.DEBUG_VERBOSE, f"  clause[{i}]={self._clause_to_dimacs_list(c)}")
        return ClauseGroup(self, clauses)

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
        self._pending_literal_defs[lit.id] = ClauseGroup(self, [*existing.clauses, *group.clauses])

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
            self._ensure_deferred_defs_in_group(group)
            self._hard.extend(group.clauses)
            self._realized_literal_defs.add(lit_id)
        finally:
            self._realizing_literal_defs.discard(lit_id)

    def _ensure_deferred_defs_in_group(self, group: ClauseGroup) -> None:
        for clause in group.clauses:
            for lit in clause.literals:
                self._ensure_literal_def_realized(lit)

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
        """Create a ladder-encoded bounded integer variable over domain ``[lb, ub)``."""
        self._reserve_container_name(name)
        return IntVar(self, name, lb=lb, ub=ub)

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
        out_ub = ((x.ub - 1) // divisor) + 1
        out_name = self._reserve_name(None) if name is None else name
        self._reserve_container_name(out_name)
        out = IntVar(self, out_name, lb=out_lb, ub=out_ub)

        for q_val in range(out.lb + 1, out.ub):
            q_lit = out.__ge__(q_val)
            x_lit = x.__ge__(q_val * divisor)
            group = self._equiv_literals_group(q_lit, x_lit)
            if group.clauses:
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
        out_ub = ((x.ub - 1) * factor) + 1
        out_name = self._reserve_name(None) if name is None else name
        self._reserve_container_name(out_name)
        out = IntVar(self, out_name, lb=out_lb, ub=out_ub)

        def ceil_div_pos(n: int, d: int) -> int:
            return -((-n) // d)

        for q_val in range(out.lb + 1, out.ub):
            q_lit = out.__ge__(q_val)
            x_cut = ceil_div_pos(q_val, factor)
            x_lit = x.__ge__(x_cut)
            group = self._equiv_literals_group(q_lit, x_lit)
            if group.clauses:
                self._register_literal_definition(q_lit, group)
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
        for k in range(z.lb + 1, z.ub):
            zk = z.__ge__(k)
            nonconst_srcs: list[Literal] = []
            saw_true = False
            saw_false = False
            for x in items:
                if k <= x.lb:
                    saw_true = True
                    continue
                if k >= x.ub:
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
        for k in range(z.lb + 1, z.ub):
            zk = z.__ge__(k)
            if kind == "upper_bound":
                for x in items:
                    if k <= x.lb:
                        m._hard.append(Clause(m, [zk]))
                        break
                    if k >= x.ub:
                        continue
                    m._hard.append(Clause(m, [~x.__ge__(k), zk]))
            else:
                active = False
                forced_false = False
                for x in items:
                    if k >= x.ub:
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
        raise TypeError("Model.vector() requires homogeneous items of type Literal, IntVar, or EnumVar.")

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
        clause: Clause,
        group_id: Optional[int] = None,
        *,
        raw_weight: Optional[float] = None,
    ) -> int:
        idx = len(self._soft)
        self._soft.append((int(weight), clause))
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
        if isinstance(constraint, PBConstraint):
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
            self._hard.extend(group.clauses)
            if self._debug_level >= self.DEBUG_DELTA:
                self._debug(self.DEBUG_DELTA, f"add_hard count={len(group.clauses)}")
                if self._debug_level >= self.DEBUG_VERBOSE:
                    for i, c in enumerate(group.clauses):
                        self._debug(self.DEBUG_VERBOSE, f"  hard[{i}]={self._clause_to_dimacs_list(c)}")
            self._inc_state.route_deltas(hard0, soft0)
            return self
        group = self._as_clausegroup(constraint)
        self._ensure_deferred_defs_in_group(group)
        self._register_clausegroup_structure(group)
        self._hard.extend(group.clauses)
        if self._debug_level >= self.DEBUG_DELTA:
            self._debug(self.DEBUG_DELTA, f"add_hard count={len(group.clauses)}")
            if self._debug_level >= self.DEBUG_VERBOSE:
                for i, c in enumerate(group.clauses):
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

        def _soft_clause_signature(clause: Clause) -> tuple[int, ...]:
            # Canonical disjunction signature; duplicate literals are collapsed.
            return tuple(sorted(set(self._lit_to_dimacs(l) for l in clause.literals)))

        def _find_soft_sid_for_clause(clause: Clause) -> int | None:
            sig = _soft_clause_signature(clause)
            for i, (_w, c) in enumerate(self._soft):
                if _soft_clause_signature(c) == sig:
                    return int(self._soft_ids[i])
            return None

        def _append_or_merge_soft(
            weight_i: int,
            clause_i: Clause,
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
                sid = _append_or_merge_soft(weight, Clause(self, [~t]), group_id, raw_weight)
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
                sid = _append_or_merge_soft(soft_w, Clause(self, [lit]), group_id, rw)
                sids.append(sid)
            return group_id, _done()

        def _add_soft_group_targeted(group: ClauseGroup) -> None:
            if not group.clauses:
                return
            if len(group.clauses) == 1:
                self._ensure_deferred_defs_in_group(group)
                sid = _append_or_merge_soft(weight, group.clauses[0], group_id, raw_weight)
                sids.append(sid)
                return
            # One weighted penalty + gated hard network (targeted relaxation).
            r = self.bool()  # hidden relaxation literal (anonymous)
            sid = _append_or_merge_soft(weight, Clause(self, [~r]), group_id, raw_weight)
            sids.append(sid)
            gated = group.only_if(~r)
            self._ensure_deferred_defs_in_group(gated)
            self._hard.extend(gated.clauses)

        # Targeted relaxation for multi-clause structures (including PBConstraint):
        # add one weighted penalty literal and gate the internal network hard.
        if isinstance(constraint, PBConstraint):
            prepared = self._prepare_pb_constraint(constraint)
            if isinstance(prepared, ClauseGroup):
                _add_soft_group_targeted(prepared)
                return group_id, _done()
            r = self.bool()  # hidden relaxation literal (anonymous)
            sid = _append_or_merge_soft(weight, Clause(self, [~r]), group_id, raw_weight)
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
        for c in group.clauses:
            sid = _append_or_merge_soft(weight, c, group_id, raw_weight)
            sids.append(sid)
        return group_id, _done()

    def add_soft(self, constraint, weight: int):
        """Add a soft constraint and return a grouped handle.

        Notes:
            ``add_soft`` cannot be used while ``model.tier_obj`` is active.
            If objective precision is disabled, ``weight`` must be a positive
            integer.
        """
        self._ensure_no_tier_objective_active()
        scaled_w, raw_w = self._coerce_soft_weight(weight, allow_zero=False)
        gid, sids = self._add_soft(int(scaled_w), constraint, dedup=bool(self._soft_dedup_enabled), raw_weight=float(raw_w))
        return SoftRef(gid, sids)

    def update_soft_weight(self, target, new_weight: int) -> None:
        """Update soft weight(s) by `SoftRef`, soft-group id, soft id, or list of soft ids.

        Notes:
            This API updates existing soft terms and requires a positive weight.
            Use objective replacement/clear APIs when you need full objective
            diffs.
        """
        scaled_w, raw_w = self._coerce_soft_weight(new_weight, allow_zero=False)
        ids: list[int]
        if isinstance(target, SoftRef):
            ids = list(target.soft_ids)
        elif isinstance(target, int):
            t = int(target)
            if t in self._soft_id_to_index:
                ids = [t]
            else:
                raise KeyError(f"Unknown soft target {target!r}")
        elif isinstance(target, Sequence) and not isinstance(target, (str, bytes)):
            ids = [int(x) for x in target]
        else:
            raise TypeError("target must be SoftRef, soft-group id, soft id, or sequence of soft ids.")
        if not ids:
            return
        for sid in ids:
            self._soft_raw_weight_by_id[int(sid)] = float(raw_w)
            self._set_soft_weight_internal(int(sid), int(scaled_w), allow_zero=False, allow_when_sat=False)

    def _compile_pb_compare(self, lhs: PBExpr, op: str, rhs: PBExpr) -> ClauseGroup:
        _ensure_same_model(self, lhs, rhs)
        lhs_r = lhs._realize_int_terms(self)
        rhs_r = rhs._realize_int_terms(self)
        self._validate_integral_pbexpr(lhs_r)
        self._validate_integral_pbexpr(rhs_r)
        pairs, const = _EncoderDispatch._normalize_pb(lhs_r, rhs_r)
        cmp_op, bound = _EncoderDispatch._bound_from_zero_compare(op, const)
        if self._debug_level >= self.DEBUG_COMPILE:
            terms = ", ".join(f"{int(w)}*{int(self._lit_to_dimacs(l))}" for w, l in pairs)
            self._debug(
                self.DEBUG_COMPILE,
                f"pb_normalize raw_op={op} -> op={cmp_op} bound={int(bound)} terms=[{terms}]",
            )
        key_pairs = tuple(sorted((int(self._lit_to_dimacs(l)), int(w)) for w, l in pairs))
        key = (cmp_op, int(bound), key_pairs)
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
        self._pending_pb_constraints.append(constraint)

    def _register_amo_group(self, lits: Sequence[int], *, exactly_one: bool = False) -> None:
        group = tuple(sorted({int(lit) for lit in lits}))
        if len(group) <= 1:
            return
        if bool(exactly_one):
            self._known_amo_groups.discard(group)
            self._known_eo_groups.add(group)
        else:
            if group in self._known_eo_groups:
                return
            self._known_amo_groups.add(group)

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
            group = [int(self._lit_to_dimacs(iv == value)) for value in range(int(iv.lb), int(iv.ub))]
            self._register_amo_group(group, exactly_one=True)
            added_groups.append(group)
        return added_groups

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

        eager_fast = (
            _EncoderDispatch._try_unary_adder_eq_fastpath(self, lhs_r, constraint._op, rhs_r)
            or _EncoderDispatch._try_int_equals_unit_bool_sum_fastpath(self, lhs_r, constraint._op, rhs_r)
            or _EncoderDispatch._try_boolsum_bigm_fastpath(self, lhs_r, constraint._op, rhs_r)
            or _EncoderDispatch._try_mixed_int_boolsum_bigm_fastpath(self, lhs_r, constraint._op, rhs_r)
            or _EncoderDispatch._try_univariate_int_fastpath(self, lhs_r, constraint._op, rhs_r)
            or _EncoderDispatch._try_univariate_with_bool_fastpath(self, lhs_r, constraint._op, rhs_r)
            or _EncoderDispatch._try_trivariate_int_fastpath(self, lhs_r, constraint._op, rhs_r)
            or _EncoderDispatch._try_bivariate_int_fastpath(self, lhs_r, constraint._op, rhs_r)
        )
        if eager_fast is not None:
            group = eager_fast
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
        hard0 = len(self._hard)
        soft0 = len(self._soft)
        pending, self._pending_pb_constraints = self._pending_pb_constraints, []
        analyzed = [(idx, self._analyze_deferred_pb_constraint(constraint)) for idx, constraint in enumerate(pending)]

        amo_candidates: list[list[int]] = [list(group) for group in sorted(self._known_amo_groups)]
        eo_candidates: list[list[int]] = [list(group) for group in sorted(self._known_eo_groups)]

        def _cache_key(item: dict[str, object]) -> tuple:
            key_pairs = tuple(
                sorted(
                    (int(self._lit_to_dimacs(lit)), int(weight))
                    for lit, weight in zip(item["lits"], item["weights"])
                )
            )
            return (str(item["cmp_op"]), int(item["bound"]), key_pairs)

        def _cached_group_for(item: dict[str, object], build):
            key = _cache_key(item)
            cached = self._pb_clause_cache.get(key)
            if cached is not None:
                if self._debug_level >= self.DEBUG_COMPILE:
                    self._debug(self.DEBUG_COMPILE, "pb_cache hit")
                return cached
            if self._debug_level >= self.DEBUG_COMPILE:
                self._debug(self.DEBUG_COMPILE, "pb_cache miss")
            group = build()
            self._pb_clause_cache[key] = group
            return group

        def _candidate_sort_key(entry: tuple[int, dict[str, object]]) -> tuple[int, int]:
            # First AMO/EO candidates, then other cardinalities, then weighted PB.
            idx, item = entry
            cmp_op = str(item["cmp_op"])
            bound = int(item["bound"])
            all_unit = bool(item["all_unit"])
            is_amo_eo = all_unit and bound == 1 and cmp_op in {"<=", "=="}
            if is_amo_eo:
                priority = 0
            elif all_unit:
                priority = 1
            else:
                priority = 2
            return (priority, idx)

        def _structured_overlap_for(pb_lit_ids: list[int]) -> tuple[list[list[int]], list[list[int]]]:
            pb_lit_set = set(pb_lit_ids)
            pb_amo_groups: list[list[int]] = []
            pb_eo_groups: list[list[int]] = []
            for group in amo_candidates:
                overlap = [lit for lit in group if lit in pb_lit_set]
                if len(overlap) > 1:
                    pb_amo_groups.append(overlap)
            for group in eo_candidates:
                overlap = [lit for lit in group if lit in pb_lit_set]
                if len(overlap) == len(group) and len(overlap) > 1:
                    pb_eo_groups.append(overlap)
                elif len(overlap) > 1:
                    pb_amo_groups.append(overlap)
            return pb_amo_groups, pb_eo_groups

        def _structured_unit_auto_group(pb_lit_ids: list[int], pb_bound: int) -> ClauseGroup:
            pb_amo_groups, pb_eo_groups = _structured_overlap_for(pb_lit_ids)
            return self._cnfplus_to_clausegroup(
                StructuredPBEnc.auto_leq(
                    lits=pb_lit_ids,
                    weights=[1] * len(pb_lit_ids),
                    bound=int(pb_bound),
                    amo_groups=pb_amo_groups,
                    eo_groups=pb_eo_groups,
                    top_id=self._top_id(),
                )
            )

        for _idx, item in sorted(analyzed, key=_candidate_sort_key):
            constraint = item["constraint"]
            lits = [lit for lit in item["lits"]]
            cmp_op = str(item["cmp_op"])
            bound = int(item["bound"])
            weights = [int(w) for w in item["weights"]]
            all_unit = bool(item["all_unit"])

            for group in self._register_small_int_eq_family_from_lits(lits):
                if group in eo_candidates:
                    continue
                amo_candidates = [existing for existing in amo_candidates if existing != group]
                eo_candidates.append(group)

            if all_unit:
                raw_group = [self._lit_to_dimacs(lit) for lit in lits]
                pb_lit_ids = [self._lit_to_dimacs(lit) for lit in lits]
                if self._debug_level >= self.DEBUG_COMPILE:
                    self._debug(
                        self.DEBUG_COMPILE,
                        f"encode path=structured_card_auto op={cmp_op} bound={bound} n={len(pb_lit_ids)}",
                    )

                def _build_unit_group():
                    if cmp_op == "<=":
                        return _structured_unit_auto_group(pb_lit_ids, bound)
                    if cmp_op == ">=":
                        return _structured_unit_auto_group([-lit for lit in pb_lit_ids], len(pb_lit_ids) - bound)
                    if cmp_op == "==":
                        upper = _structured_unit_auto_group(pb_lit_ids, bound)
                        lower = _structured_unit_auto_group([-lit for lit in pb_lit_ids], len(pb_lit_ids) - bound)
                        return upper & lower
                    return constraint.clauses()

                group = _cached_group_for(item, _build_unit_group)

                for cond in constraint._conditions:
                    group = group.only_if(cond)
                self._ensure_deferred_defs_in_group(group)
                self._hard.extend(group.clauses)
                if cmp_op == "<=" and bound == 1:
                    self._register_amo_group(raw_group, exactly_one=False)
                    amo_candidates.append(raw_group)
                elif cmp_op == "==" and bound == 1:
                    self._register_amo_group(raw_group, exactly_one=True)
                    amo_candidates = [group for group in amo_candidates if group != raw_group]
                    eo_candidates.append(raw_group)
                continue

            if cmp_op == "<=":
                pb_lit_ids = [self._lit_to_dimacs(lit) for lit in lits]
                pb_amo_groups, pb_eo_groups = _structured_overlap_for(pb_lit_ids)
                if pb_amo_groups or pb_eo_groups:
                    if self._debug_level >= self.DEBUG_COMPILE:
                        self._debug(
                            self.DEBUG_COMPILE,
                            f"encode path=structured_pb_auto op={cmp_op} bound={bound} n={len(pb_lit_ids)}",
                        )
                    group = _cached_group_for(
                        item,
                        lambda: self._cnfplus_to_clausegroup(
                            StructuredPBEnc.auto_leq(
                                lits=pb_lit_ids,
                                weights=weights,
                                bound=bound,
                                amo_groups=pb_amo_groups,
                                eo_groups=pb_eo_groups,
                                top_id=self._top_id(),
                            )
                        ),
                    )
                    for cond in constraint._conditions:
                        group = group.only_if(cond)
                    self._ensure_deferred_defs_in_group(group)
                    self._hard.extend(group.clauses)
                    continue

            group = constraint.clauses()
            self._ensure_deferred_defs_in_group(group)
            self._hard.extend(group.clauses)
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
        self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard))
        cnf = CNF()
        for clause in self._hard:
            cnf.append([self._lit_to_dimacs(l) for l in clause.literals])
        return cnf

    def to_wcnf(self) -> WCNF:
        """Export hard and soft constraints to a PySAT :class:`~pysat.formula.WCNF`."""
        self._commit_pb()
        self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard))
        self._ensure_deferred_defs_in_group(ClauseGroup(self, [c for _, c in self._soft]))
        wcnf = WCNF()
        for clause in self._hard:
            wcnf.append([self._lit_to_dimacs(l) for l in clause.literals])
        for weight, clause in self._soft:
            if int(weight) <= 0:
                continue
            wcnf.append([self._lit_to_dimacs(l) for l in clause.literals], weight=weight)
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
        self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard))
        self._ensure_deferred_defs_in_group(ClauseGroup(self, [c for _, c in self._soft]))
        g = int(self._soft_weight_gcd())
        wcnf = WCNF()
        for clause in self._hard:
            wcnf.append([self._lit_to_dimacs(l) for l in clause.literals])
        for weight, clause in self._soft:
            if int(weight) <= 0:
                continue
            ww = int(weight) // g if g > 1 else int(weight)
            wcnf.append([self._lit_to_dimacs(l) for l in clause.literals], weight=int(ww))
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
            self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard))
            soft_group = self._tier_entry_to_clausegroup_units(lit_weights)
            self._ensure_deferred_defs_in_group(soft_group)

            formula = WCNF()
            for c in self._hard:
                formula.append([self._lit_to_dimacs(l) for l in c.literals])
            for a in assumptions_dimacs:
                v = abs(int(a))
                if v > 0:
                    formula.append([int(v), -int(v)])
            for g in hardening:
                for c in g.clauses:
                    formula.append([self._lit_to_dimacs(l) for l in c.literals])
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

        self._ensure_deferred_defs_in_group(ClauseGroup(self, self._hard))
        soft_group = self._tier_entry_to_clausegroup_units(flat_lit_weights)
        self._ensure_deferred_defs_in_group(soft_group)

        formula = WCNF()
        for c in self._hard:
            formula.append([self._lit_to_dimacs(l) for l in c.literals])
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
        self._assert_lex_exclusive_usage()
        ls = None if lex_strategy is None else str(lex_strategy).lower()
        if ls is not None and ls not in {"incremental", "stratified"}:
            raise ValueError("lex_strategy must be one of: incremental, stratified")

        if self._tier_obj_proxy.is_active():
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
        # Preserve one-shot convenience MaxSAT (PySAT RC2) when no incremental
        # MaxSAT backend is explicitly provided and no backend is bound yet.
        if (
            use_incremental
            and self._inc_state.mode is None
            and self._soft
            and solver is None
            and (backend or "auto").lower() == "auto"
        ):
            use_incremental = False
        # Preserve one-shot explicit solver path for backend='auto' when caller
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
            )

        if solver is not None:
            return self._solve_with_hermax_solver(
                solver=solver,
                solver_kwargs=solver_kwargs or {},
                assumptions=assumptions,
                raise_on_abnormal=raise_on_abnormal,
            )

        if self._soft:
            if maxsat_backend.lower() != "rc2":
                raise ValueError("Unsupported maxsat backend for Model.solve().")

            return self._solve_with_hermax_solver(
                solver=HermaxRC2,
                solver_kwargs={},
                assumptions=assumptions,
                raise_on_abnormal=raise_on_abnormal,
            )

        cnf = self.to_cnf()
        with PySATSolver(name=sat_solver_name) as s:
            s.append_formula(cnf.clauses)
            sat = s.solve(assumptions=self._coerce_assumptions(assumptions))
            if not sat:
                return SolveResult(self, status="unsat", raw_model=None, cost=None, backend=f"pysat.{sat_solver_name}")
            model = s.get_model() or []
            return SolveResult(self, status="sat", raw_model=model, cost=None, backend=f"pysat.{sat_solver_name}")

    def _solve_with_hermax_solver(
        self,
        *,
        solver,
        solver_kwargs: dict,
        assumptions: Optional[Sequence[object]],
        raise_on_abnormal: bool,
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

            # Best-effort preallocation for wrappers that require explicit variable creation.
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
            if solver_kwargs:
                raise ValueError("solver_kwargs are only supported when passing a solver class/callable.")
            ip_solver = solver
            _replay_into_existing_instance(ip_solver, formula)
        else:
            if not callable(solver):
                raise TypeError("solver must be an IPAMIRSolver instance, class, or callable factory.")
            ip_solver = solver(formula=formula, **solver_kwargs)
            created = True
            if not isinstance(ip_solver, IPAMIRSolver):
                try:
                    if created and hasattr(ip_solver, "close"):
                        ip_solver.close()
                except Exception:
                    pass
                raise TypeError("solver callable must return an IPAMIRSolver instance.")

        try:
            ip_solver.solve(
                assumptions=self._coerce_assumptions(assumptions),
                raise_on_abnormal=bool(raise_on_abnormal),
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
                try:
                    ip_solver.close()
                except Exception:
                    pass


__all__ = [
    "Model",
    "Literal",
    "Clause",
    "ClauseGroup",
    "Term",
    "PBExpr",
    "PBConstraint",
    "DivExpr",
    "ScaleExpr",
    "MaxExpr",
    "IntervalVar",
    "BoolVector",
    "EnumVector",
    "IntVector",
    "BoolDict",
    "EnumDict",
    "IntDict",
    "BoolMatrix",
    "EnumMatrix",
    "IntMatrix",
    "AssignmentView",
    "SolveResult",
]
