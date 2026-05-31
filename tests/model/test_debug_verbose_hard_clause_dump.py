from __future__ import annotations

import io

from hermax.model import Model


def test_debug_verbose_dumps_hard_clauses_for_immediate_pb_compile_path():
    m = Model()
    out = io.StringIO()
    m.set_debug(3, stream=out)
    x = m.int("x", 0, 5)
    y = m.int("y", 0, 5)
    # This shape is compiled immediately via int fastpath (not deferred PB queue).
    m &= (x + y == 3)
    s = out.getvalue()
    assert "add_hard count=" in s
    assert "hard[0]=" in s
