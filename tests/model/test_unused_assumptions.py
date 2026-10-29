import pytest

from hermax.model import Model


@pytest.mark.parametrize("route", ["auto", "one_shot", "live", "tier_incremental", "tier_stratified"])
@pytest.mark.parametrize("positive", [False, True])
def test_assumptions_can_reference_an_otherwise_unused_boolean(route, positive):
    m = Model()
    cost, unused = m.bool("cost"), m.bool("unused")
    kwargs = {}
    if route.startswith("tier_"):
        m.tier_obj.add(cost)
        kwargs["lex_strategy"] = route.removeprefix("tier_")
    else:
        m.obj += cost
        if route == "one_shot":
            kwargs["incremental"] = False
        elif route == "live":
            kwargs["backend"] = "maxsat"
    for value in [positive, not positive]:
        result = m.solve(assumptions=[unused if value else ~unused], **kwargs)
        assert result.ok and result.cost == 0
        assert result[cost] is False and result[unused] is value

