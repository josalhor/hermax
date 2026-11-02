import itertools
import random
from types import SimpleNamespace

import pytest
from pysat.solvers import Solver

from hermax.model import Model
from hermax.model._all_different import clause_costs, filter_domains, prefer_bipartite


def test_matching_filter_matches_exhaustive_supported_values():
    rng = random.Random(18)
    for _ in range(400):
        width = rng.randrange(1, 7)
        domains = [tuple(sorted(rng.sample(range(width), rng.randrange(1, width + 1))))
                   for _ in range(rng.randrange(1, 6))]
        solutions = [row for row in itertools.product(*domains) if len(set(row)) == len(row)]
        result = filter_domains(domains)
        if not solutions:
            assert result is None
        else:
            supported = result
            assert list(map(set, supported)) == [set(row[i] for row in solutions)
                                                for i in range(len(domains))]


def test_matching_filter_skips_wide_domains_that_cannot_prune():
    domains = [range(10**9), range(1, 10**9)]
    supported = filter_domains(domains)
    assert supported is domains


@pytest.mark.parametrize('backend', ['pairwise', 'bipartite', 'auto'])
@pytest.mark.parametrize('mode', ['plain', 'only_if', 'iff', 'implies'])
@pytest.mark.parametrize('domains', [
    [(0, 1), (0, 1), (0, 2)],  # Hall set forces the third variable to 2.
    [(0, 1)] * 3 + [(0, 4)],  # Impossible subset despite a large enough union.
    [(0, 0), (0, 2), (1, 3)],
    [(1, 2), (1, 2), (0, 3)],  # Removing an interior interval keeps both boundaries.
    [(1, 1), (3, 3), (0, 4)],  # Multiple separate forbidden intervals.
    [(0, 1), (0, 1), (8, 9), (8, 9)],  # Two separate permutations.
])
def test_integer_filtering_truth_table_and_gating(backend, mode, domains):
    m = Model()
    xs = m.vector([m.int(f'x{i}', lb, ub) for i, (lb, ub) in enumerate(domains)])
    gate = m.bool('gate')
    condition = xs.all_different(backend=backend)
    m &= condition if mode == 'plain' else getattr(condition, mode)(gate)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product(*(range(lb, ub + 1) for lb, ub in domains)):
            truth = len(set(values)) == len(values)
            assumptions = [m._lit_to_dimacs(atom) for x, value in zip(xs, values)
                           for atom in x._exact_value_atoms(value)]
            for enabled in (False, True):
                expected = (truth if mode == 'plain' else truth == enabled if mode == 'iff'
                            else not enabled or truth if mode == 'only_if' else not truth or enabled)
                assert solver.solve(assumptions=assumptions + [gate.id if enabled else -gate.id]) == expected


@pytest.mark.parametrize('kind,n,variables,clauses', [
    ('int', 9, 72, 387),
    ('int', 32, 2944, 6816),
    ('enum', 9, 225, 432),
    ('enum', 32, 3008, 5952),
])
def test_unchanged_permutations_keep_original_encoding_size(kind, n, variables, clauses):
    m = Model()
    xs = (m.int_vector('x', n, 0, n - 1) if kind == 'int'
          else m.enum_vector('x', n, list(range(n))))
    m &= xs.all_different()
    cnf = m.to_cnf()
    assert cnf.nv == variables
    assert len(cnf.clauses) == clauses


def test_hall_filter_reduces_encoding_without_mutating_variables():
    m = Model()
    xs = m.vector([m.int(f'x{i}', 0, 31 if i < 32 else 63) for i in range(64)])
    m &= xs.all_different()
    cnf = m.to_cnf()
    assert cnf.nv < 7000
    assert len(cnf.clauses) < 16000
    assert all(x.lb == 0 and x.ub == (31 if i < 32 else 63) for i, x in enumerate(xs))


@pytest.mark.parametrize('backend', ['pairwise', 'bipartite', 'auto'])
def test_nullable_enum_hall_filter_is_conditional(backend):
    m = Model()
    a, b = [m.enum(name, ['a', 'b']) for name in ('x', 'y')]
    c = m.enum('z', ['a', 'b'], nullable=True)
    gate = m.bool('gate')
    m &= m.vector([a, b, c]).all_different(backend=backend).only_if(gate)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        assert solver.solve(assumptions=[gate.id])
        assert not solver.solve(assumptions=[gate.id, m._lit_to_dimacs(c == 'a')])
        assert solver.solve(assumptions=[-gate.id, m._lit_to_dimacs(c == 'a')])


def test_matching_does_not_expand_unrelated_wide_domains():
    domains = [range(1), range(100, 10**9), range(-10**9, -100)]
    supported = filter_domains(domains)
    assert all(a is b for a, b in zip(domains, supported))


@pytest.mark.parametrize('backend', ['pairwise', 'bipartite', 'auto'])
@pytest.mark.parametrize('mode', ['plain', 'only_if', 'iff', 'implies'])
def test_mixed_nullable_enum_filtering_truth_table(backend, mode):
    m = Model()
    xs = m.vector([m.enum('x', [1, 2]), m.enum('y', [1, 2]),
                   m.enum('z', [1, 2], nullable=True)])
    flag = m.bool('flag')
    condition = xs.all_different(backend=backend)
    m &= condition if mode == 'plain' else getattr(condition, mode)(flag)
    with Solver(bootstrap_with=m.to_cnf().clauses) as solver:
        for values in itertools.product([1, 2], [1, 2], [1, 2, None]):
            truth = len(set(values)) == 3
            atoms = [m._lit_to_dimacs(atom) for item, value in zip(xs, values)
                     for atom in ([~lit for lit in item._choice_lits.values()]
                                  if value is None else [item == value])]
            for enabled in (False, True):
                expected = (truth if mode == 'plain' else truth == enabled if mode == 'iff'
                            else not enabled or truth if mode == 'only_if' else not truth or enabled)
                assert solver.solve(assumptions=atoms + [flag.id if enabled else -flag.id]) == expected


@pytest.mark.parametrize("size,values,backend", [
    (9, 9, "pairwise"),
    (11, 11, "pairwise"),
    (12, 12, "bipartite"),
    (12, 24, "pairwise"),  # Equal clause counts keep the smaller variable count.
    (12, 100, "pairwise"),
    (13, 100, "bipartite"),
])
@pytest.mark.parametrize("mode", ["plain", "only_if", "iff", "implies"])
def test_auto_all_different_matches_cost_selected_backend(size, values, backend, mode):
    formulas = []
    for selected in ("auto", backend):
        m = Model()
        xs = m.int_vector("x", size, 0, values - 1)
        flag = m.bool("flag")
        constraint = xs.all_different(selected)
        m &= constraint if mode == "plain" else getattr(constraint, mode)(flag)
        formulas.append(m.to_cnf())
    assert formulas[0].nv == formulas[1].nv
    assert formulas[0].clauses == formulas[1].clauses


def test_large_all_different_retains_bipartite_for_sparse_domains():
    formulas = []
    for backend in ("auto", "bipartite"):
        m = Model()
        xs = m.vector([m.int(f"x{i}", (i // 4) * 100, (i // 4) * 100 + 4)
                       for i in range(32)])
        m &= xs.all_different(backend)
        formulas.append(m.to_cnf())
    assert formulas[0].nv == formulas[1].nv
    assert formulas[0].clauses == formulas[1].clauses


def test_all_different_costs_match_fresh_encodings():
    rng = random.Random(41)
    for _ in range(24):
        size = rng.randrange(2, 22)
        bounds = [(rng.randrange(-6, 7), size + rng.randrange(7, 22)) for _ in range(size)]
        actual = []
        for backend in ("pairwise", "bipartite"):
            m = Model()
            xs = m.vector([m.int(f"x{i}", lo, hi) for i, (lo, hi) in enumerate(bounds)])
            before = len(m.to_cnf().clauses)
            m &= xs.all_different(backend)
            actual.append(len(m.to_cnf().clauses) - before)
        assert clause_costs(xs._items) == tuple(actual)


def test_all_different_costs_do_not_enumerate_domains_or_gaps():
    items = [SimpleNamespace(lb=i * 10**12, ub=i * 10**12 + 10**9) for i in range(4)]
    assert clause_costs(items) == (0, 0)
    assert not prefer_bipartite(items)
