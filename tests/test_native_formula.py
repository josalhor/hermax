"""Formula ownership and interoperation contracts (PySAT is only a reference)."""
import subprocess
import sys

import pytest
from pysat.formula import CNF as PyCNF, WCNFPlus as PyWCNFPlus

from hermax.formula import CNF, CNFPlus, WCNF, WCNFPlus


def test_formula_import_does_not_import_pysat():
    subprocess.run([sys.executable, '-c', '''
import sys
from hermax.formula import WCNF
f = WCNF()
f.append([1], weight=3)
assert not any(n == 'pysat' or n.startswith('pysat.') for n in sys.modules)
'''], check=True)


def test_clause_storage_tracks_variables_and_does_not_expose_mutable_rows():
    f = CNF(from_clauses=[[1, -3], []])
    f.clauses.append([7])
    assert f.nv == 7
    with pytest.raises(AttributeError):
        f.clauses[0].append(99)
    assert f.clauses[0] == (1, -3)
    f.nv = 12
    del f.clauses[-1]
    assert f.nv == 12


def test_formula_copy_is_independent():
    f = WCNFPlus()
    f.append([1], weight=2)
    f.append([[1, 2], 1], is_atmost=True)
    g = f.copy()
    g.soft.append([3])
    g.wght.append(4)
    g.atms[0][0].append(4)
    assert len(f.soft) == 1
    assert f.wght == [2]
    assert f.atms == [[[1, 2], 1]]


def test_wcnf_fractional_weights_are_consistent_across_append_extend_and_copy():
    f = WCNF()
    f.append([1], weight=0.5)
    f.extend([[2]], [0.25])
    assert f.validate() is f
    assert f.copy().wght == [0.5, 0.25]
    with pytest.raises(ValueError, match="DIMACS WCNF serialization requires integer"):
        f.to_dimacs()


def test_pysat_roundtrip_preserves_plus_constraints_and_is_independent():
    p = PyWCNFPlus()
    p.append([-1])
    p.append([1, 2], weight=2**70)
    p.append([[1, -2], 3, [2, 4]], is_atmost=True)
    p.nv = 10
    f = WCNFPlus.from_pysat(p)
    assert f.nv == 10
    assert f.hard == p.hard
    assert f.soft == p.soft
    assert f.wght == p.wght
    assert f.atms == p.atms
    q = f.to_pysat()
    assert isinstance(q, PyWCNFPlus)
    assert q.atms == p.atms
    q.hard[0].append(4)
    assert f.hard[0] == (-1,)


def test_structural_input_needs_no_pysat_identity():
    from types import SimpleNamespace
    f = CNF.from_formula(SimpleNamespace(clauses=[[1]], nv=5, comments=['c hello']))
    assert f.nv == 5
    assert f.to_pysat().clauses == [[1]]
    assert isinstance(f.to_pysat(), PyCNF)


def test_plain_conversion_cannot_drop_native_constraints():
    f = CNFPlus()
    f.append([[1, 2], 1], is_atmost=True)
    with pytest.raises(ValueError, match='constraint'):
        CNF.from_formula(f)


@pytest.mark.parametrize('cls', [CNF, CNFPlus, WCNF, WCNFPlus])
def test_empty_clause_and_declared_variables_survive_copy(cls):
    f = cls()
    f.append([])
    f.nv = 8
    g = f.copy()
    assert g.nv == 8
    assert (g.hard if isinstance(g, WCNF) else g.clauses) == [[]]


@pytest.mark.parametrize('cls,text', [
    (CNF, 'c test\np cnf 8 2\n1\n-2 0 0\n'),
    (WCNF, 'p wcnf 8 2 10\n10 -1 0\n3 1 2 0\n'),
    (WCNF, 'h -1 0\n3 1 2 0\n'),
    (CNFPlus, 'p cnf+ 8 2\n1 0\nw 2*1 4*-2 >= 3\n'),
    (WCNFPlus, 'p wcnf+ 8 2 10\n3 1 0\n10 1 -2 <= 1\n'),
])
def test_native_parser_roundtrip(cls, text):
    f = cls(from_string=text)
    g = cls(from_string=f.to_dimacs())
    assert g.nv == f.nv
    assert g.comments == f.comments
    if isinstance(f, WCNF):
        assert g.hard == f.hard
        assert g.soft == f.soft
        assert g.wght == f.wght
    else:
        assert g.clauses == f.clauses
    assert g._constraints == f._constraints


def test_file_io_preserves_unused_vars_and_arbitrary_integer_weights(tmp_path):
    f = WCNFPlus()
    f.nv = 12
    f.append([], weight=2**80)
    f.append([[1, 2], 1], is_atmost=True)
    for suffix in ('.wcnf', '.wcnf.gz', '.wcnf.bz2', '.wcnf.xz'):
        path = tmp_path / ('test' + suffix)
        f.to_file(path)
        g = WCNFPlus(from_file=path)
        assert g.nv == 12
        assert g.soft == [[]]
        assert g.wght == [2**80]
        assert g.atms == f.atms


@pytest.mark.parametrize('text', ['p cnf 1 1\n1', 'p cnf 1 1\n1 nope 0', 'p cnf 1 1\n2 0'])
def test_native_parser_rejects_invalid_cnf(text):
    with pytest.raises(ValueError):
        CNF(from_string=text)


def test_encoder_outputs_share_formula_contract_and_convert_explicitly():
    from hermax.encoder.card import CardEnc
    from hermax.encoder._packed import CardEnc as PackedCard
    for encoder in (CardEnc, PackedCard):
        f = encoder.atmost([1, 2, 3], bound=1)
        assert isinstance(f, CNFPlus)
        assert f.to_pysat().clauses == f.clauses
        g = f.copy()
        g.append([8])
        assert g.nv == 8
        assert f.nv < 8


def test_rc2_variable_counter_is_private_and_synchronizes_with_totalizers():
    import hermax.formula as formula
    from hermax.core.rc2.rc2 import _VariableCounter
    pool = _VariableCounter(start_from=4)
    assert pool.id() == 4
    pool.top = 8
    assert pool.id() == 9
    assert not hasattr(formula, 'IDPool')
    assert formula.__all__ == ['load_formula']


def test_native_extraction_keeps_native_hard_collection():
    from hermax.core.utils import extract_wcnf_data
    f = WCNF()
    f.append([1, 2])
    f.append([-1], weight=3)
    data = extract_wcnf_data(f)
    assert data.hard is f.hard
    assert list(data.soft) == [((-1,), 3)]


@pytest.mark.parametrize('text', ['p cnf 2 2\n1 0\n', 'p cnf 2 0\n1 0\n'])
def test_native_parser_rejects_header_count_mismatch(text):
    with pytest.raises(ValueError, match='count'):
        CNF(from_string=text)


def test_parse_failure_preserves_existing_formula():
    f = WCNF(from_string='h 1 0\n3 -1 0\n')
    with pytest.raises(ValueError):
        f.from_string('h 2 0\nnot_a_weight 1 0\n')
    assert f.hard == [[1]]
    assert f.soft == [[-1]]
    assert f.wght == [3]


def test_external_tuple_clauses_keep_their_explicit_weights():
    from types import SimpleNamespace
    from hermax.core.utils import extract_wcnf_data
    f = SimpleNamespace(hard=[], soft=[(1,), (1, 2)], wght=[7, 9], nv=2)
    data = extract_wcnf_data(f)
    assert data.soft == [([1], 7), ([1, 2], 9)]


@pytest.mark.parametrize('weight', [True, '2', -1, 0, float('nan'), float('inf')])
def test_formula_boundaries_reject_mutated_invalid_weights(weight):
    from hermax.core.utils import extract_wcnf_data
    f = WCNF()
    f.append([1], weight=2)
    f.wght[0] = weight
    for boundary in (f.validate, f.to_pysat, f.copy, lambda: extract_wcnf_data(f)):
        with pytest.raises((TypeError, ValueError)):
            boundary()


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('backend_name', ['rc2', 'cgss'])
def test_local_maxsat_engines_accept_nonunit_formulas_without_mutating_input(native, backend_name):
    if backend_name == 'rc2':
        from hermax.core.rc2.rc2 import RC2 as Backend
    else:
        from hermax.core.cgss_py.vendor.rc2_wce import RC2WCE as Backend
    from pysat.formula import WCNF as PyWCNF
    formula = WCNF() if native else PyWCNF()
    formula.append([-1])
    formula.append([-2])
    formula.append([1, 2], weight=5)
    before = [tuple(row) for row in formula.soft]
    backend = Backend(formula)
    try:
        assert backend.compute() is not None
        assert backend.cost == 5
        assert [tuple(row) for row in formula.soft] == before
    finally:
        backend.delete()


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('backend_name', ['coretrail', 'rc2', 'uwr', 'cgss', 'cgss_pmres'])
def test_formula_handoff_preserves_ipamir_updates_assumptions_and_nonunit_costs(native, backend_name):
    from hermax.core import CoreTrailSolver, RC2Reentrant, UWrMaxSATSolver
    from hermax.core.cgss_py.cgss_solver import CGSSSolver, CGSSPMRESSolver
    from pysat.formula import WCNF as PyWCNF
    backends = dict(coretrail=CoreTrailSolver, rc2=RC2Reentrant, uwr=UWrMaxSATSolver,
                    cgss=CGSSSolver, cgss_pmres=CGSSPMRESSolver)
    backend = backends[backend_name]
    if hasattr(backend, 'is_available') and not backend.is_available():
        pytest.skip(f'{backend_name} is not available')
    formula = WCNF() if native else PyWCNF()
    formula.append([-1, -2])
    formula.append([1], weight=2)
    formula.append([1], weight=5)  # last preference wins in the IPAMIR adapters
    formula.append([2], weight=3)
    formula.append([1, 2], weight=4)
    before = [tuple(row) for row in formula.soft]
    solver = backend(formula)
    try:
        cases = [([], 3), ([-1], 5)]
        for assumptions, cost in cases:
            assert solver.solve(assumptions=assumptions)
            assert solver.get_cost() == cost
        solver.set_soft(1, 1)
        assert solver.solve()
        assert solver.get_cost() == 1
        assert [tuple(row) for row in formula.soft] == before
    finally:
        solver.close()


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('backend_name', ['rc2', 'cgss'])
def test_local_engines_preserve_native_cardinality_constraints(native, backend_name):
    from pysat.formula import WCNFPlus as PyWCNFPlus
    if backend_name == 'rc2':
        from hermax.core.rc2.rc2 import RC2 as Backend
    else:
        from hermax.core.cgss_py.vendor.rc2_wce import RC2WCE as Backend
    formula = WCNFPlus() if native else PyWCNFPlus()
    formula.append([1])
    formula.append([2])
    formula.append([[1, 2], 1], is_atmost=True)
    backend = Backend(formula, solver='mc')
    try:
        assert backend.compute() is None
    finally:
        backend.delete()


def test_parser_preserves_mixed_narrow_and_arbitrary_precision_literals():
    text = 'p cnf 1099511627777 3\n+1 -2147483647 0\n1099511627777 -2 0\n0\n'
    formula = CNF(from_string=text)
    assert formula.clauses == [[1, -2147483647], [1099511627777, -2], []]
    assert formula.nv == 1099511627777
    assert CNF(from_string=formula.to_dimacs()).clauses == formula.clauses


@pytest.mark.parametrize('class_path', [
    'hermax.core.rc2.rc2_reentrant.RC2Reentrant',
    'hermax.core.openwbo_inc_py.openwbo_inc_solver.OpenWBOIncSolver',
    'hermax.core.tt_openwbo_inc_py.tt_openwbo_inc_solver.TTOpenWBOIncSolver',
    'hermax.core.loandra_py.loandra_solver.LoandraSolver',
])
@pytest.mark.parametrize('native', [False, True])
def test_adapter_constructors_accept_formula_collections_and_declared_unused_variables(class_path, native):
    import importlib
    from pysat.formula import WCNF as PyWCNF
    module, name = class_path.rsplit('.', 1)
    backend = getattr(importlib.import_module(module), name)
    if hasattr(backend, 'is_available') and not backend.is_available():
        pytest.skip(f'{name} is not available')
    formula = WCNF() if native else PyWCNF()
    formula.append([-1])
    formula.append([1, 2], weight=3)
    formula.nv = 5
    solver = backend(formula)
    try:
        count = getattr(solver, 'num_vars', getattr(solver, '_num_vars', 0))
        assert count >= 5
        assert isinstance(solver.signature(), str)
        assert [tuple(c) for c in formula.hard] == [(-1,)]
    finally:
        solver.close()


@pytest.mark.parametrize('suffix', ['.cnf', '.cnf.gz', '.cnf.bz2', '.cnf.xz'])
def test_public_file_loader_accepts_cnf_and_compression(tmp_path, suffix):
    from hermax.formula import load_formula
    source = CNF(from_clauses=[[1, -2], []])
    source.nv = 5
    path = tmp_path / ('input' + suffix)
    source.to_file(path)
    loaded = load_formula(path)
    assert loaded.clauses == source.clauses
    assert loaded.nv == 5


def test_public_file_loader_preserves_weighted_native_constraints(tmp_path):
    from hermax.formula import load_formula
    path = tmp_path / 'input.data'
    path.write_text('p wcnf+ 3 2 10\n3 1 -2 0\n10 w 2*1 4*3 <= 3\n')
    formula = load_formula(path)
    assert formula.soft == [[1, -2]]
    assert formula.wght == [3]
    assert formula.atms == [[[1, 3], 3, [2, 4]]]


def test_public_file_loader_uses_extension_for_ambiguous_headerless_input(tmp_path):
    from hermax.formula import load_formula
    path = tmp_path / 'input.wcnf'
    path.write_text('3 1 -2 0\n')
    assert load_formula(path).wght == [3]
    ambiguous = tmp_path / 'input.data'
    ambiguous.write_text(path.read_text())
    with pytest.raises(ValueError, match='header|extension'):
        load_formula(ambiguous)
