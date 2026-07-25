"""Shared validation and deadline helpers for solver time limits."""

from __future__ import annotations

import math
import time
from typing import Optional


def validate_time_limit(time_limit: object) -> Optional[float]:
    """Return a validated time limit in seconds, or ``None``.

    Public solve APIs deliberately accept only finite positive values.  A zero
    budget is ambiguous (unlimited versus immediately expired), so callers must
    use ``None`` to disable a per-call limit.
    """
    if time_limit is None:
        return None
    if isinstance(time_limit, bool) or not isinstance(time_limit, (int, float)):
        raise TypeError("time_limit must be a finite positive number of seconds or None.")
    value = float(time_limit)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("time_limit must be a finite positive number of seconds.")
    return value


class Deadline:
    """Monotonic per-call deadline used by cooperative solver callbacks."""

    __slots__ = ("_deadline",)

    def __init__(self, time_limit: float):
        self._deadline = time.monotonic() + float(time_limit)

    def expired(self) -> bool:
        return time.monotonic() >= self._deadline

    def callback(self) -> int:
        return 1 if self.expired() else 0
