"""Lazy integer thresholds and their reserved ranges of literal IDs."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, overload

from .expressions import Literal

if TYPE_CHECKING:
    from .core import Model
    from .variables import IntVar


class ThresholdLiterals(Sequence[Literal]):
    """Create and cache a literal pair only when its threshold is requested."""

    __slots__ = ("model", "name", "start", "count", "_cache")

    def __init__(self, model: Model, name: str, start: int, count: int):
        self.model, self.name, self.start, self.count = model, name, start, count
        self._cache: dict[int, Literal] = {}

    def __len__(self) -> int:
        return self.count

    @overload
    def __getitem__(self, index: int) -> Literal: ...

    @overload
    def __getitem__(self, index: slice) -> list[Literal]: ...

    def __getitem__(self, index: int | slice) -> Literal | list[Literal]:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self.count))]
        if not isinstance(index, int):
            raise TypeError("threshold indices must be integers or slices")
        if index < 0:
            index += self.count
        if index < 0 or index >= self.count:
            raise IndexError("threshold index out of range")
        lit = self._cache.get(index)
        if lit is None:
            lit = Literal(self.model, self.start + index, f"{self.name}<=#{index}", True)
            negative = Literal(self.model, lit.id, lit.name, False)
            lit._link_negation(negative)
            negative._link_negation(lit)
            self._cache[index] = lit
        return lit


class ThresholdOwners(Mapping[int, tuple["IntVar", int]]):
    """Index reserved ID ranges by integer owner without allocating per ID."""

    __slots__ = ("_starts", "_owners", "_count")

    def __init__(self) -> None:
        self._starts: list[int] = []
        self._owners: list[IntVar] = []
        self._count = 0

    def add(self, owner: IntVar) -> None:
        bits = owner._threshold_lits
        if not isinstance(bits, ThresholdLiterals) or not bits:
            raise ValueError("expected a nonempty integer threshold range")
        if self._owners:
            previous = self._owners[-1]._threshold_lits
            assert isinstance(previous, ThresholdLiterals)
            if bits.start < previous.start + len(previous):
                raise ValueError("overlapping threshold IDs")
        self._starts.append(bits.start)
        self._owners.append(owner)
        self._count += len(bits)

    def __getitem__(self, key: int) -> tuple[IntVar, int]:
        if isinstance(key, int):
            index = bisect_right(self._starts, key) - 1
            if index >= 0:
                owner = self._owners[index]
                offset = key - self._starts[index]
                if offset < len(owner._threshold_lits):
                    return owner, offset
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, int):
            return False
        index = bisect_right(self._starts, key) - 1
        return index >= 0 and key - self._starts[index] < len(self._owners[index]._threshold_lits)

    def __iter__(self) -> Iterator[int]:
        for start, owner in zip(self._starts, self._owners):
            yield from range(start, start + len(owner._threshold_lits))

    def __len__(self) -> int:
        return self._count
