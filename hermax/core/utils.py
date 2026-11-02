from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Sequence

from hermax.formula import WCNF, WCNFPlus


@dataclass(frozen=True)
class WCNFData:
    """Stable view of a WCNF-like input used by solver adapters.

    Third-party formula implementations do not all expose PySAT's exact
    ``hard``/``soft``/``wght`` layout.  Keep that compatibility at this
    boundary; solver implementations should consume this representation
    rather than probe arbitrary formula objects themselves.
    """

    hard: Sequence
    soft: Sequence
    num_vars: int


class _SoftTerms(Sequence):
    """Repeatable term view; native formulas need no whole-formula list export."""
    def __init__(self, formula):
        self._clauses = formula.soft
        self._weights = formula.wght
        if len(self._clauses) != len(self._weights):
            raise ValueError('Soft clauses and weights must have equal length.')

    def __len__(self):
        return len(self._clauses)

    def __iter__(self):
        return zip(self._clauses, self._weights)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return list(zip(self._clauses[index], self._weights[index]))
        return self._clauses[index], self._weights[index]


def _is_optilog_wcnf_instance(formula: Any) -> bool:
    cls = formula.__class__
    mod = getattr(cls, "__module__", "")
    name = getattr(cls, "__name__", "")
    return mod.startswith("optilog.") and (
        name == "WCNF"
        or (hasattr(formula, "hard_clauses") and hasattr(formula, "soft_clauses") and callable(getattr(formula, "max_var", None)))
    )


def _convert_optilog_wcnf(formula: Any) -> WCNF:
    """
    Convert an OptiLog WCNF instance into a native Hermax WCNF.

    Expected OptiLog fields (based on public docs):
    - hard_clauses: Iterable[Iterable[int]]
    - soft_clauses: Iterable[Tuple[weight, clause]]
    """
    # Fast path for OptiLog API:
    # - formula.hard_clauses: list[list[int]]
    # - formula.soft_clauses: list[tuple[int, list[int]]]
    # - formula.max_var(): int
    soft_pairs = formula.soft_clauses
    hard = [list(clause) for clause in formula.hard_clauses]
    if any(isinstance(lit, bool) or not isinstance(lit, int) or lit == 0 for clause in hard for lit in clause):
        raise ValueError("WCNF hard clauses must contain non-zero integer literals.")
    normalized_soft = []
    for weight, clause in soft_pairs:
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ValueError("WCNF soft weights must be integers.")
        copied = list(clause)
        if any(isinstance(lit, bool) or not isinstance(lit, int) or lit == 0 for lit in copied):
            raise ValueError("WCNF soft clauses must contain non-zero integer literals.")
        normalized_soft.append((int(weight), copied))
    out = WCNF()
    out.hard = hard
    out.soft = [clause for _, clause in normalized_soft]
    out.wght = [weight for weight, _ in normalized_soft]
    out.nv = formula.max_var()
    return out


def normalize_wcnf_formula(formula: Any) -> Any:
    """
    Normalize foreign WCNF inputs when needed.

    Returns ``None`` unchanged.
    Returns PySAT ``WCNF``/``WCNFPlus`` unchanged.
    Converts OptiLog ``WCNF`` into Hermax ``WCNF``.
    Returns any other object unchanged, so existing wrapper-specific
    best-effort loaders can still handle custom WCNF-like objects.
    """
    if formula is None:
        return None
    if isinstance(formula, WCNF):
        return formula.validate()
    if _is_optilog_wcnf_instance(formula):
        return _convert_optilog_wcnf(formula)
    return formula


def extract_wcnf_data(formula: Any) -> WCNFData:
    """Extract clauses from a PySAT or compatible WCNF object.

    Compatibility attribute access is deliberately contained here.
    External clauses are copied. Native formulas expose read-only clause values
    through their existing collections, avoiding whole-formula materialization.
    """
    if formula is None:
        raise TypeError("formula must be a WCNF-like object, not None.")

    if getattr(formula, "atms", None):
        raise NotImplementedError("Native cardinality and pseudo-Boolean constraints are unsupported; encode them as clauses first.")

    if isinstance(formula, WCNF):
        formula.validate()
        return WCNFData(formula.hard, _SoftTerms(formula), formula.nv)

    try:
        hard_attr = formula.hard
        soft_attr = formula.soft
    except AttributeError as exc:
        raise TypeError(
            "formula must expose WCNF-compatible 'hard' and 'soft' attributes."
        ) from exc

    hard = [list(clause) for clause in hard_attr]
    if hasattr(formula, "wght"):
        weights = formula.wght
    else:
        weights = None

    if weights is not None:
        if len(weights) != len(soft_attr):
            raise ValueError("Soft clauses and weights must have equal length.")
        soft = [(list(clause), weight) for clause, weight in zip(soft_attr, weights)]
    else:
        soft = []
        for item in soft_attr:
            if isinstance(item, tuple) and len(item) >= 2:
                clause, weight = item[0], item[1]
            else:
                clause, weight = item, 1
            soft.append((list(clause), weight))

    # ``nv`` is part of PySAT's WCNF API.  It is optional only for compatible
    # third-party inputs, whose declared variable count is then inferred from
    # the literals by the consuming adapter.
    num_vars = int(formula.nv) if hasattr(formula, "nv") else 0
    return WCNFData(hard=hard, soft=soft, num_vars=num_vars)
