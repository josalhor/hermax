from __future__ import annotations

from typing import Any

from pysat.formula import WCNF, WCNFPlus


def _is_optilog_wcnf_instance(formula: Any) -> bool:
    cls = formula.__class__
    mod = getattr(cls, "__module__", "")
    name = getattr(cls, "__name__", "")
    return mod.startswith("optilog.") and name == "WCNF"


def _convert_optilog_wcnf(formula: Any) -> WCNF:
    """
    Convert an OptiLog WCNF instance into a PySAT WCNF.

    Expected OptiLog fields (based on public docs):
    - hard_clauses: Iterable[Iterable[int]]
    - soft_clauses: Iterable[Tuple[weight, clause]]
    """
    # Fast path for OptiLog API:
    # - formula.hard_clauses: list[list[int]]
    # - formula.soft_clauses: list[tuple[int, list[int]]]
    # - formula.max_var(): int
    soft_pairs = formula.soft_clauses
    out = WCNF()
    out.hard = formula.hard_clauses
    out.soft = [clause for _, clause in soft_pairs]
    out.wght = [weight for weight, _ in soft_pairs]
    out.nv = formula.max_var()
    return out


def normalize_wcnf_formula(formula: Any) -> Any:
    """
    Normalize WCNF-like inputs to PySAT WCNF when needed.

    Returns ``None`` unchanged.
    Returns PySAT ``WCNF``/``WCNFPlus`` unchanged.
    Converts OptiLog ``WCNF`` into PySAT ``WCNF``.
    Returns any other object unchanged, so existing wrapper-specific
    best-effort loaders can still handle custom WCNF-like objects.
    """
    if formula is None:
        return None
    if isinstance(formula, (WCNF, WCNFPlus)):
        return formula
    if _is_optilog_wcnf_instance(formula):
        return _convert_optilog_wcnf(formula)
    return formula
