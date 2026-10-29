"""Private storage for DIMACS clauses."""

from pysat.formula import CNF, WCNF

from hermax.internal._clauses import Storage


class ClauseStorage:
    __slots__ = ("_storage",)

    def __init__(self, clauses=()):
        source = clauses._storage if isinstance(clauses, ClauseStorage) else clauses
        self._storage = Storage(source)

    @classmethod
    def _wrap(cls, storage):
        result = cls.__new__(cls)
        result._storage = storage
        return result

    def __len__(self):
        return len(self._storage)

    def __iter__(self):
        return iter(self._storage)

    def __getitem__(self, index):
        return self._storage[index]

    def __delitem__(self, index):
        del self._storage[index]

    def __eq__(self, other):
        if isinstance(other, ClauseStorage):
            other = list(other)
        return list(self) == other

    def __add__(self, other):
        if not isinstance(other, ClauseStorage):
            return NotImplemented
        return self._wrap(self._storage + other._storage)

    def append(self, clause):
        self._storage.append(clause)

    def extend(self, clauses):
        source = clauses._storage if isinstance(clauses, ClauseStorage) else clauses
        self._storage.extend(source)

    def with_literal(self, literal):
        return self._wrap(self._storage.with_literal(literal))

    def iter_from(self, first):
        return self._storage.iter_from(first)

    def to_lists(self):
        return self._storage.to_lists()

    @property
    def max_var(self):
        return self._storage.max_var


def to_cnf(clauses):
    result = CNF()
    result.clauses, result.nv = clauses._storage.export()
    return result


def to_wcnf(clauses):
    result = WCNF()
    result.hard, result.nv = clauses._storage.export()
    return result
