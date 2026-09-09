from hermax.internal.model_check import check_model, model_satisfies_hard_clauses
import pytest


def test_model_check_rejects_contradictory_literal_assignments():
    model = [1, -1]

    assert not model_satisfies_hard_clauses([[1], [-1]], model)
    assert not check_model(model, [[1]], [], reported_cost=0).hards_ok


def test_model_check_rejects_duplicate_literal_assignments():
    assert not model_satisfies_hard_clauses([[1]], [1, 1])


@pytest.mark.parametrize("bad_model", [[1.5], [True], ["1"]])
def test_model_check_rejects_non_integer_model_literals(bad_model):
    assert not model_satisfies_hard_clauses([[1]], bad_model)


@pytest.mark.parametrize("bad_literal", [1.5, True, "1"])
def test_model_check_rejects_non_integer_hard_literals(bad_literal):
    with pytest.raises((TypeError, ValueError)):
        model_satisfies_hard_clauses([[bad_literal]], [1])


@pytest.mark.parametrize("bad_literal", [1.5, True, "1"])
def test_model_check_rejects_non_integer_soft_literals(bad_literal):
    with pytest.raises((TypeError, ValueError)):
        check_model([1], [], [([bad_literal], 1)], reported_cost=0)


@pytest.mark.parametrize("bad_weight", [1.5, True, "1"])
def test_model_check_rejects_non_integer_soft_weights(bad_weight):
    with pytest.raises((TypeError, ValueError)):
        check_model([1], [], [([1], bad_weight)], reported_cost=0)


def test_model_check_rejects_non_integer_reported_cost():
    with pytest.raises((TypeError, ValueError)):
        check_model([1], [], [], reported_cost=0.5)
