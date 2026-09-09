import itertools

import pytest

from hermax.internal.pb_normalize import normalize_signed_terms


def _value(lit: int, assignment: dict[int, bool]) -> int:
    value = assignment[abs(lit)]
    return int(value if lit > 0 else not value)


def _evaluate(terms, constant, assignment) -> int:
    return constant + sum(weight * _value(lit, assignment) for weight, lit in terms)


@pytest.mark.parametrize(
    ("weights", "lits", "constant"),
    [
        ([-3, 2], [1, 2], -4),
        ([3, -2], [-1, 2], 7),
        ([-1, -2, 4], [1, -1, 2], 0),
        ([0, 5, -5], [1, 2, -2], 3),
    ],
)
def test_normalize_signed_terms_preserves_value_for_every_assignment(weights, lits, constant):
    original = list(zip(weights, lits))
    normalized = normalize_signed_terms(original, constant, flip=lambda lit: -lit)

    assert all(weight > 0 for weight, _lit in normalized.terms)
    assert all(isinstance(weight, int) for weight, _lit in normalized.terms)

    for values in itertools.product((False, True), repeat=2):
        assignment = {1: values[0], 2: values[1]}
        assert _evaluate(original, constant, assignment) == _evaluate(
            normalized.terms, normalized.constant, assignment
        )


def test_normalize_signed_terms_is_exhaustively_equivalent_for_two_dimacs_literals():
    for weights in itertools.product(range(-2, 3), repeat=2):
        for lits in itertools.product((1, -1, 2, -2), repeat=2):
            for constant in range(-2, 3):
                original = list(zip(weights, lits))
                normalized = normalize_signed_terms(original, constant, flip=lambda lit: -lit)
                for values in itertools.product((False, True), repeat=2):
                    assignment = {1: values[0], 2: values[1]}
                    assert _evaluate(original, constant, assignment) == _evaluate(
                        normalized.terms, normalized.constant, assignment
                    )


def test_normalize_signed_terms_flips_coalesces_and_keeps_first_seen_order():
    normalized = normalize_signed_terms(
        [(2, 1), (-3, -1), (5, 2), (0, 3)],
        constant=11,
        flip=lambda lit: -lit,
    )

    # -3 * ~x is 3 * x - 3, so both x terms coalesce.
    assert normalized.terms == ((5, 1), (5, 2))
    assert normalized.constant == 8


def test_normalize_signed_terms_works_for_non_dimacs_items_via_key_and_flip():
    flipped = {"x": "~x", "~x": "x", "y": "~y", "~y": "y"}
    normalized = normalize_signed_terms(
        [(-2, "x"), (1, "~x"), (3, "y")],
        constant=0,
        flip=flipped.__getitem__,
        key=str,
    )

    assert normalized.terms == ((3, "~x"), (3, "y"))
    assert normalized.constant == -2


@pytest.mark.parametrize("constant", [1.0, True])
def test_normalize_signed_terms_rejects_non_integral_constants(constant):
    with pytest.raises(ValueError, match="constant must be an integer"):
        normalize_signed_terms([], constant, flip=lambda item: item)


@pytest.mark.parametrize("weight", [1.0, True])
def test_normalize_signed_terms_rejects_non_integral_coefficients(weight):
    with pytest.raises(ValueError, match="integer coefficients.*integers"):
        normalize_signed_terms([(weight, "x")], 0, flip=lambda item: item)
