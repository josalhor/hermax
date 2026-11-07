"""Hermax formulas with native clause storage.

Clause collections support append/extend and return independent clause values.
Use :meth:`to_pysat` for an explicit, independent PySAT representation.
"""
from __future__ import annotations

from copy import deepcopy
import math
from operator import index

from hermax.internal._clause_storage import ClauseStorage

__all__ = ["load_formula"]


def _integer(value, name, *, minimum=0):
    if isinstance(value, bool):
        raise TypeError(f'{name} must be an integer.')
    value = index(value)
    if value < minimum:
        raise ValueError(f'{name} must be at least {minimum}.')
    return value


def _validate_soft_weight(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError('Soft weight must be numeric.')
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Soft weight must be finite and positive.')
    if isinstance(value, float) and not value.is_integer():
        raise ValueError('Soft weights must be integer-valued in WCNF.')
    return value


def _constraint(value):
    if len(value) not in (2, 3):
        raise ValueError('A native constraint needs literals, a bound, and optional weights.')
    lits = list(ClauseStorage([value[0]])[0])
    if isinstance(value[1], bool):
        raise TypeError("Constraint bound must be an integer.")
    bound = index(value[1])
    if len(value) == 2:
        return [lits, bound]
    weights = [_integer(w, 'Constraint weight') for w in value[2]]
    if len(lits) != len(weights):
        raise ValueError('Constraint literals and weights must have equal length.')
    return [lits, bound, weights]


class _Formula:
    _weighted = False
    _plus = False

    def __init__(self):
        self._nv = 0
        self.comments = []
        self._constraints = []

    @property
    def nv(self):
        collections = (self.hard, self.soft) if self._weighted else (self.clauses,)
        top = max((c.max_var for c in collections), default=0)
        for constraint in self._constraints:
            top = max(top, max(map(abs, constraint[0]), default=0))
        return max(self._nv, top)

    @nv.setter
    def nv(self, value):
        self._nv = _integer(value, 'Variable count')

    def validate(self):
        """Check metadata after direct collection edits, without changing this formula."""
        if self._weighted:
            if len(self.soft) != len(self.wght):
                raise ValueError('Soft clauses and weights must have equal length.')
            for weight in self.wght:
                _validate_soft_weight(weight)
        for constraint in self._constraints:
            _constraint(constraint)
        return self

    def copy(self):
        self.validate()
        return type(self).from_formula(self)

    @classmethod
    def from_pysat(cls, formula):
        """Copy a PySAT-shaped formula; no PySAT import or identity check needed."""
        return cls.from_formula(formula)

    @classmethod
    def from_formula(cls, formula):
        """Copy an equivalent formula, preserving declared variables and constraints."""
        result = cls()
        source_weighted = hasattr(formula, 'hard') and hasattr(formula, 'soft')
        if source_weighted != result._weighted:
            raise TypeError('Use weighted()/unweighted() to change formula kind explicitly.')
        constraints = getattr(formula, 'atms' if source_weighted else 'atmosts', ())
        if constraints and not result._plus:
            raise ValueError('Native constraints require a Plus formula.')
        if source_weighted:
            result.hard = formula.hard
            result.soft = formula.soft
            result.wght = [_validate_soft_weight(w) for w in formula.wght]
            if len(result.soft) != len(result.wght):
                raise ValueError('Soft clauses and weights must have equal length.')
            result.topw = getattr(formula, 'topw', sum(result.wght) + 1)
        else:
            result.clauses = formula.clauses
        result._constraints = [_constraint(c) for c in constraints]
        result.comments = list(getattr(formula, 'comments', ()))
        result.nv = getattr(formula, 'nv', 0)
        return result

    def to_pysat(self):
        """Return an independent PySAT formula of the corresponding kind."""
        self.validate()
        from pysat import formula as pysat_formula
        kind = ('WCNF' if self._weighted else 'CNF') + ('Plus' if self._plus else '')
        result = getattr(pysat_formula, kind)()
        result.nv = self.nv
        result.comments = list(self.comments)
        if self._weighted:
            if len(self.soft) != len(self.wght):
                raise ValueError('Soft clauses and weights must have equal length.')
            result.hard = self.hard.to_lists()
            result.soft = self.soft.to_lists()
            result.wght = list(self.wght)
            result.topw = self.topw
            if self._plus:
                result.atms = deepcopy(self._constraints)
        else:
            result.clauses = self.clauses.to_lists()
            if self._plus:
                result.atmosts = deepcopy(self._constraints)
        return result

    def _append_constraint(self, constraint):
        if not self._plus:
            raise ValueError('Native constraints require a Plus formula.')
        self._constraints.append(_constraint(constraint))


    def _load_source(self, from_file, from_fp, from_string):
        sources = sum(value is not None for value in (from_file, from_fp, from_string))
        if sources > 1:
            raise ValueError('Specify only one formula source.')
        if from_file is not None:
            self.from_file(from_file)
        elif from_fp is not None:
            self.from_fp(from_fp)
        elif from_string is not None:
            self.from_string(from_string)

    def from_string(self, text):
        """Replace this formula using the native DIMACS/Plus parser."""
        from hermax.internal._clauses import parse_formula
        if isinstance(text, bytes):
            text = text.decode('utf-8')
        hard, soft, weights, constraints, nv, top, comments = parse_formula(
            text, self._weighted, self._plus)
        if self._weighted:
            self.hard = ClauseStorage._wrap(hard)
            self.soft = ClauseStorage._wrap(soft)
            self.wght = weights
            self._topw = top if top is not None else sum(weights) + 1
        else:
            self.clauses = ClauseStorage._wrap(hard)
        self._constraints = constraints
        self.comments = comments
        self.nv = nv

    @staticmethod
    def _open(path, mode):
        import os
        path = os.fspath(path)
        if path.endswith('.gz'):
            from gzip import open
        elif path.endswith('.bz2'):
            from bz2 import open
        elif path.endswith(('.xz', '.lzma')):
            from lzma import open
        else:
            from builtins import open
        return open(path, mode, encoding='utf-8')

    def from_file(self, path):
        with self._open(path, 'rt') as stream:
            self.from_fp(stream)

    def from_fp(self, stream):
        self.from_string(stream.read())

    def to_dimacs(self):
        self.validate()
        topw = self.topw if self._weighted else None
        kind = ('wcnf' if self._weighted else 'cnf') + ('+' if self._plus else '')
        if self._weighted:
            if len(self.soft) != len(self.wght):
                raise ValueError('Soft clauses and weights must have equal length.')
            count = len(self.hard) + len(self.soft) + len(self._constraints)
            header = f'p {kind} {self.nv} {count} {topw}'
        else:
            count = len(self.clauses) + len(self._constraints)
            header = f'p {kind} {self.nv} {count}'
        lines = [*self.comments, header]
        def clause_line(row, prefix=''):
            return prefix + ' '.join(map(str, (*row, 0)))
        if self._weighted:
            lines.extend(clause_line(row, f'{topw} ') for row in self.hard)
            lines.extend(clause_line(row, f'{_integer(w, "Soft weight", minimum=1)} ')
                         for row, w in zip(self.soft, self.wght))
        else:
            lines.extend(clause_line(row) for row in self.clauses)
        for constraint in self._constraints:
            lits, bound, *weights = _constraint(constraint)
            prefix = f'{topw} ' if self._weighted else ''
            if weights:
                body = 'w ' + ' '.join(f'{w}*{lit}' for w, lit in zip(weights[0], lits))
            else:
                body = ' '.join(map(str, lits))
            lines.append(f'{prefix}{body} <= {bound}')
        return '\n'.join(lines) + '\n'

    def to_fp(self, stream):
        stream.write(self.to_dimacs())

    def to_file(self, path):
        with self._open(path, 'wt') as stream:
            self.to_fp(stream)


class CNF(_Formula):
    """A conjunction of clauses stored in a native copy-on-write container."""
    def __init__(self, *, from_clauses=None, from_file=None, from_fp=None, from_string=None):
        super().__init__()
        if from_clauses is not None and any(s is not None for s in (from_file, from_fp, from_string)):
            raise ValueError("Specify only one formula source.")
        self.clauses = () if from_clauses is None else from_clauses
        self._load_source(from_file, from_fp, from_string)

    @property
    def clauses(self):
        return self._clauses

    @clauses.setter
    def clauses(self, value):
        self._clauses = ClauseStorage(value)

    def append(self, clause, *, is_atmost=False):
        if is_atmost:
            self._append_constraint(clause)
        else:
            self.clauses.append(clause)

    def extend(self, clauses):
        self.clauses.extend(clauses)

    def __iter__(self):
        return iter(self.clauses)

    def weighted(self):
        result = WCNFPlus() if self._plus else WCNF()
        result.soft = self.clauses
        result.wght = [1] * len(self.clauses)
        result._constraints = deepcopy(self._constraints)
        result.comments = list(self.comments)
        result.nv = self.nv
        return result


class CNFPlus(CNF):
    """CNF with explicitly stored native cardinality/PB constraints."""
    _plus = True

    @property
    def atmosts(self):
        return self._constraints

    @atmosts.setter
    def atmosts(self, value):
        self._constraints = [_constraint(c) for c in value]


class WCNF(_Formula):
    """Hard clauses and ordered weighted soft clauses.

    Formula terms preserve input order. Solver loading follows the selected
    interface's semantics, including IPAMIR soft-unit replacement.
    """
    _weighted = True

    def __init__(self, *, from_file=None, from_fp=None, from_string=None):
        super().__init__()
        self.hard = ()
        self.soft = ()
        self.wght = []
        self._topw = 1
        self._load_source(from_file, from_fp, from_string)

    @property
    def hard(self):
        return self._hard

    @hard.setter
    def hard(self, value):
        self._hard = ClauseStorage(value)

    @property
    def soft(self):
        return self._soft

    @soft.setter
    def soft(self, value):
        self._soft = ClauseStorage(value)

    @property
    def topw(self):
        return max(self._topw, sum(self.wght) + 1)

    @topw.setter
    def topw(self, value):
        self._topw = _integer(value, 'Hard weight', minimum=1)

    def append(self, clause, weight=None, *, is_atmost=False):
        if is_atmost:
            if weight is not None:
                raise ValueError('Native constraints must be hard.')
            self._append_constraint(clause)
        elif weight is None:
            self.hard.append(clause)
        else:
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                raise TypeError('Soft weight must be numeric.')
            if not math.isfinite(weight) or weight <= 0:
                raise ValueError('Soft weight must be finite and positive.')
            self.soft.append(clause)
            self.wght.append(weight)

    def extend(self, clauses, weights=None):
        if weights is None:
            self.hard.extend(clauses)
        else:
            # Validate both collections before mutation; never silently zip-truncate.
            rows = ClauseStorage(clauses)
            weights = [_validate_soft_weight(w) for w in weights]
            if len(rows) != len(weights):
                raise ValueError('Soft clauses and weights must have equal length.')
            self.soft.extend(rows)
            self.wght.extend(weights)

    def unweighted(self):
        result = CNFPlus() if self._plus else CNF()
        result.clauses = self.hard + self.soft
        result._constraints = deepcopy(self._constraints)
        result.comments = list(self.comments)
        result.nv = self.nv
        return result


class WCNFPlus(WCNF):
    """WCNF with hard native cardinality/PB constraints."""
    _plus = True

    @property
    def atms(self):
        return self._constraints

    @atms.setter
    def atms(self, value):
        self._constraints = [_constraint(c) for c in value]


def load_formula(path):
    """Load a CNF/WCNF file, optionally compressed, for use with Hermax solvers.

    Interchange with supported PySAT formula shapes is best effort. The concrete
    return type and storage are implementation details.
    """
    import os
    path = os.fsdecode(path)
    with _Formula._open(path, 'rt') as stream:
        text = stream.read()
    first = next((line.split() for line in text.splitlines()
                  if line.strip() and not line.lstrip().startswith('c')), [])
    name = path.lower()
    for compression in ('.gz', '.bz2', '.xz', '.lzma'):
        if name.endswith(compression):
            name = name[:-len(compression)]
            break
    if first and first[0] == 'p':
        if len(first) < 2 or first[1] not in ('cnf', 'cnf+', 'wcnf', 'wcnf+'):
            raise ValueError('Unsupported formula header.')
        weighted = first[1].startswith('wcnf')
    elif first and first[0] == 'h':
        weighted = True
    elif name.endswith(('.wcnf', '.wcnf+')):
        weighted = True
    elif not first or name.endswith(('.cnf', '.cnf+')):
        weighted = False
    else:
        raise ValueError('Headerless input requires a .cnf or .wcnf file extension.')
    # Plus parsing preserves native constraints even when the header omits '+'.
    return (WCNFPlus if weighted else CNFPlus)(from_string=text)
