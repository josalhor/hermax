from __future__ import annotations

import random
import statistics
import time
from dataclasses import dataclass

from hermax.internal.kmerge import KMergeConfig
from hermax.model import Model


@dataclass(frozen=True)
class Scenario:
    name: str
    family: str
    n_vars: int
    weights: tuple[tuple[int, ...], ...]
    bounds: tuple[int, ...]


def _make_overlap_masks(rng: random.Random, n_vars: int, n_constraints: int, active: int, overlap: float) -> list[list[int]]:
    shared = list(range(min(n_vars, max(2, int(active * overlap)))))
    masks: list[list[int]] = []
    for idx in range(n_constraints):
        pool = list(shared)
        while len(pool) < active:
            candidate = rng.randrange(n_vars)
            if candidate not in pool:
                pool.append(candidate)
        rng.shuffle(pool)
        masks.append(sorted(pool[:active]))
        if idx % 2 == 1 and len(shared) < n_vars:
            shared.append(len(shared))
    return masks


def _make_hidden_assignment(rng: random.Random, n_vars: int, density: float) -> list[int]:
    return [1 if rng.random() < density else 0 for _ in range(n_vars)]


def _build_weight_row(n_vars: int, active_idx: list[int], generator) -> tuple[int, ...]:
    row = [0] * n_vars
    for idx in active_idx:
        row[idx] = int(generator(idx))
    return tuple(row)


def _sat_bound(weights: tuple[int, ...], hidden_assignment: list[int], slack: int) -> int:
    lhs = sum(weights[idx] for idx, bit in enumerate(hidden_assignment) if bit)
    return max(1, lhs + slack)


def build_random_scenarios(seed: int, per_family: int) -> list[Scenario]:
    rng = random.Random(seed)
    scenarios: list[Scenario] = []

    for idx in range(per_family):
        n_vars = 20 + (idx % 3) * 8
        n_constraints = 4 + (idx % 3)
        active = min(n_vars, 10 + (idx % 4) * 3)
        hidden = _make_hidden_assignment(rng, n_vars, 0.35)

        masks = _make_overlap_masks(rng, n_vars, n_constraints, active, overlap=0.65)
        weights = tuple(
            _build_weight_row(n_vars, mask, lambda _j: 6 + rng.randint(0, 5))
            for mask in masks
        )
        bounds = tuple(_sat_bound(row, hidden, slack=5 + idx % 5) for row in weights)
        scenarios.append(Scenario(f"correlated_{idx}", "correlated", n_vars, weights, bounds))

        masks = _make_overlap_masks(rng, n_vars, n_constraints, active, overlap=0.8)
        weights = tuple(
            _build_weight_row(n_vars, mask, lambda _j: rng.choice([6, 10, 12, 18, 20, 24, 40]))
            for mask in masks
        )
        bounds = tuple(_sat_bound(row, hidden, slack=3 + idx % 4) for row in weights)
        scenarios.append(Scenario(f"carry_{idx}", "carry", n_vars, weights, bounds))

        masks = _make_overlap_masks(rng, n_vars, n_constraints, active, overlap=0.75)
        base_row = _build_weight_row(n_vars, masks[0], lambda _j: rng.choice([2, 3, 4, 5, 7, 9]))
        weights_list = [base_row]
        for mask_pos in range(1, n_constraints):
            row = list(base_row)
            for col in range(n_vars):
                if col not in masks[mask_pos]:
                    row[col] = 0
            if mask_pos == n_constraints - 1:
                extra_idx = next((col for col in masks[mask_pos] if row[col] == 0), masks[mask_pos][0])
                row[extra_idx] = 11
            weights_list.append(tuple(row))
        weights = tuple(weights_list)
        bounds = [_sat_bound(weights[0], hidden, slack=1 + idx % 3)]
        for row in weights[1:]:
            bounds.append(_sat_bound(row, hidden, slack=8 + idx % 5))
        scenarios.append(Scenario(f"slack_{idx}", "slack", n_vars, weights, tuple(bounds)))

        masks = _make_overlap_masks(rng, n_vars, n_constraints, active, overlap=0.7)
        anchor = _build_weight_row(n_vars, masks[0], lambda _j: 8 + rng.randint(0, 4))
        weights_list = [anchor]
        for scale in range(1, n_constraints):
            weights_list.append(
                tuple(
                    int(value * (1 + scale)) if value else 0
                    for value in anchor
                )
            )
        weights = tuple(weights_list)
        bounds = tuple(_sat_bound(row, hidden, slack=6 + idx % 4) for row in weights)
        scenarios.append(Scenario(f"delta_{idx}", "delta", n_vars, weights, bounds))

        masks = _make_overlap_masks(rng, n_vars, n_constraints + 1, active, overlap=0.45)
        weights = tuple(
            _build_weight_row(
                n_vars,
                mask,
                lambda _j: rng.choice([1, 2, 3, 5, 8, 13, 21, 34]),
            )
            for mask in masks
        )
        bounds = tuple(_sat_bound(row, hidden, slack=4 + idx % 6) for row in weights)
        scenarios.append(Scenario(f"mixed_{idx}", "mixed", n_vars, weights, bounds))

    return scenarios


def run_case(scenario: Scenario, preset_name: str, merge_enabled: bool, config: KMergeConfig, repeats: int) -> dict[str, float | int | str]:
    commit_ms_values = []
    solve_ms_values = []
    clause_counts = []
    literal_counts = []
    statuses = []

    for _ in range(repeats):
        model = Model()
        model.set_merge_pb_optimization(merge_enabled)
        model.set_kmerge_config(config)
        xs = [model.bool(f"x{i}") for i in range(scenario.n_vars)]

        for weights, bound in zip(scenario.weights, scenario.bounds):
            expr = sum(int(weight) * xs[idx] for idx, weight in enumerate(weights) if weight)
            model &= expr <= int(bound)

        t0 = time.perf_counter()
        model._commit_pb()
        t1 = time.perf_counter()
        res = model.solve(sat_solver_name="cadical195", incremental=False)
        t2 = time.perf_counter()

        commit_ms_values.append((t1 - t0) * 1000.0)
        solve_ms_values.append((t2 - t1) * 1000.0)
        clause_counts.append(len(model._hard))
        literal_counts.append(sum(len(clause) for clause in model._hard))
        statuses.append("sat" if res.ok else "unsat")

    return {
        "scenario": scenario.name,
        "family": scenario.family,
        "preset": preset_name,
        "merge_enabled": int(merge_enabled),
        "commit_ms": statistics.mean(commit_ms_values),
        "solve_ms": statistics.mean(solve_ms_values),
        "clauses": statistics.mean(clause_counts),
        "literals": statistics.mean(literal_counts),
        "status": max(set(statuses), key=statuses.count),
    }


def family_metric_matrix(rows: list[dict[str, float | int | str]], presets: list[str], metric: str) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        family = str(row["family"])
        preset = str(row["preset"])
        grouped.setdefault(family, {}).setdefault(preset, []).append(float(row[metric]))
    return {
        family: {
            preset: statistics.mean(grouped.get(family, {}).get(preset, [float("nan")]))
            for preset in presets
        }
        for family in sorted(grouped)
    }
