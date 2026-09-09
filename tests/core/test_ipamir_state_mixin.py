import pytest

from hermax.core.ipamir_solver_interface import SolveStatus
from hermax.core.ipamir_state_mixin import IPAMIRStateMixin


def _state() -> IPAMIRStateMixin:
    state = IPAMIRStateMixin()
    state._init_ipamir_state()
    return state


@pytest.mark.parametrize("model", ([1, -1], [0, 1]))
def test_set_result_rejects_malformed_models(model):
    with pytest.raises(ValueError, match="model"):
        _state()._set_result(
            status=SolveStatus.OPTIMUM,
            model=model,
            num_vars=2,
        )


def test_set_result_pads_missing_variable_ids_not_list_positions():
    state = _state()
    state._set_result(
        status=SolveStatus.OPTIMUM,
        model=[1, 3],
        num_vars=3,
    )
    assert state.get_model() == [1, -2, 3]


@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_set_result_rejects_non_integer_model_literals(raw_literal):
    with pytest.raises((TypeError, ValueError)):
        _state()._set_result(
            status=SolveStatus.OPTIMUM,
            model=[raw_literal],
            num_vars=1,
        )


def test_set_result_is_atomic_when_replacement_model_is_invalid():
    state = _state()
    state._set_result(
        status=SolveStatus.OPTIMUM,
        model=[1],
        cost=7,
        num_vars=1,
    )

    with pytest.raises(ValueError, match="invalid literal"):
        state._set_result(
            status=SolveStatus.UNSAT,
            model=[2],
            cost=None,
            num_vars=1,
        )

    assert state.get_status() is SolveStatus.OPTIMUM
    assert state.get_model() == [1]
    assert state.get_cost() == 7


@pytest.mark.parametrize("raw_cost", [1.5, True, "7"])
def test_set_result_rejects_non_integer_costs(raw_cost):
    with pytest.raises((TypeError, ValueError)):
        _state()._set_result(
            status=SolveStatus.OPTIMUM,
            model=[1],
            cost=raw_cost,
            num_vars=1,
        )


def test_set_result_is_atomic_when_replacement_cost_is_invalid():
    state = _state()
    state._set_result(
        status=SolveStatus.OPTIMUM,
        model=[1],
        cost=7,
        num_vars=1,
    )

    with pytest.raises((TypeError, ValueError)):
        state._set_result(
            status=SolveStatus.OPTIMUM,
            model=[-1],
            cost="not-an-integer",
            num_vars=1,
        )

    assert state.get_status() is SolveStatus.OPTIMUM
    assert state.get_model() == [1]
    assert state.get_cost() == 7


@pytest.mark.parametrize("raw_literal", [1.5, True, "1"])
def test_val_rejects_non_integer_literals(raw_literal):
    state = _state()
    state._set_result(status=SolveStatus.OPTIMUM, model=[1], num_vars=1)

    with pytest.raises((TypeError, ValueError)):
        state.val(raw_literal)


@pytest.mark.parametrize("raw_status", [30.0, False, "OPTIMUM"])
def test_set_result_rejects_malformed_status_values(raw_status):
    with pytest.raises((TypeError, ValueError)):
        _state()._set_result(status=raw_status, model=[1], cost=0, num_vars=1)
