import pytest

from hermax.internal.maxsat_cli_parse import parse_maxsat_cli_output


@pytest.mark.parametrize("model_line", ["v 1 -1 0", "v 1 1 0"])
@pytest.mark.xfail(
    strict=True,
    reason="MaxSAT CLI parsing silently collapses duplicate or contradictory model literals",
)
def test_cli_parser_rejects_duplicate_model_literals(model_line):
    with pytest.raises(ValueError, match="duplicate|contradictory"):
        parse_maxsat_cli_output(
            f"s OPTIMUM FOUND\n{model_line}\n",
            num_vars=1,
        )


@pytest.mark.xfail(
    strict=True,
    reason="MaxSAT CLI parsing classifies UNKNOWN before a later model line and loses the feasible-incumbent status",
)
def test_cli_parser_unknown_with_later_model_is_interrupted_sat():
    status, cost, model = parse_maxsat_cli_output(
        "s UNKNOWN\nv 1 -2 0\n",
        num_vars=2,
    )

    assert status.name == "INTERRUPTED_SAT"
    assert cost is None
    assert model == [1, -2]


@pytest.mark.xfail(
    strict=True,
    reason="MaxSAT CLI parser silently ignores malformed tokens in model lines",
)
def test_cli_parser_rejects_malformed_model_token():
    with pytest.raises(ValueError, match="invalid|malformed"):
        parse_maxsat_cli_output(
            "s OPTIMUM FOUND\nv 1 not-a-literal 0\n",
            num_vars=1,
        )
