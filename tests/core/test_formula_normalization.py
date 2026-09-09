import pytest

from hermax.core.utils import normalize_wcnf_formula


class _OptiLogWCNF:
    __module__ = "optilog.formula"

    def __init__(self):
        self.hard_clauses = [[1, -2]]
        self.soft_clauses = [(3, [2, 3])]

    def max_var(self):
        return 3


def test_optilog_wcnf_conversion_is_independent_of_source_lists():
    source = _OptiLogWCNF()
    converted = normalize_wcnf_formula(source)

    converted.hard[0][0] = -1
    converted.soft[0][0] = -2

    assert source.hard_clauses == [[1, -2]]
    assert source.soft_clauses == [(3, [2, 3])]


def test_optilog_wcnf_conversion_supports_one_shot_soft_clause_iterables():
    OptiLikeWCNF = type("WCNF", (), {"__module__": "optilog.formulas"})

    obj = OptiLikeWCNF()
    obj.hard_clauses = [[1]]
    obj.soft_clauses = ((weight, [literal]) for weight, literal in [(2, 2), (3, 3)])
    obj.max_var = lambda: 3

    converted = normalize_wcnf_formula(obj)

    assert converted.soft == [[2], [3]]
    assert converted.wght == [2, 3]


def test_optilog_wcnf_conversion_materializes_one_shot_hard_clause_iterables():
    OptiLikeWCNF = type("WCNF", (), {"__module__": "optilog.formulas"})

    obj = OptiLikeWCNF()
    obj.hard_clauses = ((literal,) for literal in [1, -2])
    obj.soft_clauses = []
    obj.max_var = lambda: 2

    converted = normalize_wcnf_formula(obj)

    assert converted.hard == [[1], [-2]]
