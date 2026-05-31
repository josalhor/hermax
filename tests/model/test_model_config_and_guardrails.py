from __future__ import annotations

import io

import pytest

from hermax.internal.kmerge import KMergeConfig
from hermax.model import Clause, Model


class _FlushBoom(io.StringIO):
    def flush(self):
        raise ValueError("flush fail")


def test_set_debug_rejects_invalid_levels():
    m = Model()
    with pytest.raises(ValueError, match="non-negative integer"):
        m.set_debug(-1)
    with pytest.raises(ValueError, match="non-negative integer"):
        m.set_debug(1.5)  # type: ignore[arg-type]


def test_debug_flush_failure_is_swallowed():
    m = Model()
    s = _FlushBoom()
    m.set_debug(1, stream=s)
    m &= Clause(m, [m.bool("a")])


def test_set_kmerge_config_supports_replace_and_kwargs_update():
    m = Model()
    base = m._kmerge_config
    m.set_kmerge_config(min_mean_term_len_for_merge=9.0, safe_min_cluster_size_for_merge=5)
    assert m._kmerge_config.min_mean_term_len_for_merge == 9.0
    assert m._kmerge_config.safe_min_cluster_size_for_merge == 5
    assert m._kmerge_config is not base

    custom = KMergeConfig(routing_mode="bestfit", basis_mode="bitplane")
    m.set_kmerge_config(custom)
    assert m._kmerge_config is custom


def test_safe_close_backend_ignores_missing_and_raising_close():
    class _NoClose:
        pass

    class _BoomClose:
        def close(self):
            raise RuntimeError("boom")

    Model._safe_close_backend(_NoClose())
    Model._safe_close_backend(_BoomClose())


def test_objective_set_rejects_cross_model_expression():
    m1 = Model()
    m2 = Model()
    a2 = m2.bool("a2")
    with pytest.raises(ValueError, match="different models"):
        m1.obj.set(a2, weight=1)


def test_objective_add_rejects_cross_model_expression():
    m1 = Model()
    m2 = Model()
    a1 = m1.bool("a1")
    a2 = m2.bool("a2")
    m1.obj.set(a1, weight=1)
    with pytest.raises(ValueError, match="different models"):
        m1.obj.add(a2, weight=1)
