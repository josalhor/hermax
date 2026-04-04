from __future__ import annotations

import statistics
from dataclasses import dataclass

from hermax.encoder.pb import PBItem
from hermax.encoder.pbamo import PBAMOEnc
from hermax.internal.kmerge import KMergeConfig, PBConstraintStub, analyze_group


@dataclass(frozen=True)
class ClusterDiagnostic:
    scenario: str
    family: str
    proxy_sep: float
    proxy_merged: float
    proxy_reduction: float
    actual_sep_clauses: int
    actual_merged_clauses: int
    actual_sep_literals: int
    actual_merged_literals: int
    clause_ratio: float
    literal_ratio: float
    merge_predicted_good: bool
    merge_actually_good: bool


def scenario_to_stubs(scenario) -> list[PBConstraintStub]:
    stubs = []
    lits = tuple(range(1, scenario.n_vars + 1))
    for weights, bound in zip(scenario.weights, scenario.bounds):
        stubs.append(
            PBConstraintStub(
                lits=lits,
                weights=tuple(int(w) for w in weights),
                bound=int(bound),
                op="<=",
            )
        )
    return stubs


def _cnf_clause_count(cnf) -> int:
    return len(cnf.clauses)


def _cnf_literal_count(cnf) -> int:
    return sum(len(clause) for clause in cnf.clauses)


def diagnose_cluster(scenario, config: KMergeConfig | None = None) -> ClusterDiagnostic:
    cfg = config or KMergeConfig()
    stubs = scenario_to_stubs(scenario)
    proxy_sep = sum(analyze_group([stub], cfg).total_cost for stub in stubs)
    merged_analysis = analyze_group(stubs, cfg)
    proxy_merged = merged_analysis.total_cost
    proxy_reduction = proxy_sep - proxy_merged

    top_id = scenario.n_vars
    sep_clause_count = 0
    sep_literal_count = 0
    current_top = top_id
    lits = list(range(1, scenario.n_vars + 1))
    for stub in stubs:
        cnf = PBAMOEnc.auto_leq(
            lits=lits,
            weights=list(stub.weights),
            bound=int(stub.bound),
            amo_groups=[],
            eo_groups=[],
            top_id=current_top,
        )
        sep_clause_count += _cnf_clause_count(cnf)
        sep_literal_count += _cnf_literal_count(cnf)
        current_top = max(current_top, cnf.nv)

    merged_cnf = PBAMOEnc.multi_leq(
        lits=tuple(lits),
        stubs=stubs,
        top_id=top_id,
        kmerge_config=cfg,
    )
    merged_clause_count = _cnf_clause_count(merged_cnf)
    merged_literal_count = _cnf_literal_count(merged_cnf)

    return ClusterDiagnostic(
        scenario=scenario.name,
        family=scenario.family,
        proxy_sep=float(proxy_sep),
        proxy_merged=float(proxy_merged),
        proxy_reduction=float(proxy_reduction),
        actual_sep_clauses=int(sep_clause_count),
        actual_merged_clauses=int(merged_clause_count),
        actual_sep_literals=int(sep_literal_count),
        actual_merged_literals=int(merged_literal_count),
        clause_ratio=float(merged_clause_count) / max(float(sep_clause_count), 1.0),
        literal_ratio=float(merged_literal_count) / max(float(sep_literal_count), 1.0),
        merge_predicted_good=bool(proxy_reduction > 1e-6),
        merge_actually_good=bool(
            merged_clause_count <= sep_clause_count and merged_literal_count <= sep_literal_count
        ),
    )


def summarize_diagnostics(diags: list[ClusterDiagnostic]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[ClusterDiagnostic]] = {}
    for diag in diags:
        grouped.setdefault(diag.family, []).append(diag)
    out: dict[str, dict[str, float]] = {}
    for family, items in grouped.items():
        out[family] = {
            "count": float(len(items)),
            "proxy_positive_rate": statistics.mean(1.0 if item.merge_predicted_good else 0.0 for item in items),
            "actual_positive_rate": statistics.mean(1.0 if item.merge_actually_good else 0.0 for item in items),
            "clause_ratio": statistics.mean(item.clause_ratio for item in items),
            "literal_ratio": statistics.mean(item.literal_ratio for item in items),
        }
    return out
