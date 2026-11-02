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

    converted.hard.append([-1])
    converted.soft = [[-2]]
    source.hard_clauses[0][0] = -3
    assert converted.hard[0] == (1, -2)
    source.hard_clauses[0][0] = 1

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


def test_cgss_requires_explicit_optional_encoder_without_importing_pysat_helpers():
    from hermax.core.cgss_py.vendor.rc2_wce import RC2WCE
    from hermax.formula import WCNF
    with pytest.raises(NotImplementedError, match='encoder'):
        RC2WCE(WCNF(), structure_sharing_opts=(0, 100))


def test_internal_pysat_imports_are_limited_to_sat_bindings_and_explicit_conversion():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / 'hermax'
    forbidden = []
    for path in root.rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('pysat'):
                if node.module == 'pysat.solvers':
                    continue
                if path == root / 'formula.py' and node.module == 'pysat' and [n.name for n in node.names] == ['formula']:
                    continue
                forbidden.append((str(path.relative_to(root)), node.lineno, node.module))
    assert forbidden == []
