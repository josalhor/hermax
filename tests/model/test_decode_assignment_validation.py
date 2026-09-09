import pytest

from hermax.model import Model


@pytest.mark.parametrize("polarity", [1, -1])
def test_decode_model_rejects_duplicate_raw_literals(polarity):
    model = Model()
    atom = model.bool("a")
    literal = polarity * atom.id

    with pytest.raises(ValueError, match="duplicate"):
        model.decode_model([literal, literal])


@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_decode_model_rejects_non_integer_literals(raw_literal):
    with pytest.raises((TypeError, ValueError)):
        Model().decode_model([raw_literal])


def test_decode_model_rejects_foreign_lookup_objects():
    model = Model()
    local = model.bool("local")
    foreign = Model().bool("foreign")

    decoded = model.decode_model([local.id])

    with pytest.raises(ValueError, match="different model|belong"):
        decoded[foreign]
