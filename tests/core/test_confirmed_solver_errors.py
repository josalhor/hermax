import pytest
from pysat.formula import WCNFPlus
from hermax.core import CoreTrailSolver, RC2Reentrant, UWrMaxSATSolver
from hermax.core.utils import extract_wcnf_data


@pytest.mark.parametrize('weighted', [False, True])
def test_extractor_rejects_native_constraints(weighted):
    f = WCNFPlus()
    f.append([[1, 2], 1, [2, 3]] if weighted else [[1, 2], 1], is_atmost=True)
    with pytest.raises(NotImplementedError, match='cardinality|pseudo-Boolean'):
        extract_wcnf_data(f)


@pytest.mark.parametrize('cls', [CoreTrailSolver, RC2Reentrant, UWrMaxSATSolver])
def test_adapters_reject_contradictory_wcnfplus(cls):
    f = WCNFPlus()
    f.append([1])
    f.append([2])
    f.append([[1, 2], 1], is_atmost=True)
    with pytest.raises(NotImplementedError):
        cls(f)


@pytest.mark.parametrize('method', ['set_soft', 'add_clause'])
def test_coretrail_rejects_total_weight_overflow_atomically(method):
    s = CoreTrailSolver()
    try:
        s.add_clause([-1])
        s.add_clause([-2])
        s.set_soft(1, (1 << 63) - 1)
        with pytest.raises((ValueError, OverflowError), match='weight|range|overflow'):
            if method == 'set_soft':
                s.set_soft(2, 1)
            else:
                s.solver.add_clause([2], weight=1)
        assert s.solve()
        assert s.get_cost() == (1 << 63) - 1
        s.set_soft(1, 0)
        s.set_soft(2, 1)
        assert s.solve()
        assert s.get_cost() == 1
    finally:
        s.close()


def test_portfolio_rejects_native_constraints():
    from hermax.portfolio.solver import PortfolioSolver
    f = WCNFPlus()
    f.append([[1, 2], 1], is_atmost=True)
    with pytest.raises(NotImplementedError):
        PortfolioSolver([RC2Reentrant], formula=f)


def test_clause_only_wcnfplus_remains_supported():
    f = WCNFPlus()
    f.append([-1])
    f.append([1], weight=3)
    assert extract_wcnf_data(f).soft == [([1], 3)]
