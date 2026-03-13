from __future__ import annotations


def _pairwise_mutex_map(groups):
    out: dict[int, set[int]] = {}
    for group in groups:
        for lit in group:
            out.setdefault(int(lit), set())
        for i, li in enumerate(group):
            for lj in group[i + 1 :]:
                out[int(li)].add(int(lj))
                out[int(lj)].add(int(li))
    return out


def _assert_partition_is_valid(partition, lits, candidate_groups):
    flat = [lit for group in partition for lit in group]
    assert sorted(flat) == sorted(lits)
    assert len(flat) == len(set(flat))
    mutex = _pairwise_mutex_map(candidate_groups)
    for group in partition:
        for i, li in enumerate(group):
            for lj in group[i + 1 :]:
                assert int(lj) in mutex.get(int(li), set())


def test_baseline_paper_matches_first_fit_known_case(structuredpb_module) -> None:
    lits = [1, 2, 3, 4, 5, 6]
    weights = [5, 5, 5, 4, 4, 4]
    amo_groups = [[1, 2, 4], [2, 3, 5], [1, 3, 6], [4, 5], [5, 6]]

    baseline = structuredpb_module.choose_overlap_partition(
        lits,
        weights,
        amo_groups=amo_groups,
        eo_groups=[],
        policy=structuredpb_module.OverlapPolicy.baseline_paper,
    )

    assert baseline == [[1, 2, 3], [4, 5], [6]]


def test_dynamic_future_known_case_expected_partition_and_better_amo_cap(structuredpb_module) -> None:
    lits = [1, 2, 3, 4, 5, 6]
    weights = [5, 5, 5, 4, 4, 4]
    amo_groups = [[1, 2, 4], [2, 3, 5], [1, 3, 6], [4, 5], [5, 6]]

    baseline = structuredpb_module.choose_overlap_partition(
        lits,
        weights,
        amo_groups=amo_groups,
        eo_groups=[],
        policy=structuredpb_module.OverlapPolicy.baseline_paper,
    )
    improved = structuredpb_module.choose_overlap_partition(
        lits,
        weights,
        amo_groups=amo_groups,
        eo_groups=[],
        policy=structuredpb_module.OverlapPolicy.paper_best_fit_dynamic_future,
    )

    assert improved == [[1, 2, 4], [3, 5, 6]]
    assert structuredpb_module.amo_upper_bound(weights, improved, lits=lits) < structuredpb_module.amo_upper_bound(
        weights, baseline, lits=lits
    )


def test_dynamic_future_returns_valid_partition_on_deterministic_overlap_cases(structuredpb_module) -> None:
    cases = [
        {
            "lits": [1, 2, 3, 4, 5],
            "weights": [9, 8, 7, 2, 1],
            "amo": [[1, 2, 3], [2, 3, 4], [3, 4, 5]],
            "eo": [[1, 5]],
        },
        {
            "lits": [1, 2, 3, 4, 5, 6],
            "weights": [10, 9, 8, 2, 2, 2],
            "amo": [[1, 4], [1, 5], [2, 5], [2, 6], [3, 4], [3, 6]],
            "eo": [],
        },
    ]
    for case in cases:
        partition = structuredpb_module.choose_overlap_partition(
            case["lits"],
            case["weights"],
            amo_groups=case["amo"],
            eo_groups=case["eo"],
            policy=structuredpb_module.OverlapPolicy.paper_best_fit_dynamic_future,
        )
        _assert_partition_is_valid(partition, case["lits"], [*case["amo"], *case["eo"]])


def test_dynamic_future_exact_partition_on_secondary_cases(structuredpb_module) -> None:
    case_a = structuredpb_module.choose_overlap_partition(
        [1, 2, 3, 4, 5],
        [9, 8, 7, 2, 1],
        amo_groups=[[1, 2, 3], [2, 3, 4], [3, 4, 5]],
        eo_groups=[[1, 5]],
        policy=structuredpb_module.OverlapPolicy.paper_best_fit_dynamic_future,
    )
    case_b = structuredpb_module.choose_overlap_partition(
        [1, 2, 3, 4, 5, 6],
        [10, 9, 8, 2, 2, 2],
        amo_groups=[[1, 4], [1, 5], [2, 5], [2, 6], [3, 4], [3, 6]],
        eo_groups=[],
        policy=structuredpb_module.OverlapPolicy.paper_best_fit_dynamic_future,
    )

    assert case_a == [[1, 5], [2, 3, 4]]
    assert case_b == [[1, 5], [2, 6], [3, 4]]
