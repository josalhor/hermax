import pytest

from hermax.model import Model


@pytest.mark.parametrize("kind", ["upper_bound", "lower_bound"])
@pytest.mark.parametrize("api", ["model", "vector"])
def test_singleton_bounds_keep_their_one_sided_meaning(kind, api):
    for source, chosen in [(1, 3), (4, 2), (0, 0), (5, 5)]:
        m = Model()
        x = m.int("x", 0, 5)
        bound = getattr(m, kind)([x], name="bound") if api == "model" else getattr(m.vector([x]), kind)(name="bound")
        m &= x == source
        m &= bound == chosen
        result = m.solve()
        expected = chosen >= source if kind == "upper_bound" else chosen <= source
        assert result.ok is expected
        if expected:
            assert result[x] == source and result[bound] == chosen
        assert (bound if api == "model" else bound._realized).name == "bound"
