from __future__ import annotations

import io

from hermax.model import Model


def test_debug_level_zero_emits_no_output():
    m = Model()
    buf = io.StringIO()
    m.set_debug(0, stream=buf)
    a = m.bool("a")
    m &= a
    assert buf.getvalue() == ""


def test_debug_level_one_shows_delta_events():
    m = Model()
    buf = io.StringIO()
    m.set_debug(1, stream=buf)
    a = m.bool("a")
    m &= a
    m.obj[3] += a
    out = buf.getvalue()
    assert "add_hard count=" in out
    assert "add_soft hard_delta=" in out
    assert "route_deltas mode=" in out


def test_debug_level_two_shows_normalized_pb_and_encoder_path():
    m = Model()
    buf = io.StringIO()
    m.set_debug(2, stream=buf)
    a = m.bool("a")
    b = m.bool("b")
    m &= (a + b <= 1)
    out = buf.getvalue()
    assert "pb_normalize" in out
    assert "encode path=card" in out


def test_debug_level_two_shows_cache_hit_on_repeat_pb_compare():
    m = Model()
    buf = io.StringIO()
    m.set_debug(2, stream=buf)
    a = m.bool("a")
    b = m.bool("b")
    m &= (2 * a + 3 * b <= 3)
    m &= (2 * a + 3 * b <= 3)
    out = buf.getvalue()
    assert "pb_cache miss" in out
    assert "pb_cache hit" in out


def test_debug_level_three_includes_clause_dumps():
    m = Model()
    buf = io.StringIO()
    m.set_debug(3, stream=buf)
    a = m.bool("a")
    m &= a
    m.obj[2] += ~a
    out = buf.getvalue()
    assert "hard[0]=" in out
    assert "soft+[0]" in out

