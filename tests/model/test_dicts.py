import pytest

from hermax.model import BoolDict, EnumDict, IntDict, Model


def _solve_ok(m: Model):
    r = m.solve()
    assert r.ok, f"expected satisfiable/optimal model, got status={r.status}"
    return r


def test_typed_dict_construction_decode_and_registry_collisions():
    m = Model()
    keys = ["r1", "r2"]
    flags = m.bool_dict("flags", keys=keys)
    speed = m.int_dict("speed", keys=keys, lb=1, ub=4)
    color = m.enum_dict("color", keys=keys, choices=["red", "green"], nullable=True)

    assert isinstance(flags, BoolDict)
    assert isinstance(speed, IntDict)
    assert isinstance(color, EnumDict)

    m &= flags["r1"]
    m &= ~flags["r2"]
    m &= (speed["r1"] == 2)
    m &= (speed["r2"] == 3)
    m &= (color["r1"] == "red")
    # leave color["r2"] nullable/None

    r = _solve_ok(m)
    assert r[flags] == {"r1": True, "r2": False}
    assert r[speed] == {"r1": 2, "r2": 3}
    assert r[color]["r1"] == "red"
    assert r[color]["r2"] is None

    with pytest.raises(ValueError, match="already registered"):
        m.bool_dict("flags", keys=keys)
