"""Flat cardinality routing and arithmetic size predictions."""
import itertools

import pytest
from pysat.solvers import Solver

from hermax.encoder.pbamo import PBAMOEnc
from hermax.encoder._packed import PBAMOEnc as PackedPBAMOEnc
from hermax.encoder._packed import CardEnc
from hermax.encoder.card import EncType
from hermax.encoder._cardinality_policy import modulo_size, sequential_size, shared_equality_size


@pytest.mark.parametrize('backend', [PBAMOEnc, PackedPBAMOEnc])
def test_small_lower_bound_does_not_build_a_large_modulo_counter(backend):
    n = 1000
    cnf = backend.auto_leq(lits=list(range(1, n + 1)), weights=[1] * n,
                           bound=n - 4, top_id=1200)
    assert cnf.nv - 1200 <= 4 * n
    assert len(cnf.clauses) <= 7 * n


@pytest.mark.parametrize('backend', [PBAMOEnc, PackedPBAMOEnc])
def test_exact_count_beyond_three_uses_shared_equality_when_smaller(backend):
    n = 200
    cnf = backend.auto_eq(lits=list(range(1, n + 1)), weights=[1] * n, bound=6)
    assert cnf.nv - n <= 1163
    assert len(cnf.clauses) <= 5619


@pytest.mark.parametrize('count', [4, 5, 8, 13, 32, 65, 128, 257])
def test_arithmetic_sizes_match_native_encoders(count):
    bounds = (range(count + 1) if count <= 32 else
              {0, 1, 2, 3, 4, 8, 15, 16, 17, count // 2,
               count - 17, count - 4, count - 2, count - 1, count})
    lits = list(range(1, count + 1))
    for bound in bounds:
        for predict, encoding in [(modulo_size, EncType.kmtotalizer),
                                  (sequential_size, EncType.seqcounter)]:
            cnf = CardEnc.atmost(lits=lits, bound=bound, top_id=count, encoding=encoding)
            assert predict(count, bound) == (max(0, cnf.nv - count), len(cnf.clauses))
        if 2 <= bound <= count - 2:
            cnf = PackedPBAMOEnc.equals(lits=lits, weights=[1] * count,
                                       groups=[[lit] for lit in lits], bound=bound)
            assert shared_equality_size(count, bound) == (cnf.nv - count, len(cnf.clauses))


@pytest.mark.parametrize('backend', [PBAMOEnc, PackedPBAMOEnc])
@pytest.mark.parametrize('method', ['auto_leq', 'auto_eq'])
def test_selected_encoding_preserves_complete_input_propagation(backend, method):
    n = 6
    lits = [1, -2, 3, -4, 5, -6]
    for bound in range(2, n - 1):
        cnf = getattr(backend, method)(lits=lits, weights=[1] * n, bound=bound, top_id=20)
        with Solver(bootstrap_with=cnf.clauses) as solver:
            for values in itertools.product([None, False, True], repeat=n):
                fixed = [lit if value else -lit for lit, value in zip(lits, values)
                         if value is not None]
                true, false = values.count(True), values.count(False)
                expected = true <= bound and (method == 'auto_leq' or false <= n - bound)
                ok, propagated = solver.propagate(assumptions=fixed)
                assert ok == expected
                if ok:
                    required = set(fixed)
                    if true == bound:
                        required.update(-lit for lit, value in zip(lits, values) if value is None)
                    if method == 'auto_eq' and false == n - bound:
                        required.update(lit for lit, value in zip(lits, values) if value is None)
                    assert required <= set(propagated)


@pytest.mark.parametrize('backend', [PBAMOEnc, PackedPBAMOEnc])
@pytest.mark.parametrize('lits', [[1, 1, 2, 3, 4, 5], [1, -1, 2, 3, 4, 5]])
def test_aliases_keep_the_existing_inequality_encoder(backend, lits):
    actual = backend.auto_leq(lits=lits, weights=[1] * len(lits), bound=4, top_id=20)
    expected = CardEnc.atmost(lits=lits, bound=4, top_id=20, encoding=EncType.kmtotalizer)
    assert actual.nv == expected.nv
    assert list(map(tuple, actual.clauses)) == list(map(tuple, expected.clauses))


@pytest.mark.parametrize('backend', [PBAMOEnc, PackedPBAMOEnc])
def test_flat_selection_only_runs_for_unstructured_sides(monkeypatch, backend):
    import hermax.encoder.pbamo as module

    original = module.prefer_sequential
    calls = []

    def record(*args):
        calls.append(args)
        return original(*args)

    def reject(*args):
        pytest.fail('flat equality selector was used for a structured constraint')

    monkeypatch.setattr(module, 'prefer_sequential', record)
    monkeypatch.setattr(module, 'prefer_shared_equality', reject)
    lits = list(range(1, 9))
    for method in ['auto_leq', 'auto_eq']:
        getattr(backend, method)(lits=lits, weights=[1] * 8, bound=3,
                                 groups=[[1, 2], [3, 4], [5, 6], [7, 8]])
        assert calls == ([] if method == 'auto_leq' else [(8, 5)])


def test_variable_clause_tradeoffs_keep_modulo_counter():
    for count, bound in [(128, 4), (128, 120), (200, 3)]:
        lits = list(range(1, count + 1))
        actual = PackedPBAMOEnc.auto_leq(lits=lits, weights=[1] * count, bound=bound)
        expected = CardEnc.atmost(lits=lits, bound=bound, encoding=EncType.kmtotalizer)
        assert actual.nv == expected.nv
        assert list(actual.clauses) == list(expected.clauses)
