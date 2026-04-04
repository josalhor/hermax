import itertools
import math
import statistics
from dataclasses import dataclass, replace
from typing import Iterable, NamedTuple, Sequence


class PBConstraintStub(NamedTuple):
    lits: tuple[int, ...]
    weights: tuple[int, ...]
    bound: int
    op: str  # "<=" or "=="


@dataclass(frozen=True)
class KMergeConfig:
    routing_mode: str = "fixed"
    basis_mode: str = "integer"
    extraction_architecture: str = "A"
    discriminator_mode: str = "combo_aggressive"
    combo_baseline_weight: float = 0.5
    combo_delta_weight: float = 1.5
    combo_slack_weight: float = -1.0
    combo_threshold: float = 0.0
    min_merge_reduction_ratio: float = 0.0
    min_shared_support_ratio: float = 0.0
    min_mean_term_len_for_merge: float = 15.0
    use_delay_cost: bool = False
    delay_penalty: float = 1.5
    use_slack_tripwire: bool = False
    slack_conflict_depth_abort: int = 4
    use_short_circuit_penalty: bool = False
    short_circuit_clause_penalty: float = 1.0
    use_delta_variance_penalty: bool = False
    delta_variance_weight: float = 0.25
    selector_bitplane_min_weight: int = 32
    selector_non_power_two_ratio_min: float = 0.60
    selector_slack_ratio_min: float = 1.15
    selector_max_short_conflict_depth: int = 3
    selector_enable_delay: bool = False
    selector_delay_penalty: float = 0.5
    selector_delta_variance_min: float = 0.35
    selector_delta_variance_weight: float = 0.10

    def with_updates(self, **kwargs) -> "KMergeConfig":
        return replace(self, **kwargs)


DEFAULT_KMERGE_CONFIG = KMergeConfig()


def _safe_reduction_ratio(cost_sep: float, cost_merged: float) -> float:
    if not math.isfinite(cost_sep) or cost_sep <= 1e-9:
        return 0.0
    if not math.isfinite(cost_merged):
        return 0.0
    reduction = cost_sep - cost_merged
    if reduction <= 1e-6:
        return 0.0
    ratio = reduction / max(cost_sep, 1e-9)
    if not math.isfinite(ratio):
        return 0.0
    return float(ratio)


def _discriminator_ratio(
    c1: Sequence[PBConstraintStub],
    c2: Sequence[PBConstraintStub],
    merged: Sequence[PBConstraintStub],
    analysis_config: KMergeConfig,
) -> float:
    analysis_sep_1 = analyze_group(c1, analysis_config)
    analysis_sep_2 = analyze_group(c2, analysis_config)
    analysis_merged = analyze_group(merged, analysis_config)
    return _safe_reduction_ratio(
        analysis_sep_1.total_cost + analysis_sep_2.total_cost,
        analysis_merged.total_cost,
    )


@dataclass(frozen=True)
class KMergeGroupAnalysis:
    basis: tuple[int, ...]
    base_cost: float
    total_cost: float
    area_cost: float
    depth_cost: float
    short_circuit_clause_count: int
    conflict_depth: int | None
    slack_abort: bool
    delta_variance: float


@dataclass(frozen=True)
class KMergeClusterFeatures:
    max_weight: int
    non_power_two_ratio: float
    slack_ratio: float
    conflict_depth: int | None
    delta_variance: float
    positive_weight_count: int


def get_wvc_cost(weights: Sequence[int]) -> float:
    """Weighted Variable Count proxy for SAT complexity."""
    active = sum(1 for w in weights if w > 0)
    if active == 0:
        return 0.0
    max_w = max(weights)
    return float(active) * math.log2(max_w + 1)


def _bitplane_shared_weight(values: Sequence[int]) -> int:
    shared = int(values[0])
    for value in values[1:]:
        shared &= int(value)
    return shared


def _active_count(weights: Sequence[int]) -> int:
    return sum(1 for weight in weights if int(weight) > 0)


def _is_power_of_two(value: int) -> bool:
    value = int(value)
    return value > 0 and (value & (value - 1)) == 0


def get_basis(
    weights_list: Sequence[Sequence[int]],
    config: KMergeConfig | None = None,
) -> list[int]:
    """Calculate the shared basis across a list of aligned weights."""
    if not weights_list:
        return []
    cfg = config or DEFAULT_KMERGE_CONFIG
    n = len(weights_list[0])
    if cfg.basis_mode == "bitplane":
        return [_bitplane_shared_weight([w[i] for w in weights_list]) for i in range(n)]
    return [min(w[i] for w in weights_list) for i in range(n)]


def get_shared_support_ratio(
    constraints: Sequence[PBConstraintStub],
    basis: Sequence[int] | None = None,
    config: KMergeConfig | None = None,
) -> float:
    if not constraints:
        return 0.0
    if basis is None:
        weights_list = [constraint.weights for constraint in constraints]
        basis = get_basis(weights_list, config=config)
    basis_active = _active_count(basis)
    if basis_active == 0:
        return 0.0
    mean_active = sum(_active_count(constraint.weights) for constraint in constraints) / len(constraints)
    if mean_active <= 0.0:
        return 0.0
    return float(basis_active) / float(mean_active)


def _get_area_and_depth(weights: Sequence[int]) -> tuple[float, float]:
    active = sum(1 for w in weights if w > 0)
    if active == 0:
        return 0.0, 0.0
    max_w = max(weights)
    area = float(active) * math.log2(max_w + 1)
    bit_width = math.ceil(math.log2(max_w + 1)) if max_w > 0 else 0
    tree_depth = math.ceil(math.log(active, 1.5)) if active > 1 else 0
    depth = float(tree_depth + bit_width)
    return area, depth


def _estimate_beta(weights_list: Sequence[Sequence[int]], config: KMergeConfig) -> float:
    if not config.use_delay_cost:
        return 0.0
    total_area = 0.0
    total_depth = 0.0
    for weights in weights_list:
        area, depth = _get_area_and_depth(weights)
        total_area += area
        total_depth += depth
    if total_depth <= 0.0:
        return float(config.delay_penalty)
    return (total_area / total_depth) * float(config.delay_penalty)


def get_conflict_depth(weights: Sequence[int], bound: int) -> int | None:
    ordered = sorted((int(w) for w in weights if w > 0), reverse=True)
    total = 0
    for idx, weight in enumerate(ordered, start=1):
        total += weight
        if total > int(bound):
            return idx
    return None


def iter_minimal_violating_subsets(
    weights: Sequence[int],
    bound: int,
    max_size: int,
) -> Iterable[tuple[int, ...]]:
    indexed = [(idx, int(weight)) for idx, weight in enumerate(weights) if weight > 0]
    for size in range(1, max_size + 1):
        for combo in itertools.combinations(indexed, size):
            combo_sum = sum(weight for _, weight in combo)
            if combo_sum <= int(bound):
                continue
            minimal = True
            for drop in range(size):
                reduced_sum = combo_sum - combo[drop][1]
                if reduced_sum > int(bound):
                    minimal = False
                    break
            if minimal:
                yield tuple(idx for idx, _weight in combo)


def get_short_circuit_subsets(
    weights: Sequence[int],
    bound: int,
    max_size: int,
) -> list[tuple[int, ...]]:
    return list(iter_minimal_violating_subsets(weights, bound, max_size))


def _short_circuit_clause_count(weights: Sequence[int], bound: int, max_size: int) -> int:
    return len(get_short_circuit_subsets(weights, bound, max_size))


def analyze_group(
    constraints: Sequence[PBConstraintStub],
    config: KMergeConfig | None = None,
) -> KMergeGroupAnalysis:
    cfg = config or DEFAULT_KMERGE_CONFIG
    if not constraints:
        return KMergeGroupAnalysis(
            basis=(),
            base_cost=0.0,
            total_cost=0.0,
            area_cost=0.0,
            depth_cost=0.0,
            short_circuit_clause_count=0,
            conflict_depth=None,
            slack_abort=False,
            delta_variance=0.0,
        )

    weights_list = [tuple(int(w) for w in c.weights) for c in constraints]
    basis = tuple(get_basis(weights_list, cfg))
    beta = _estimate_beta(weights_list, cfg)

    basis_area, basis_depth = _get_area_and_depth(basis)
    total_area = basis_area
    total_depth = basis_depth
    delta_loads: list[float] = []
    for weights in weights_list:
        delta = [weights[i] - basis[i] for i in range(len(weights))]
        delta_area, delta_depth = _get_area_and_depth(delta)
        total_area += delta_area
        total_depth += delta_depth
        delta_loads.append(sum(delta))

    base_cost = total_area + (beta * total_depth)
    total_cost = base_cost
    short_circuit_clause_count = 0
    conflict_depth = None
    slack_abort = False

    if cfg.use_slack_tripwire and any(c.op == "<=" for c in constraints):
        min_bound = min(int(c.bound) for c in constraints if c.op == "<=")
        max_basis = sum(basis)
        if max_basis > min_bound:
            conflict_depth = get_conflict_depth(basis, min_bound)
            if conflict_depth is not None and conflict_depth >= int(cfg.slack_conflict_depth_abort):
                slack_abort = True
                total_cost = math.inf
            elif (
                conflict_depth is not None
                and cfg.use_short_circuit_penalty
                and conflict_depth > 0
            ):
                short_circuit_clause_count = _short_circuit_clause_count(
                    basis,
                    min_bound,
                    conflict_depth,
                )
                total_cost += (
                    float(cfg.short_circuit_clause_penalty)
                    * float(short_circuit_clause_count)
                )

    delta_variance = 0.0
    if cfg.use_delta_variance_penalty and len(delta_loads) >= 2:
        mean_delta = sum(delta_loads) / len(delta_loads)
        if mean_delta > 0.0:
            delta_variance = statistics.pstdev(delta_loads) / mean_delta
            total_cost *= 1.0 + (float(cfg.delta_variance_weight) * delta_variance)

    return KMergeGroupAnalysis(
        basis=basis,
        base_cost=base_cost,
        total_cost=total_cost,
        area_cost=total_area,
        depth_cost=total_depth,
        short_circuit_clause_count=short_circuit_clause_count,
        conflict_depth=conflict_depth,
        slack_abort=slack_abort,
        delta_variance=delta_variance,
    )


def extract_cluster_features(
    constraints: Sequence[PBConstraintStub],
    config: KMergeConfig | None = None,
) -> KMergeClusterFeatures:
    cfg = config or DEFAULT_KMERGE_CONFIG
    if not constraints:
        return KMergeClusterFeatures(
            max_weight=0,
            non_power_two_ratio=0.0,
            slack_ratio=0.0,
            conflict_depth=None,
            delta_variance=0.0,
            positive_weight_count=0,
        )
    integer_cfg = cfg.with_updates(
        routing_mode="fixed",
        basis_mode="integer",
    )
    analysis = analyze_group(constraints, integer_cfg)
    positive_weights = [int(weight) for c in constraints for weight in c.weights if int(weight) > 0]
    non_power_two_count = sum(1 for weight in positive_weights if not _is_power_of_two(weight))
    positive_count = len(positive_weights)
    max_weight = max(positive_weights, default=0)
    min_bound = min((int(c.bound) for c in constraints if c.op == "<="), default=0)
    slack_ratio = float(sum(analysis.basis)) / float(min_bound) if min_bound > 0 else 0.0
    conflict_depth = get_conflict_depth(analysis.basis, min_bound) if min_bound > 0 else None
    return KMergeClusterFeatures(
        max_weight=max_weight,
        non_power_two_ratio=(float(non_power_two_count) / float(positive_count)) if positive_count else 0.0,
        slack_ratio=slack_ratio,
        conflict_depth=conflict_depth,
        delta_variance=analysis.delta_variance,
        positive_weight_count=positive_count,
    )


def resolve_cluster_config(
    constraints: Sequence[PBConstraintStub],
    config: KMergeConfig | None = None,
) -> KMergeConfig:
    cfg = config or DEFAULT_KMERGE_CONFIG
    if cfg.routing_mode != "hybrid":
        return cfg
    features = extract_cluster_features(constraints, cfg)
    resolved = cfg.with_updates(
        routing_mode="fixed",
        basis_mode="integer",
        use_delay_cost=False,
        delay_penalty=cfg.delay_penalty,
        use_slack_tripwire=False,
        use_short_circuit_penalty=False,
        use_delta_variance_penalty=False,
        delta_variance_weight=cfg.delta_variance_weight,
    )
    if (
        features.max_weight >= int(cfg.selector_bitplane_min_weight)
        and features.non_power_two_ratio >= float(cfg.selector_non_power_two_ratio_min)
    ):
        resolved = resolved.with_updates(basis_mode="bitplane")
    if cfg.selector_enable_delay:
        resolved = resolved.with_updates(
            use_delay_cost=True,
            delay_penalty=float(cfg.selector_delay_penalty),
        )
    if (
        features.slack_ratio >= float(cfg.selector_slack_ratio_min)
        and features.conflict_depth is not None
        and int(features.conflict_depth) <= int(cfg.selector_max_short_conflict_depth)
    ):
        resolved = resolved.with_updates(
            use_slack_tripwire=True,
            use_short_circuit_penalty=True,
        )
    if features.delta_variance >= float(cfg.selector_delta_variance_min):
        resolved = resolved.with_updates(
            use_delta_variance_penalty=True,
            delta_variance_weight=float(cfg.selector_delta_variance_weight),
        )
    return resolved


def get_group_cost(
    weights_list: Sequence[Sequence[int]],
    config: KMergeConfig | None = None,
) -> float:
    stubs = [
        PBConstraintStub(lits=tuple(), weights=tuple(int(w) for w in weights), bound=0, op="<=")
        for weights in weights_list
    ]
    return analyze_group(stubs, config).total_cost


def partition_constraints(
    constraints: Sequence[PBConstraintStub],
    config: KMergeConfig | None = None,
) -> list[list[int]]:
    """
    Greedy agglomerative clustering to partition constraints into basis groups.
    """
    m = len(constraints)
    if m == 0:
        return []
    if m == 1:
        return [[0]]

    cfg = config or DEFAULT_KMERGE_CONFIG
    clusters = [[i] for i in range(m)]
    group_constraint_cache: dict[tuple[int, ...], tuple[PBConstraintStub, ...]] = {}
    analysis_cache: dict[tuple[KMergeConfig, tuple[int, ...]], KMergeGroupAnalysis] = {}

    def _cluster_key(indices: Sequence[int]) -> tuple[int, ...]:
        return tuple(sorted(int(idx) for idx in indices))

    def _group_for_key(cluster_key: tuple[int, ...]) -> tuple[PBConstraintStub, ...]:
        cached_group = group_constraint_cache.get(cluster_key)
        if cached_group is not None:
            return cached_group
        group = tuple(constraints[idx] for idx in cluster_key)
        group_constraint_cache[cluster_key] = group
        return group

    def _analysis_for(mode_cfg: KMergeConfig, cluster_key: tuple[int, ...]) -> KMergeGroupAnalysis:
        cache_key = (mode_cfg, cluster_key)
        cached = analysis_cache.get(cache_key)
        if cached is not None:
            return cached
        analysis = analyze_group(_group_for_key(cluster_key), mode_cfg)
        analysis_cache[cache_key] = analysis
        return analysis

    if str(cfg.discriminator_mode) != "legacy_reduction":
        base_cfg = cfg.with_updates(
            routing_mode="fixed",
            basis_mode="integer",
            use_delay_cost=False,
            use_slack_tripwire=False,
            use_short_circuit_penalty=False,
            use_delta_variance_penalty=False,
        )
        delta_cfg = base_cfg.with_updates(
            use_delta_variance_penalty=True,
            delta_variance_weight=0.25,
        )
        slack_cfg = base_cfg.with_updates(
            use_slack_tripwire=True,
            use_short_circuit_penalty=True,
            short_circuit_clause_penalty=1.0,
            slack_conflict_depth_abort=4,
        )
    else:
        base_cfg = delta_cfg = slack_cfg = cfg

    def _pair_reduction_and_score(i: int, j: int) -> tuple[float, float] | None:
        key_1 = _cluster_key(clusters[i])
        key_2 = _cluster_key(clusters[j])
        merged_key = _cluster_key(clusters[i] + clusters[j])
        analysis_merged = _analysis_for(cfg, merged_key)

        if str(cfg.discriminator_mode) == "legacy_reduction":
            analysis_sep_1 = _analysis_for(cfg, key_1)
            analysis_sep_2 = _analysis_for(cfg, key_2)
            reduction_ratio = _safe_reduction_ratio(
                analysis_sep_1.total_cost + analysis_sep_2.total_cost,
                analysis_merged.total_cost,
            )
        else:
            baseline_sep = _analysis_for(base_cfg, key_1).total_cost + _analysis_for(base_cfg, key_2).total_cost
            baseline_merged = _analysis_for(base_cfg, merged_key).total_cost
            baseline_ratio = _safe_reduction_ratio(baseline_sep, baseline_merged)

            delta_sep = _analysis_for(delta_cfg, key_1).total_cost + _analysis_for(delta_cfg, key_2).total_cost
            delta_merged = _analysis_for(delta_cfg, merged_key).total_cost
            delta_ratio = _safe_reduction_ratio(delta_sep, delta_merged)

            slack_sep = _analysis_for(slack_cfg, key_1).total_cost + _analysis_for(slack_cfg, key_2).total_cost
            slack_merged = _analysis_for(slack_cfg, merged_key).total_cost
            slack_ratio = _safe_reduction_ratio(slack_sep, slack_merged)

            reduction_ratio = (
                float(cfg.combo_baseline_weight) * baseline_ratio
                + float(cfg.combo_delta_weight) * delta_ratio
                + float(cfg.combo_slack_weight) * slack_ratio
            )
            if reduction_ratio < float(cfg.combo_threshold):
                return None

        if reduction_ratio <= 1e-9:
            return None
        shared_support_ratio = get_shared_support_ratio(
            _group_for_key(merged_key),
            basis=analysis_merged.basis,
            config=cfg,
        )
        if reduction_ratio < float(cfg.min_merge_reduction_ratio):
            return None
        if shared_support_ratio < float(cfg.min_shared_support_ratio):
            return None

        score = reduction_ratio
        if str(cfg.extraction_architecture).upper() == "C":
            merged_size = max(len(merged_key), 1)
            score = reduction_ratio / float(merged_size)
        return reduction_ratio, score

    arch = str(cfg.extraction_architecture).upper()
    while True:
        if arch == "B":
            candidates: list[tuple[float, float, int, int]] = []
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    result = _pair_reduction_and_score(i, j)
                    if result is None:
                        continue
                    reduction_ratio, score = result
                    candidates.append((score, reduction_ratio, i, j))
            if not candidates:
                break
            candidates.sort(reverse=True)
            used: set[int] = set()
            merges: list[tuple[int, int]] = []
            for _score, _red, i, j in candidates:
                if i in used or j in used:
                    continue
                merges.append((i, j))
                used.add(i)
                used.add(j)
            if not merges:
                break
            consumed = {idx for pair in merges for idx in pair}
            new_clusters = [clusters[idx] for idx in range(len(clusters)) if idx not in consumed]
            for i, j in merges:
                new_clusters.append(clusters[i] + clusters[j])
            clusters = new_clusters
            continue

        best_score = 0.0
        best_pair = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                result = _pair_reduction_and_score(i, j)
                if result is None:
                    continue
                _reduction_ratio, score = result
                if score > best_score:
                    best_score = score
                    best_pair = (i, j)

        if best_pair is None or best_score <= 1e-9:
            break

        i, j = best_pair
        merged = clusters[i] + clusters[j]
        new_clusters = [clusters[k] for k in range(len(clusters)) if k != i and k != j]
        new_clusters.append(merged)
        clusters = new_clusters

    return clusters
