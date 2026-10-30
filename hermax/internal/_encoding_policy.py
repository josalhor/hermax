"""Shared limits for integer arithmetic encodings."""

STATE_LIMIT = 20_000
CLAUSE_LIMIT = 40_000


def exceeds_limits(*, clauses=0, states=0) -> bool:
    # Zero disables a limit, matching the native encoder interface.
    return (CLAUSE_LIMIT > 0 and clauses > CLAUSE_LIMIT) or (
        STATE_LIMIT > 0 and states > STATE_LIMIT
    )
