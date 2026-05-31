from __future__ import annotations

import random

from hermax.encoder import PBCompiler
from hermax.model import Model


def _build_model(constraints: list[tuple[list[int], int]], *, merge_enabled: bool) -> tuple[Model, list]:
    m = Model()
    m.set_merge_pb_optimization(bool(merge_enabled))
    xs = [m.bool(f"x{i}") for i in range(5)]
    for weights, bound in constraints:
        expr = sum(weights[i] * xs[i] for i in range(5))
        m &= expr <= bound
    return m, xs


def test_model_class_default_disables_merge_pb_optimization():
    assert Model.MERGE_PB_OPTIMIZATION_ENABLED is False


def test_merge_enabled_matches_disabled_results_randomized():
    rnd = random.Random(73)
    for _ in range(12):
        constraints: list[tuple[list[int], int]] = []
        for _j in range(4):
            weights = [rnd.randint(1, 8) for _k in range(5)]
            bound = rnd.randint(4, 16)
            constraints.append((weights, bound))

        m_off, x_off = _build_model(constraints, merge_enabled=False)
        m_on, x_on = _build_model(constraints, merge_enabled=True)

        for mask in range(1 << 5):
            ass_off = [x_off[i] if ((mask >> i) & 1) else ~x_off[i] for i in range(5)]
            ass_on = [x_on[i] if ((mask >> i) & 1) else ~x_on[i] for i in range(5)]
            r_off = m_off.solve(assumptions=ass_off)
            r_on = m_on.solve(assumptions=ass_on)
            assert bool(r_off.ok) == bool(r_on.ok), (constraints, mask)


def test_merge_batch_path_is_reached_when_enabled(monkeypatch):
    calls: list[tuple[int, bool]] = []
    original = PBCompiler.compile_batch_with_options

    def _wrapped(*, items, amo_groups, eo_groups, top_id, merge_pb_optimization, kmerge_config):
        calls.append((len(items), bool(merge_pb_optimization)))
        return original(
            items=items,
            amo_groups=amo_groups,
            eo_groups=eo_groups,
            top_id=top_id,
            merge_pb_optimization=merge_pb_optimization,
            kmerge_config=kmerge_config,
        )

    monkeypatch.setattr(PBCompiler, "compile_batch_with_options", _wrapped)

    constraints = [
        ([7, 3, 5, 2, 6], 11),
        ([6, 4, 5, 3, 7], 12),
        ([5, 6, 3, 4, 8], 11),
    ]
    m, _xs = _build_model(constraints, merge_enabled=True)
    m.solve()

    assert any(n > 1 and flag for n, flag in calls), calls
