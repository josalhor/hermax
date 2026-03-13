"""Internal bindings for structured PB(AMO) encoders."""

from __future__ import annotations

from collections.abc import Iterable

from pysat.formula import CNFPlus

from . import _structuredpb
from .card import CardEnc, EncType as CardEncType


CARD_STRUCTURE_THRESHOLD = 0.27
CARD_FLAT_ENCODING = CardEncType.kmtotalizer


class EncType:
    best = "best"
    mdd = "mdd"
    gswc = "gswc"
    ggpw = "ggpw"
    gmto = "gmto"
    rggt = "rggt"


class OverlapPolicy:
    baseline_paper = "baseline_paper"
    paper_best_fit_dynamic_future = "paper_best_fit_dynamic_future"


def _normalize_groups(groups):
    return [[int(lit) for lit in group] for group in groups]


def _normalize_candidate_groups(groups: Iterable[Iterable[int]] | None):
    if not groups:
        return []
    out = []
    for group in groups:
        uniq = []
        seen = set()
        for lit in group:
            lit_i = int(lit)
            if lit_i in seen:
                continue
            seen.add(lit_i)
            uniq.append(lit_i)
        if uniq:
            out.append(uniq)
    return out


def _pair_support_maps(lits, amo_groups, eo_groups):
    pair_support: dict[tuple[int, int], int] = {}
    eo_pair_support: dict[tuple[int, int], int] = {}
    mutex_neighbors = {int(lit): set() for lit in lits}

    def _add_group_support(group, target):
        for i in range(len(group)):
            li = int(group[i])
            for j in range(i + 1, len(group)):
                lj = int(group[j])
                key = (li, lj) if li < lj else (lj, li)
                target[key] = target.get(key, 0) + 1
                mutex_neighbors[li].add(lj)
                mutex_neighbors[lj].add(li)

    for group in amo_groups:
        _add_group_support(group, pair_support)
    for group in eo_groups:
        _add_group_support(group, pair_support)
        _add_group_support(group, eo_pair_support)

    return pair_support, eo_pair_support, mutex_neighbors


def _pair_score(pair_map, a: int, b: int) -> int:
    if a == b:
        return 0
    key = (a, b) if a < b else (b, a)
    return int(pair_map.get(key, 0))


def _group_is_compatible(mutex_neighbors, lit: int, group) -> bool:
    neighbors = mutex_neighbors.get(int(lit), set())
    return all(int(member) in neighbors for member in group)


def _partition_score(grouping):
    # Canonical deterministic ordering for stable comparisons.
    normalized = [tuple(sorted(int(l) for l in group)) for group in grouping if group]
    normalized.sort(key=lambda g: (len(g), g))
    return tuple(normalized)


def choose_overlap_partition(
    lits,
    weights,
    *,
    amo_groups=None,
    eo_groups=None,
    policy: str = OverlapPolicy.paper_best_fit_dynamic_future,
):
    lits = [int(lit) for lit in lits]
    weight_by_lit = {int(lit): int(weight) for lit, weight in zip(lits, weights)}
    amo_groups = _normalize_candidate_groups(amo_groups)
    eo_groups = _normalize_candidate_groups(eo_groups)
    pair_support, eo_pair_support, mutex_neighbors = _pair_support_maps(lits, amo_groups, eo_groups)

    if policy not in {OverlapPolicy.baseline_paper, OverlapPolicy.paper_best_fit_dynamic_future}:
        raise ValueError(f"Unknown overlap policy: {policy!r}")

    groups: list[list[int]] = []

    if policy == OverlapPolicy.baseline_paper:
        for lit in lits:
            placed = False
            for group in groups:
                if _group_is_compatible(mutex_neighbors, lit, group):
                    group.append(int(lit))
                    placed = True
                    break
            if not placed:
                groups.append([int(lit)])
        return [sorted(group) for group in groups]

    remaining = set(lits)

    def compatible_groups_count(lit: int) -> int:
        return sum(1 for group in groups if _group_is_compatible(mutex_neighbors, lit, group))

    def eo_support_degree(lit: int) -> int:
        return sum(_pair_score(eo_pair_support, lit, other) for other in lits if other != lit)

    def pair_support_degree(lit: int) -> int:
        return sum(_pair_score(pair_support, lit, other) for other in lits if other != lit)

    def future_compatibility(lit: int, group) -> int:
        proposed = [*group, int(lit)]
        total = 0
        for other in remaining:
            if other == lit:
                continue
            if _group_is_compatible(mutex_neighbors, other, proposed):
                total += 1
        return total

    while remaining:
        lit = min(
            remaining,
            key=lambda cur: (
                compatible_groups_count(cur),
                -eo_support_degree(cur),
                -pair_support_degree(cur),
                -len(mutex_neighbors.get(cur, set())),
                -weight_by_lit[cur],
                cur,
            ),
        )
        compatible = [group for group in groups if _group_is_compatible(mutex_neighbors, lit, group)]
        if not compatible:
            groups.append([int(lit)])
            remaining.remove(lit)
            continue

        def score_group(group):
            eo_support = sum(_pair_score(eo_pair_support, lit, member) for member in group)
            support = sum(_pair_score(pair_support, lit, member) for member in group)
            future = future_compatibility(lit, group)
            candidate_weights = [weight_by_lit[member] for member in group] + [weight_by_lit[lit]]
            spread = max(candidate_weights) - min(candidate_weights)
            return (
                eo_support,
                support,
                future,
                len(group),
                -spread,
                sum(candidate_weights),
                -min(group),
            )

        best = max(compatible, key=score_group)
        best.append(int(lit))
        remaining.remove(lit)

    return [sorted(group) for group in groups]


def amo_upper_bound(weights, groups, lits=None) -> int:
    if lits is None:
        lits = list(range(1, len(weights) + 1))
    weight_by_lit = {int(lit): int(weight) for lit, weight in zip(lits, weights)}
    return sum(max(weight_by_lit[lit] for lit in group) for group in groups)


def extract_features(lits, weights, groups, bound):
    lits = [int(lit) for lit in lits]
    weights = [int(weight) for weight in weights]
    groups = _normalize_groups(groups)
    n_terms = len(lits)
    amo_cap = amo_upper_bound(weights, groups, lits=lits) if groups else 0
    return {
        "n_terms": float(n_terms),
        "n_groups": float(len(groups)),
        "bound_ratio_amo": (float(bound) / float(amo_cap)) if amo_cap > 0 else 0.0,
    }


def extract_cardinality_features(lits, groups, bound):
    lits = [int(lit) for lit in lits]
    groups = _normalize_groups(groups)
    n_terms = len(lits)
    non_singleton = [group for group in groups if len(group) > 1]
    covered = sum(len(group) for group in non_singleton)
    structured_coverage = (float(covered) / float(n_terms)) if n_terms > 0 else 0.0
    mutex_degree_sum = sum((len(group) - 1) * len(group) for group in non_singleton)
    mean_mutex_degree = (float(mutex_degree_sum) / float(n_terms)) if n_terms > 0 else 0.0
    amo_cap = float(len(groups)) if groups else 0.0
    amo_upper_bound_ratio = (float(bound) / amo_cap) if amo_cap > 0.0 else 0.0
    card_structure_score = structured_coverage * (1.0 + mean_mutex_degree) * (amo_upper_bound_ratio ** 0.5)
    return {
        "n_terms": float(n_terms),
        "n_groups": float(len(groups)),
        "non_singleton_groups": float(len(non_singleton)),
        "structured_coverage": structured_coverage,
        "mean_mutex_degree": mean_mutex_degree,
        "amo_upper_bound_ratio": amo_upper_bound_ratio,
        "card_structure_score": card_structure_score,
    }


def choose_portfolio(lits, weights, groups, bound):
    groups = _normalize_groups(groups)
    non_singleton_groups = sum(1 for group in groups if len(group) > 1)
    if non_singleton_groups == 0:
        return "pblib"
    if len(lits) <= 11:
        return "pblib"
    return "structuredpb"


def choose_cardinality_portfolio(lits, groups, bound):
    features = extract_cardinality_features(lits, groups, bound)
    if features["non_singleton_groups"] == 0.0:
        return "card"
    if features["card_structure_score"] >= CARD_STRUCTURE_THRESHOLD:
        return "structuredpb"
    return "card"


def choose_encoding(lits, weights, groups, bound):
    features = extract_features(lits, weights, groups, bound)
    if features["bound_ratio_amo"] <= 0.91:
        if features["n_terms"] <= 23.0:
            return EncType.rggt
        return EncType.ggpw
    return EncType.mdd


class StructuredPBEnc:
    @classmethod
    def leq(cls, lits, weights, groups, bound, top_id=None, encoding=EncType.best, emit_amo=True):
        if len(lits) != len(weights):
            raise ValueError("Same number of literals and weights is expected.")
        wlits = [(int(lit), int(weight)) for lit, weight in zip(lits, weights)]
        grouped = _normalize_groups(groups)
        if top_id is None:
            top_id = max((abs(int(lit)) for lit in lits), default=0)
        if encoding == EncType.best:
            encoding = choose_encoding(lits, weights, grouped, bound)
        clauses, max_aux = _structuredpb.encode_leq(
            wlits=wlits,
            groups=grouped,
            bound=int(bound),
            top_id=int(top_id),
            encoder=str(encoding),
            emit_amo=bool(emit_amo),
        )
        cnf = CNFPlus()
        cnf.clauses = clauses
        cnf.nv = max(int(top_id), int(max_aux))
        return cnf

    @classmethod
    def auto_leq(
        cls,
        *,
        lits,
        weights,
        bound,
        groups=None,
        amo_groups=None,
        eo_groups=None,
        top_id=None,
        overlap_policy: str = OverlapPolicy.paper_best_fit_dynamic_future,
        structured_encoding=EncType.best,
    ):
        if len(lits) != len(weights):
            raise ValueError("Same number of literals and weights is expected.")
        lits = [int(lit) for lit in lits]
        weights = [int(weight) for weight in weights]
        groups_were_explicit = groups is not None
        normalized_groups = _normalize_groups(groups) if groups is not None else None
        normalized_amo = _normalize_candidate_groups(amo_groups)
        normalized_eo = _normalize_candidate_groups(eo_groups)

        if normalized_groups is not None and (normalized_amo or normalized_eo):
            raise ValueError("Provide either disjoint groups or overlapping AMO/EO candidates, not both.")

        if normalized_groups is None:
            if normalized_amo or normalized_eo:
                normalized_groups = choose_overlap_partition(
                    lits,
                    weights,
                    amo_groups=normalized_amo,
                    eo_groups=normalized_eo,
                    policy=overlap_policy,
                )
            else:
                normalized_groups = [[lit] for lit in lits]

        if top_id is None:
            top_id = max((abs(int(lit)) for lit in lits), default=0)
        top_id = int(top_id)

        if all(int(weight) == 1 for weight in weights):
            return cls._auto_atmost(
                lits=lits,
                bound=int(bound),
                groups=normalized_groups if groups_were_explicit else None,
                amo_groups=normalized_amo if not groups_were_explicit else None,
                eo_groups=normalized_eo if not groups_were_explicit else None,
                top_id=top_id,
                overlap_policy=overlap_policy,
                structured_encoding=structured_encoding,
            )

        portfolio = choose_portfolio(lits, weights, normalized_groups, bound)
        if portfolio == "pblib":
            from .pb import EncType as PBEncType
            from .pb import PBEnc

            cnf = PBEnc.leq(lits=lits, weights=weights, bound=int(bound), top_id=top_id, encoding=PBEncType.best)
        else:
            enc = structured_encoding
            if enc == EncType.best:
                enc = choose_encoding(lits, weights, normalized_groups, bound)
            cnf = cls.leq(
                lits=lits,
                weights=weights,
                groups=normalized_groups,
                bound=int(bound),
                top_id=top_id,
                encoding=enc,
                emit_amo=False,
            )

        extra = CNFPlus()
        extra.nv = int(cnf.nv)
        for group in normalized_amo + normalized_eo:
            uniq = sorted({int(lit) for lit in group})
            if len(uniq) > 1:
                for i in range(len(uniq)):
                    for j in range(i + 1, len(uniq)):
                        extra.clauses.append([-uniq[i], -uniq[j]])
        for group in normalized_eo:
            uniq = sorted({int(lit) for lit in group})
            if uniq:
                extra.clauses.append(list(uniq))
        cnf.clauses.extend(extra.clauses)
        cnf.nv = max(int(cnf.nv), int(extra.nv), top_id)
        return cnf

    @classmethod
    def _auto_atmost(
        cls,
        *,
        lits,
        bound,
        groups=None,
        amo_groups=None,
        eo_groups=None,
        top_id=None,
        overlap_policy: str = OverlapPolicy.paper_best_fit_dynamic_future,
        structured_encoding=EncType.best,
        flat_encoding=CARD_FLAT_ENCODING,
    ):
        lits = [int(lit) for lit in lits]
        normalized_groups = _normalize_groups(groups) if groups is not None else None
        normalized_amo = _normalize_candidate_groups(amo_groups)
        normalized_eo = _normalize_candidate_groups(eo_groups)

        if normalized_groups is not None and (normalized_amo or normalized_eo):
            raise ValueError("Provide either disjoint groups or overlapping AMO/EO candidates, not both.")

        if normalized_groups is None:
            if normalized_amo or normalized_eo:
                normalized_groups = choose_overlap_partition(
                    lits,
                    [1] * len(lits),
                    amo_groups=normalized_amo,
                    eo_groups=normalized_eo,
                    policy=overlap_policy,
                )
            else:
                normalized_groups = [[lit] for lit in lits]

        if top_id is None:
            top_id = max((abs(int(lit)) for lit in lits), default=0)
        top_id = int(top_id)

        portfolio = choose_cardinality_portfolio(lits, normalized_groups, bound)
        if portfolio == "card":
            cnf = CardEnc.atmost(lits=lits, bound=int(bound), top_id=top_id, encoding=flat_encoding)
        else:
            enc = structured_encoding
            if enc == EncType.best:
                enc = choose_encoding(lits, [1] * len(lits), normalized_groups, bound)
            cnf = cls.leq(
                lits=lits,
                weights=[1] * len(lits),
                groups=normalized_groups,
                bound=int(bound),
                top_id=top_id,
                encoding=enc,
                emit_amo=False,
            )

        extra = CNFPlus()
        extra.nv = int(cnf.nv)
        for group in normalized_amo + normalized_eo:
            uniq = sorted({int(lit) for lit in group})
            if len(uniq) > 1:
                for i in range(len(uniq)):
                    for j in range(i + 1, len(uniq)):
                        extra.clauses.append([-uniq[i], -uniq[j]])
        for group in normalized_eo:
            uniq = sorted({int(lit) for lit in group})
            if uniq:
                extra.clauses.append(list(uniq))
        cnf.clauses.extend(extra.clauses)
        cnf.nv = max(int(cnf.nv), int(extra.nv), top_id)
        return cnf


def available_encoders():
    return [EncType.best, *_structuredpb.available_encoders()]


__all__ = [
    "CARD_FLAT_ENCODING",
    "CARD_STRUCTURE_THRESHOLD",
    "EncType",
    "OverlapPolicy",
    "StructuredPBEnc",
    "amo_upper_bound",
    "available_encoders",
    "choose_cardinality_portfolio",
    "choose_encoding",
    "choose_overlap_partition",
    "choose_portfolio",
    "extract_cardinality_features",
    "extract_features",
]
