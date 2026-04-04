import math

from hermax.internal.kmerge import (
    KMergeConfig,
    PBConstraintStub,
    analyze_group,
    extract_cluster_features,
    get_basis,
    get_shared_support_ratio,
    partition_constraints,
    resolve_cluster_config,
)


def test_bitplane_basis_extracts_shared_powers_of_two():
    weights = [(10, 10), (6, 6)]
    assert get_basis(weights, KMergeConfig(basis_mode="integer")) == [6, 6]
    assert get_basis(weights, KMergeConfig(basis_mode="bitplane")) == [2, 2]


def test_delay_cost_increases_group_cost():
    stubs = [
        PBConstraintStub(lits=(1, 2, 3, 4), weights=(15, 15, 15, 15), bound=30, op="<="),
        PBConstraintStub(lits=(1, 2, 3, 4), weights=(14, 14, 14, 14), bound=30, op="<="),
    ]
    plain = analyze_group(stubs, KMergeConfig())
    delayed = analyze_group(stubs, KMergeConfig(use_delay_cost=True, delay_penalty=2.0))
    assert delayed.depth_cost > 0.0
    assert delayed.total_cost > plain.total_cost


def test_slack_tripwire_aborts_high_conflict_depth_merge():
    stubs = [
        PBConstraintStub(lits=(1, 2, 3, 4), weights=(1, 1, 1, 1), bound=3, op="<="),
        PBConstraintStub(lits=(1, 2, 3, 4), weights=(1, 1, 1, 1), bound=8, op="<="),
    ]
    analysis = analyze_group(
        stubs,
        KMergeConfig(use_slack_tripwire=True, slack_conflict_depth_abort=4),
    )
    assert analysis.slack_abort
    assert math.isinf(analysis.total_cost)


def test_short_circuit_penalty_counts_minimal_conflicts():
    stubs = [
        PBConstraintStub(lits=(1, 2, 3, 4), weights=(4, 3, 3, 2), bound=5, op="<="),
    ]
    analysis = analyze_group(
        stubs,
        KMergeConfig(
            use_slack_tripwire=True,
            use_short_circuit_penalty=True,
            slack_conflict_depth_abort=4,
        ),
    )
    assert analysis.conflict_depth == 2
    assert analysis.short_circuit_clause_count == 4
    assert analysis.total_cost > analysis.base_cost


def test_delta_variance_penalty_increases_asymmetric_group_cost():
    stubs = [
        PBConstraintStub(lits=(1, 2), weights=(10, 10), bound=10, op="<="),
        PBConstraintStub(lits=(1, 2), weights=(10, 10), bound=10, op="<="),
        PBConstraintStub(lits=(1, 2), weights=(20, 20), bound=20, op="<="),
    ]
    plain = analyze_group(stubs, KMergeConfig())
    penalized = analyze_group(
        stubs,
        KMergeConfig(use_delta_variance_penalty=True, delta_variance_weight=1.0),
    )
    assert penalized.delta_variance > 0.0
    assert penalized.total_cost > plain.total_cost


def test_hybrid_selector_chooses_bitplane_for_carry_heavy_cluster():
    stubs = [
        PBConstraintStub(lits=(1, 2), weights=(10, 10), bound=16, op="<="),
        PBConstraintStub(lits=(1, 2), weights=(6, 6), bound=12, op="<="),
    ]
    config = KMergeConfig(
        routing_mode="hybrid",
        selector_bitplane_min_weight=8,
        selector_non_power_two_ratio_min=0.5,
    )
    resolved = resolve_cluster_config(stubs, config)
    assert resolved.basis_mode == "bitplane"


def test_hybrid_selector_chooses_slack_for_tight_bound_cluster():
    stubs = [
        PBConstraintStub(lits=(1, 2, 3, 4, 5), weights=(4, 3, 3, 2, 0), bound=5, op="<="),
        PBConstraintStub(lits=(1, 2, 3, 4, 5), weights=(4, 3, 3, 2, 5), bound=12, op="<="),
    ]
    config = KMergeConfig(
        routing_mode="hybrid",
        selector_slack_ratio_min=1.1,
        selector_max_short_conflict_depth=3,
    )
    features = extract_cluster_features(stubs, config)
    resolved = resolve_cluster_config(stubs, config)
    assert features.slack_ratio > 1.1
    assert resolved.use_slack_tripwire
    assert resolved.use_short_circuit_penalty


def test_shared_support_ratio_tracks_basis_coverage():
    stubs = [
        PBConstraintStub(lits=(1, 2, 3), weights=(8, 4, 0), bound=8, op="<="),
        PBConstraintStub(lits=(1, 2, 3), weights=(8, 0, 4), bound=8, op="<="),
    ]
    ratio = get_shared_support_ratio(stubs, basis=(8, 0, 0))
    assert 0.0 < ratio < 1.0


def test_partition_constraints_respects_conservative_merge_gates():
    stubs = [
        PBConstraintStub(lits=(1, 2, 3), weights=(10, 0, 1), bound=10, op="<="),
        PBConstraintStub(lits=(1, 2, 3), weights=(10, 1, 0), bound=10, op="<="),
    ]
    parts = partition_constraints(
        stubs,
        KMergeConfig(
            min_merge_reduction_ratio=0.5,
            min_shared_support_ratio=0.8,
        ),
    )
    assert parts == [[0], [1]]
