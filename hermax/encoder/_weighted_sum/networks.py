"""Shared exact sorting gates and implication-based simplification."""
from collections.abc import Sequence

from .common import CNFBuilder, Signal, negate


def comparator_count(size: int) -> int:
    """Upper bound for the insertion or odd-even network selected by sort()."""
    width = 1 << (max(1, size) - 1).bit_length()
    stages = width.bit_length() - 1
    insertion = size * (size - 1) // 2
    odd_even = width * stages * (stages - 1) // 4 + width - 1
    return min(insertion, odd_even)


class ComparatorNetwork:
    """Exact gates with sharing and locally known implications."""

    def __init__(self, cnf: CNFBuilder):
        self.cnf = cnf
        self.gates = {}
        self.implies = set()

    def conjunction(self, a: Signal, b: Signal) -> Signal:
        if a is False or b is False or a == negate(b):
            return False
        if a is True:
            return b
        if b is True or a == b or (a, b) in self.implies:
            return a
        if (b, a) in self.implies:
            return b
        key = tuple(sorted((a, b)))
        if key not in self.gates:
            out = self.cnf.fresh()
            self.cnf.add(-out, a)
            self.cnf.add(-out, b)
            self.cnf.add(out, negate(a), negate(b))
            self.gates[key] = out
            self.implies.update(((out, a), (out, b), (negate(a), -out), (negate(b), -out)))
        return self.gates[key]

    def compare(self, a: Signal, b: Signal) -> tuple[Signal, Signal]:
        high = negate(self.conjunction(negate(a), negate(b)))
        low = self.conjunction(a, b)
        # These follow from the comparator itself. Reusing the relation is
        # substitution, not deletion of an unproved gate constraint.
        if type(low) is int and type(high) is int:
            self.implies.add((low, high))
            self.implies.add((negate(high), negate(low)))
        return high, low

    def sort(self, inputs: Sequence[Signal]) -> list[Signal]:
        size = len(inputs)
        width = 1 << (max(1, size) - 1).bit_length()
        stages = width.bit_length() - 1
        if size * (size - 1) // 2 < width * stages * (stages - 1) // 4 + width - 1:
            outputs = []
            for literal in inputs:
                carry, following = literal, []
                for previous in outputs:
                    high, carry = self.compare(previous, carry)
                    following.append(high)
                outputs = following + [carry]
            return outputs
        outputs = list(inputs) + [False] * (width - size)

        def merge(start, length, stride):
            step = 2 * stride
            if step < length:
                merge(start, length, step)
                merge(start + stride, length, step)
                for i in range(start + stride, start + length - stride, step):
                    outputs[i], outputs[i + stride] = self.compare(outputs[i], outputs[i + stride])
            else:
                outputs[start], outputs[start + stride] = self.compare(outputs[start], outputs[start + stride])

        length = 2
        while length <= width:
            for start in range(0, width, length):
                merge(start, length, 1)
            length *= 2
        return outputs[:size]

