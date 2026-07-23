from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence
from hermax.utils import batcher_odd_even_unary_add_network

from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from .expressions import *
    from .variables import *
    from .encoders import *
    from .core import *

FLOAT_ZERO_TOL = 1e-12


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
        try:
            m = obj._model
        except AttributeError:
            continue
        if m is None:
            continue
        if model is None:
            model = m
        elif m is not model:
            raise ValueError("Variables belong to different models.")
    return model


def _ensure_same_model_pair_fast(a, b) -> "Model":
    """Fast model identity check for hot binary internal call sites.

    This helper assumes both operands are model-bound objects exposing ``._model``.
    Use ``_ensure_same_model(...)`` when inputs may be optional/heterogeneous.
    """
    ma = a._model
    mb = b._model
    if ma is not mb:
        raise ValueError("Variables belong to different models.")
    return ma


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
        terms: list[Term] = []
        constant = 0
        int_terms: list[tuple[int, IntVar | _LazyIntExpr]] = []
    else:
        numeric_total = 0
        start_expr = PBExpr.from_item(start)
        terms = list(start_expr.terms)
        constant = start_expr.constant
        int_terms = list(start_expr.int_terms)

    for item in iterable:
        item_model = _item_model(item)
        if model is None and item_model is None:
            numeric_total = numeric_total + item
            continue

        item_expr = PBExpr.from_item(item)
        if model is None:
            model = item_model
            if model is None:
                raise TypeError(f"Unsupported item for sum_expr(): {type(item)!r}")
            constant = numeric_total
            numeric_total = 0
        else:
            if item_model is not None and item_model is not model:
                raise ValueError("Variables belong to different models.")

        if item_expr.terms:
            terms.extend(item_expr.terms)
        constant = constant + item_expr.constant
        if item_expr.int_terms:
            int_terms.extend((int(c), v) for c, v in item_expr.int_terms if int(c) != 0)

    if model is None:
        return numeric_total
    return PBExpr._from_terms_trusted(
        model,
        PBExpr._collapse_terms(terms),
        constant,
        int_terms=int_terms,
        collapsed=True,
    )


class ClauseGroup:
    """Immutable collection of CNF clauses stored in DIMACS form."""

    __slots__ = ("_model", "_clauses", "_amo_groups", "_eo_groups")

    def __init__(
        self,
        model: "Model",
        clauses: Sequence["Clause | Sequence[int]"] | None = None,
        *,
        amo_groups: Sequence[Sequence[int]] | None = None,
        eo_groups: Sequence[Sequence[int]] | None = None,
        reserve_aux_ids: bool = True,
    ):
        self._model = model
        norm: list[tuple[int, ...]] = []
        for clause in clauses or ():
            if isinstance(clause, Clause):
                _ensure_same_model_pair_fast(self, clause)
                norm.append(tuple(int(x) for x in clause.dimacs))
            else:
                dims = tuple(int(x) for x in clause if int(x) != 0)
                if reserve_aux_ids and len(dims) > 0:
                    self._model._reserve_literal_ids_up_to(max(abs(x) for x in dims))
                norm.append(dims)
        self._clauses = tuple(norm)
        self._amo_groups = [list(group) for group in (amo_groups or [])]
        self._eo_groups = [list(group) for group in (eo_groups or [])]

    @classmethod
    def _from_dimacs_trusted(
        cls,
        model: "Model",
        clauses: Sequence[Sequence[int]],
        *,
        amo_groups: Sequence[Sequence[int]] | None = None,
        eo_groups: Sequence[Sequence[int]] | None = None,
    ) -> "ClauseGroup":
        """Construct directly from validated DIMACS tuples.

        Caller must ensure each clause is a tuple of non-zero ints and that
        model variable ids are already reserved.
        """
        group = cls.__new__(cls)
        group._model = model
        if isinstance(clauses, tuple) and all(isinstance(clause, tuple) for clause in clauses):
            group._clauses = clauses
        else:
            group._clauses = tuple(tuple(int(x) for x in clause) for clause in clauses)
        group._amo_groups = [] if amo_groups is None else amo_groups
        group._eo_groups = [] if eo_groups is None else eo_groups
        return group

    def _ensure_mutable_clauses(self) -> list[tuple[int, ...]]:
        if isinstance(self._clauses, list):
            return self._clauses
        mutable = list(self._clauses)
        self._clauses = mutable
        return mutable

    @staticmethod
    def _copy_groups(groups: Sequence[Sequence[int]]) -> list[list[int]]:
        return [list(group) for group in groups]

    def __len__(self) -> int:
        return len(self._clauses)

    def __iter__(self):
        return iter(self._clauses)

    def is_empty(self) -> bool:
        return len(self._clauses) == 0

    def single_clause_or_none(self) -> "tuple[int, ...] | None":
        return self._clauses[0] if len(self._clauses) == 1 else None

    def iter_dimacs(self):
        return iter(self._clauses)

    def materialize_semantic(self) -> tuple["Clause", ...]:
        return tuple(Clause.from_dimacs(self._model, clause) for clause in self._clauses)

    def _combined_groups(self, other) -> tuple[list[list[int]], list[list[int]]]:
        amo_groups = self._copy_groups(self._amo_groups)
        eo_groups = self._copy_groups(self._eo_groups)
        if isinstance(other, ClauseGroup):
            amo_groups.extend(self._copy_groups(other._amo_groups))
            eo_groups.extend(self._copy_groups(other._eo_groups))
        return amo_groups, eo_groups

    def only_if(self, condition: "Literal") -> "ClauseGroup":
        """Return a new clause group gated by one literal."""
        if not isinstance(condition, Literal):
            raise _detection_error()
        _ensure_same_model_pair_fast(self, condition)
        gate = -self._model._lit_to_dimacs(condition)
        return ClauseGroup._from_dimacs_trusted(self._model, tuple((*clause, gate) for clause in self._clauses))

    def implies(self, target):
        """Reject ClauseGroup-as-condition usage in this modeling API."""
        raise _detection_error()

    def __and__(self, other):
        if isinstance(other, Literal):
            _ensure_same_model_pair_fast(self, other)
            return ClauseGroup._from_dimacs_trusted(
                self._model,
                (*self._clauses, (self._model._lit_to_dimacs(other),)),
                amo_groups=self._copy_groups(self._amo_groups),
                eo_groups=self._copy_groups(self._eo_groups),
            )
        if isinstance(other, Clause):
            _ensure_same_model_pair_fast(self, other)
            return ClauseGroup._from_dimacs_trusted(
                self._model,
                (*self._clauses, other.dimacs),
                amo_groups=self._copy_groups(self._amo_groups),
                eo_groups=self._copy_groups(self._eo_groups),
            )
        if isinstance(other, ClauseGroup):
            _ensure_same_model_pair_fast(self, other)
            amo_groups, eo_groups = self._combined_groups(other)
            return ClauseGroup._from_dimacs_trusted(
                self._model,
                (*self._clauses, *other._clauses),
                amo_groups=amo_groups,
                eo_groups=eo_groups,
            )
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
            ``group &= x`` with rebinding) for immutable operator behavior.
        """
        if not inplace:
            raise TypeError("ClauseGroup.extend() requires keyword argument inplace=True to mutate.")
        if isinstance(other, Literal):
            _ensure_same_model_pair_fast(self, other)
            self._ensure_mutable_clauses().append((self._model._lit_to_dimacs(other),))
            return self
        if isinstance(other, Clause):
            _ensure_same_model_pair_fast(self, other)
            self._ensure_mutable_clauses().append(other.dimacs)
            return self
        if isinstance(other, ClauseGroup):
            _ensure_same_model_pair_fast(self, other)
            self._ensure_mutable_clauses().extend(other._clauses)
            self._amo_groups.extend(other._amo_groups)
            self._eo_groups.extend(other._eo_groups)
            return self
        raise TypeError("ClauseGroup.extend() only supports Literal, Clause, or ClauseGroup operands.")

    def __repr__(self) -> str:
        return f"ClauseGroup(n={len(self._clauses)})"


class DeferredClauseGroup(ClauseGroup):
    """Clause-group shaped wrapper that compiles only when consumed.

    This preserves the builder-side API boundary: constructing a derived
    constraint should not allocate helper variables or clauses until the user
    actually commits it to the model (for example via ``model &= ...``).
    """

    __slots__ = ("_builder", "_compiled")

    def __init__(self, model: "Model", builder):
        self._model = model
        self._clauses = ()
        self._amo_groups = []
        self._eo_groups = []
        self._builder = builder
        self._compiled: ClauseGroup | None = None

    def _realize(self) -> ClauseGroup:
        if self._compiled is None:
            group = self._builder()
            if not isinstance(group, ClauseGroup):
                raise TypeError("DeferredClauseGroup builder must return ClauseGroup.")
            self._compiled = group
            self._clauses = group._clauses
            self._amo_groups = self._copy_groups(group._amo_groups)
            self._eo_groups = self._copy_groups(group._eo_groups)
        return self._compiled

    def __len__(self) -> int:
        return len(self._realize())

    def __iter__(self):
        return iter(self._realize())

    def is_empty(self) -> bool:
        return self._realize().is_empty()

    def single_clause_or_none(self) -> "tuple[int, ...] | None":
        return self._realize().single_clause_or_none()

    def iter_dimacs(self):
        return self._realize().iter_dimacs()

    def materialize_semantic(self) -> tuple["Clause", ...]:
        return self._realize().materialize_semantic()

    def only_if(self, condition: "Literal") -> "ClauseGroup":
        if not isinstance(condition, Literal):
            raise _detection_error()
        _ensure_same_model_pair_fast(self, condition)
        return DeferredClauseGroup(self._model, lambda: self._realize().only_if(condition))

    def implies(self, target):
        raise _detection_error()

    def __and__(self, other):
        if isinstance(other, (Literal, Clause, ClauseGroup, DeferredClauseGroup)):
            _ensure_same_model_pair_fast(self, other)
            if isinstance(other, DeferredClauseGroup):
                return DeferredClauseGroup(self._model, lambda: self._realize() & other._realize())
            return DeferredClauseGroup(self._model, lambda: self._realize() & other)
        return NotImplemented

    def __iand__(self, other):
        return self.__and__(other)

    def __repr__(self) -> str:
        if self._compiled is None:
            return "DeferredClauseGroup(<pending>)"
        return repr(self._compiled)


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
        _ensure_same_model_pair_fast(self, indicator)
        fwd = self.only_if(indicator)
        rev = self._negated().only_if(~indicator)
        return ClauseGroup(self._model, [*fwd, *rev])


class Clause:
    """Single CNF clause (disjunction of literals)."""
    __slots__ = ("_model", "_dimacs", "_literals_cache")

    def __init__(self, model: "Model", literals: Sequence["Literal"]):
        self._model = model
        dims: list[int] = []
        for lit in literals:
            if not isinstance(lit, Literal):
                raise TypeError("Clause expects Literal operands.")
            _ensure_same_model_pair_fast(self, lit)
            dims.append(model._lit_to_dimacs(lit))
        self._dimacs = tuple(int(x) for x in dims)
        self._literals_cache = list(literals)

    @classmethod
    def from_dimacs(cls, model: "Model", ints: Sequence[int]) -> "Clause":
        dimacs = tuple(int(x) for x in ints if int(x) != 0)
        max_var = 0
        for x in dimacs:
            max_var = max(max_var, abs(x))
        model._reserve_literal_ids_up_to(max_var)
        return cls._from_dimacs_trusted(model, dimacs)

    @classmethod
    def _from_dimacs_trusted(
        cls,
        model: "Model",
        dimacs: tuple[int, ...],
        *,
        literals_cache: list["Literal"] | None = None,
    ) -> "Clause":
        clause = cls.__new__(cls)
        clause._model = model
        clause._dimacs = dimacs if isinstance(dimacs, tuple) else tuple(int(x) for x in dimacs)
        clause._literals_cache = literals_cache
        return clause

    def _ensure_mutable_dimacs(self) -> list[int]:
        if isinstance(self._dimacs, list):
            return self._dimacs
        mutable = list(self._dimacs)
        self._dimacs = mutable
        return mutable

    @property
    def literals(self) -> list["Literal"]:
        cache = self._literals_cache
        if cache is None:
            cache = [self._model._dimacs_to_lit(int(x)) for x in self._dimacs]
            self._literals_cache = cache
        return cache

    @property
    def dimacs(self) -> tuple[int, ...]:
        if isinstance(self._dimacs, tuple):
            return self._dimacs
        return tuple(self._dimacs)

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
            _ensure_same_model_pair_fast(self, other)
            return Clause._from_dimacs_trusted(self._model, (*self._dimacs, self._model._lit_to_dimacs(other)))
        raise TypeError("Clause OR only supports Literal operands.")

    def __ior__(self, other):
        # Immutable-by-operator contract: `x |= y` returns a new Clause.
        return self.__or__(other)

    def append(self, literal: "Literal", *, inplace: bool = False) -> "Clause":
        """Append a literal to this clause when ``inplace=True``.

        Warning:
            Mutation requires ``inplace=True``. Prefer ``clause | lit`` (or
            ``clause |= lit`` with rebinding) for immutable operator behavior.
        """
        if not inplace:
            raise TypeError("Clause.append() requires keyword argument inplace=True to mutate.")
        if not isinstance(literal, Literal):
            raise TypeError("Clause.append() expects a Literal.")
        _ensure_same_model_pair_fast(self, literal)
        dim = self._model._lit_to_dimacs(literal)
        self._ensure_mutable_dimacs().append(dim)
        if self._literals_cache is not None:
            self._literals_cache.append(literal)
        return self

    def __invert__(self):
        raise TypeError("Cannot directly negate a Clause. Negate literals individually to maintain strict CNF.")

    def __and__(self, other):
        if isinstance(other, Literal):
            _ensure_same_model_pair_fast(self, other)
            return ClauseGroup._from_dimacs_trusted(
                self._model,
                (self._dimacs, (self._model._lit_to_dimacs(other),)),
            )
        if isinstance(other, Clause):
            _ensure_same_model_pair_fast(self, other)
            return ClauseGroup._from_dimacs_trusted(self._model, (self._dimacs, other.dimacs))
        if isinstance(other, ClauseGroup):
            _ensure_same_model_pair_fast(self, other)
            return ClauseGroup._from_dimacs_trusted(
                self._model,
                (self._dimacs, *other._clauses),
                amo_groups=ClauseGroup._copy_groups(other._amo_groups),
                eo_groups=ClauseGroup._copy_groups(other._eo_groups),
            )
        raise TypeError("AND only supports Literal, Clause, or ClauseGroup operands.")

    def only_if(self, condition: "Literal") -> "Clause":
        """Return a gated clause enforcing this clause only when ``condition`` is true.

        Meaning: ``condition -> clause``.
        """
        if not isinstance(condition, Literal):
            raise _detection_error()
        _ensure_same_model_pair_fast(self, condition)
        return Clause._from_dimacs_trusted(self._model, (*self._dimacs, self._model._lit_to_dimacs(~condition)))

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
                parts.extend(out)
            elif isinstance(out, PBConstraint):
                parts.extend(out.clauses())
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
            _ensure_same_model_pair_fast(self, other)
            return Clause(self._model, [self, other])
        if isinstance(other, Clause):
            return other.__or__(self)
        raise TypeError("OR only supports Literal or Clause.")

    def __and__(self, other):
        if isinstance(other, Literal):
            _ensure_same_model_pair_fast(self, other)
            return ClauseGroup(
                self._model,
                [Clause(self._model, [self]), Clause(self._model, [other])],
            )
        if isinstance(other, Clause):
            _ensure_same_model_pair_fast(self, other)
            return ClauseGroup(self._model, [Clause(self._model, [self]), other])
        if isinstance(other, ClauseGroup):
            _ensure_same_model_pair_fast(self, other)
            return ClauseGroup(self._model, [Clause(self._model, [self]), *other])
        raise TypeError("AND only supports Literal operands.")

    def __eq__(self, other):  # type: ignore[override]
        if isinstance(other, IntRelation):
            _ensure_same_model_pair_fast(self, other)
            return other.reify(self)
        if isinstance(other, Literal):
            if self is other:
                return True
            _ensure_same_model_pair_fast(self, other)
            # Boolean equivalence: (self -> other) & (other -> self)
            return ClauseGroup(
                self._model,
                [
                    Clause(self._model, [~self, other]),
                    Clause(self._model, [~other, self]),
                ],
            )
        result = _compare_pb_operands(self, "==", other)
        return False if result is NotImplemented else result

    def __ne__(self, other):  # type: ignore[override]
        if isinstance(other, IntRelation):
            _ensure_same_model_pair_fast(self, other)
            return other.reify(~self)
        if isinstance(other, Literal):
            # Keep Python inequality boolean-stable for now; modeling inequality can
            # be added explicitly later if needed.
            return not (self is other)
        result = _compare_pb_operands(self, "!=", other)
        return True if result is NotImplemented else result

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
        _ensure_same_model_pair_fast(self, condition)
        return Clause(self._model, [self, ~condition])

    def implies(self, target):
        """Return encoding of ``self -> target``.

        Supported targets include ``Literal``, ``Clause``, ``ClauseGroup``, and
        lazy :class:`PBConstraint`.
        """
        # source -> target  <=>  target.only_if(source)
        if isinstance(target, Literal):
            _ensure_same_model_pair_fast(self, target)
            return target.only_if(self)
        if isinstance(target, Clause):
            _ensure_same_model_pair_fast(self, target)
            return target.only_if(self)
        if isinstance(target, ClauseGroup):
            _ensure_same_model_pair_fast(self, target)
            return target.only_if(self)
        if isinstance(target, PBConstraint):
            _ensure_same_model_pair_fast(self, target)
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

    @classmethod
    def _unsafe_new(cls, coefficient: int | float, literal: Literal) -> "Term":
        """Internal fast constructor that skips runtime validation."""
        obj = object.__new__(cls)
        object.__setattr__(obj, "coefficient", coefficient)
        object.__setattr__(obj, "literal", literal)
        return obj

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
        result = _compare_pb_operands(self, op, rhs)
        if result is NotImplemented:
            raise TypeError(f"Unsupported PB comparison operand: {type(rhs)!r}")
        return result

    def __le__(self, rhs):
        return self._finalize_compare("<=", rhs)

    def __lt__(self, rhs):
        return self._finalize_compare("<", rhs)

    def __ge__(self, rhs):
        return self._finalize_compare(">=", rhs)

    def __gt__(self, rhs):
        return self._finalize_compare(">", rhs)

    def __eq__(self, rhs):  # type: ignore[override]
        result = _compare_pb_operands(self, "==", rhs)
        return False if result is NotImplemented else result

    def __ne__(self, rhs):  # type: ignore[override]
        result = _compare_pb_operands(self, "!=", rhs)
        return True if result is NotImplemented else result


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
        return self._compare_pb("<=", rhs)

    def __lt__(self, rhs):
        return self._compare_pb("<", rhs)

    def __ge__(self, rhs):
        return self._compare_pb(">=", rhs)

    def __gt__(self, rhs):
        return self._compare_pb(">", rhs)

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
        result = _compare_pb_operands(self, "==", rhs)
        return False if result is NotImplemented else result

    def __ne__(self, rhs):  # type: ignore[override]
        result = _compare_pb_operands(self, "!=", rhs)
        return True if result is NotImplemented else result

    def _compare_pb(self, op: str, rhs):
        result = _compare_pb_operands(self, op, rhs)
        if result is NotImplemented:
            raise TypeError(f"Unsupported PB comparison operand: {type(rhs)!r}")
        return result

    @property
    def lb(self) -> int:  # pragma: no cover - overridden by subclasses
        """Lower bound for this lazy integer expression."""
        raise NotImplementedError

    @property
    def ub(self) -> int:  # pragma: no cover - overridden by subclasses
        """Upper bound for this lazy integer expression."""
        raise NotImplementedError


class DivExpr(_LazyIntExpr):
    """Lazy ``IntVar // constant`` derived integer expression."""

    __slots__ = ("_src", "_divisor", "_lb", "_ub")

    def __init__(self, src: "IntVar | _LazyIntExpr", divisor: int):
        super().__init__(src._model)
        self._src = src
        self._divisor = divisor
        self._lb = src.lb // divisor
        self._ub = src.ub // divisor

    @property
    def lb(self) -> int:
        """Lower bound of this lazy quotient expression."""
        return self._lb

    @property
    def ub(self) -> int:
        """Upper bound of this lazy quotient expression."""
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
        self._ub = src.ub * factor

    @property
    def lb(self) -> int:
        """Lower bound of this lazy scaled expression."""
        return self._lb

    @property
    def ub(self) -> int:
        """Upper bound of this lazy scaled expression."""
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
        """Upper bound of this lazy aggregate expression."""
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
    __slots__ = ("_model", "terms", "constant", "int_terms", "_collapsed", "_term_index")

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
        self._collapsed = True
        self._term_index = None

    @classmethod
    def _from_terms_trusted(
        cls,
        model: "Model",
        terms: Sequence[Term],
        constant: int = 0,
        *,
        int_terms: Sequence[tuple[int, IntVar | _LazyIntExpr]] | None = None,
        collapsed: bool = True,
    ) -> "PBExpr":
        expr = cls.__new__(cls)
        expr._model = model
        expr.terms = list(terms)
        expr.constant = int(constant)
        expr.int_terms = [(int(c), v) for c, v in (int_terms or []) if int(c) != 0]
        expr._collapsed = bool(collapsed)
        expr._term_index = None
        return expr

    def _ensure_term_index(self) -> dict[tuple[int, bool], int]:
        if not self._collapsed:
            self.terms = self._collapse_terms(self.terms)
            self._collapsed = True
            self._term_index = None
        index = self._term_index
        if index is None:
            index = {(t.literal.id, t.literal.polarity): i for i, t in enumerate(self.terms)}
            self._term_index = index
        return index

    def _accumulate_terms_inplace(self, incoming: Sequence[Term]) -> None:
        if not incoming:
            return
        index = self._ensure_term_index()
        for t in incoming:
            key = (t.literal.id, t.literal.polarity)
            pos = index.get(key)
            if pos is None:
                coeff = t.coefficient
                if isinstance(coeff, float):
                    if abs(coeff) <= FLOAT_ZERO_TOL:
                        continue
                elif coeff == 0:
                    continue
                index[key] = len(self.terms)
                self.terms.append(t)
                continue

            prev = self.terms[pos]
            prev_coeff = prev.coefficient
            coeff = t.coefficient
            if isinstance(prev_coeff, float) or isinstance(coeff, float):
                new_coeff = float(prev_coeff) + float(coeff)
                zero = abs(new_coeff) <= FLOAT_ZERO_TOL
            else:
                new_coeff = int(prev_coeff) + int(coeff)
                zero = new_coeff == 0

            if zero:
                self.terms.pop(pos)
                del index[key]
                for i in range(pos, len(self.terms)):
                    lit = self.terms[i].literal
                    index[(lit.id, lit.polarity)] = i
                continue

            self.terms[pos] = Term._unsafe_new(new_coeff, prev.literal)

    @staticmethod
    def _merge_int_terms(
        left: Sequence[tuple[int, IntVar | _LazyIntExpr]],
        right: Sequence[tuple[int, IntVar | _LazyIntExpr]],
        sign: int,
    ) -> list[tuple[int, IntVar | _LazyIntExpr]]:
        out = [*left]
        if sign == 1:
            out.extend((int(c), v) for c, v in right if int(c) != 0)
        else:
            out.extend((-int(c), v) for c, v in right if int(c) != 0)
        return out

    @staticmethod
    def _signed_terms(terms: Sequence[Term], sign: int) -> list[Term]:
        if sign == 1:
            return list(terms)
        return [Term._unsafe_new(sign * t.coefficient, t.literal) for t in terms]

    @classmethod
    def _merge_terms_immutable(
        cls,
        lhs: "PBExpr",
        rhs: "PBExpr",
        sign: int,
    ) -> tuple[list[Term], bool]:
        rhs_terms = cls._signed_terms(rhs.terms, sign)
        if lhs._collapsed and rhs._collapsed:
            if not lhs.terms:
                return rhs_terms, True
            if not rhs_terms:
                return list(lhs.terms), True
            if cls._terms_disjoint(lhs.terms, rhs_terms):
                return [*lhs.terms, *rhs_terms], True
        return [*lhs.terms, *rhs_terms], False

    def _accumulate_int_terms_inplace(
        self,
        incoming: Sequence[tuple[int, IntVar | _LazyIntExpr]],
        sign: int,
    ) -> None:
        if sign == 1:
            self.int_terms.extend((int(c), v) for c, v in incoming if int(c) != 0)
        else:
            self.int_terms.extend((-int(c), v) for c, v in incoming if int(c) != 0)

    @staticmethod
    def _collapse_terms(terms: list[Term]) -> list[Term]:
        # Collapse repeated identical literals (same var + polarity) by summing
        # coefficients. We intentionally do not fold x and ~x together here since
        # that would introduce an offset; offset normalization is handled later in
        # encoder dispatch.
        if not terms:
            return []
        if len(terms) == 1:
            t0 = terms[0]
            c0 = t0.coefficient
            if isinstance(c0, float):
                return [] if abs(c0) <= FLOAT_ZERO_TOL else terms
            return [] if c0 == 0 else terms
        # Very common fast path: no duplicate literals and no zero coefficients.
        # In this case we can keep the original term objects as-is.
        seen: set[tuple[int, bool]] = set()
        no_dupes = True
        all_nonzero = True
        for t in terms:
            key = (t.literal.id, t.literal.polarity)
            if key in seen:
                no_dupes = False
                break
            seen.add(key)
            coeff = t.coefficient
            if isinstance(coeff, float):
                if abs(coeff) <= FLOAT_ZERO_TOL:
                    all_nonzero = False
                    break
            elif coeff == 0:
                all_nonzero = False
                break
        if no_dupes and all_nonzero:
            return terms
        all_int_coeffs = True
        for t in terms:
            if isinstance(t.coefficient, float):
                all_int_coeffs = False
                break
        if all_int_coeffs:
            acc_i: dict[tuple[int, bool], int] = {}
            lit_ref: dict[tuple[int, bool], Literal] = {}
            order: list[tuple[int, bool]] = []
            for t in terms:
                key = (t.literal.id, t.literal.polarity)
                prev = acc_i.get(key)
                if prev is None:
                    acc_i[key] = int(t.coefficient)
                    lit_ref[key] = t.literal
                    order.append(key)
                else:
                    acc_i[key] = prev + int(t.coefficient)
            out_i: list[Term] = []
            for key in order:
                coeff = acc_i[key]
                if coeff != 0:
                    out_i.append(Term._unsafe_new(coeff, lit_ref[key]))
            return out_i
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
                if abs(coeff) <= FLOAT_ZERO_TOL:
                    continue
                out.append(Term._unsafe_new(coeff, lit_ref[key]))
            elif coeff != 0:
                out.append(Term._unsafe_new(coeff, lit_ref[key]))
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
            return cls._from_terms_trusted(item.literal._model, [item], 0, collapsed=True)
        if isinstance(item, Literal):
            return cls._from_terms_trusted(item._model, [Term(1, item)], 0, collapsed=True)
        if isinstance(item, IntVar):
            return item._as_pbexpr()
        if isinstance(item, _LazyIntExpr):
            return cls._from_terms_trusted(item._model, [], 0, int_terms=[(1, item)], collapsed=True)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            # Constants are carried and normalized during PB compilation. This
            # keeps algebraic forms like `a + b + 2 <= 3` equivalent to
            # `a + b <= 1` in the public DSL.
            return cls._from_terms_trusted(None, [], item, collapsed=True)  # type: ignore[arg-type]
        raise TypeError(f"Unsupported PB item: {type(item)!r}")

    @staticmethod
    def _terms_disjoint(a_terms: Sequence[Term], b_terms: Sequence[Term]) -> bool:
        if not a_terms or not b_terms:
            return True
        if len(a_terms) > len(b_terms):
            a_terms, b_terms = b_terms, a_terms
        keys = {(t.literal.id, t.literal.polarity) for t in a_terms}
        for t in b_terms:
            if (t.literal.id, t.literal.polarity) in keys:
                return False
        return True

    def _merge(self, other: "PBExpr", sign: int = 1) -> "PBExpr":
        model = _ensure_same_model(self, other)
        int_terms = self._merge_int_terms(self.int_terms, other.int_terms, sign)
        terms, collapsed = self._merge_terms_immutable(self, other, sign)
        if collapsed:
            return PBExpr._from_terms_trusted(
                model,
                terms,
                self.constant + sign * other.constant,
                int_terms=int_terms,
                collapsed=True,
            )
        return PBExpr(model, terms, self.constant + sign * other.constant, int_terms=int_terms)

    def _realize_int_terms(self, model: "Model") -> "PBExpr":
        if not self.int_terms:
            return self
        _ensure_same_model(self, model)
        out = PBExpr._from_terms_trusted(model, self.terms, self.constant, collapsed=self._collapsed)
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
            ``expr += x`` with rebinding) for immutable operator behavior.
        """
        if not inplace:
            raise TypeError("PBExpr.add() requires keyword argument inplace=True to mutate.")
        other_expr = PBExpr.from_item(other)
        model = _ensure_same_model(self, other_expr)
        if self._model is None:
            self._model = model
        if other_expr.terms:
            self._accumulate_terms_inplace(other_expr.terms)
        self.constant = self.constant + other_expr.constant
        if other_expr.int_terms:
            self._accumulate_int_terms_inplace(other_expr.int_terms, +1)
        return self

    def sub(self, other, *, inplace: bool = False) -> "PBExpr":
        """Subtract a PB-compatible item from this expression when ``inplace=True``.

        Warning:
            Mutation requires ``inplace=True``. Prefer ``expr - x`` (or
            ``expr -= x`` with rebinding) for immutable operator behavior.
        """
        if not inplace:
            raise TypeError("PBExpr.sub() requires keyword argument inplace=True to mutate.")
        other_expr = PBExpr.from_item(other)
        model = _ensure_same_model(self, other_expr)
        if self._model is None:
            self._model = model
        if other_expr.terms:
            neg_terms = [Term(-t.coefficient, t.literal) for t in other_expr.terms]
            self._accumulate_terms_inplace(neg_terms)
        self.constant = self.constant - other_expr.constant
        if other_expr.int_terms:
            self._accumulate_int_terms_inplace(other_expr.int_terms, -1)
        return self

    def _finalize_compare(self, op: str, rhs):
        result = _compare_pb_operands(self, op, rhs)
        if result is NotImplemented:
            raise TypeError(f"Unsupported PB comparison operand: {type(rhs)!r}")
        return result

    def __le__(self, rhs):
        return self._finalize_compare("<=", rhs)

    def __lt__(self, rhs):
        return self._finalize_compare("<", rhs)

    def __ge__(self, rhs):
        return self._finalize_compare(">=", rhs)

    def __gt__(self, rhs):
        return self._finalize_compare(">", rhs)

    def __eq__(self, rhs):  # type: ignore[override]
        result = _compare_pb_operands(self, "==", rhs)
        return False if result is NotImplemented else result

    def __ne__(self, rhs):  # type: ignore[override]
        result = _compare_pb_operands(self, "!=", rhs)
        return True if result is NotImplemented else result

    def __repr__(self) -> str:
        return f"PBExpr(terms={self.terms!r}, int_terms={self.int_terms!r}, c={self.constant})"


def _coerce_pb_comparison_operand(value) -> PBExpr | None:
    """Return a non-materializing PB view of a supported comparison operand."""
    if isinstance(value, (Literal, Term, PBExpr, IntVar, _LazyIntExpr)):
        return PBExpr.from_item(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return PBExpr.from_item(value)
    return None


def _compare_pb_operands(lhs, op: str, rhs):
    """Build a PB comparison when both operands have a PB representation."""
    lhs_expr = _coerce_pb_comparison_operand(lhs)
    rhs_expr = _coerce_pb_comparison_operand(rhs)
    if lhs_expr is None or rhs_expr is None:
        return NotImplemented
    model = _ensure_same_model(lhs_expr, rhs_expr)
    if model is None:
        return NotImplemented
    return PBConstraint(model, lhs_expr, op, rhs_expr)


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

        Meaning: ``condition -> PB``.
        """
        if not isinstance(condition, Literal):
            raise _detection_error()
        _ensure_same_model_pair_fast(self, condition)
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
        if self._op == "!=":
            return PBConstraint(self._model, self._lhs, "==", self._rhs)
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
        _ensure_same_model_pair_fast(self, target)
        neg = self._negated()
        if isinstance(neg, PBConstraint):
            return neg.only_if(~target)

        # Equality antecedent: (~target) -> (A OR B), where A/B are PB constraints.
        # Encode the disjunction with a selector and two half-reified branches.
        left, right = neg
        return DeferredClauseGroup(
            self._model,
            lambda: (
                left.only_if(~target).only_if((sel := self._model.bool())).clauses()
                & right.only_if(~target).only_if(~sel).clauses()
            ),
        )

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



from .variables import IntVar
