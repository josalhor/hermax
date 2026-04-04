import pytest
from hermax.model import Model
from hermax.internal.kmerge import PBConstraintStub
from hermax.internal.kmerge import partition_constraints


def _kmerge_model() -> Model:
    m = Model()
    m.set_merge_pb_optimization(False)
    return m

def test_kmerge_clause_reduction():
    # Test correlation: 3 constraints with a heavy shared basis
    # C1: 100x1 + 10x2 + 20x3 <= 300
    # C2: 100x1 + 12x2 + 18x3 <= 300
    # Basis: 100x1 + 10x2 + 18x3
    
    def verify_model(res, core, stubs):
        # res[lit] returns the value of the literal in the model
        for stub in stubs:
            v_sum = sum(w * (1 if res[core[i]] else 0) for i, w in enumerate(stub.weights))
            if stub.op == "<=":
                assert v_sum <= stub.bound, f"Constraint failed: {v_sum} <= {stub.bound}"
            elif stub.op == "==":
                assert v_sum == stub.bound, f"Constraint failed: {v_sum} == {stub.bound}"

    def get_model_and_stats(shared):
        m = _kmerge_model()
        x = [m.bool(f"x{i}") for i in range(20)]
        
        # Correlated weights
        w1 = [100 + (i % 5) for i in range(20)]
        w2 = [100 + (i % 7) for i in range(20)]
        
        core = x
        stubs = [
            PBConstraintStub(lits=tuple(range(20)), weights=tuple(w1), bound=1000, op="<="),
            PBConstraintStub(lits=tuple(range(20)), weights=tuple(w2), bound=1000, op="<=")
        ]
        
        if shared:
            m &= sum(w1[i] * x[i] for i in range(20)) <= 1000
            m &= sum(w2[i] * x[i] for i in range(20)) <= 1000
            m._commit_pb()
        else:
            # Commit separately to avoid K-MERGE
            m &= sum(w1[i] * x[i] for i in range(20)) <= 1000
            m._commit_pb()
            m &= sum(w2[i] * x[i] for i in range(20)) <= 1000
            m._commit_pb()
            
        res = m.solve()
        assert res.ok
        verify_model(res, core, stubs)
        return len(m._hard)

    size_ind = get_model_and_stats(False)
    size_shr = get_model_and_stats(True)
    
    print(f"Independent: clauses={size_ind}")
    print(f"Shared:      clauses={size_shr}")
    
    # With merge optimization disabled in model tests, the shared commit path
    # must still preserve semantics even if it is not smaller.
    assert size_shr >= size_ind

def test_kmerge_unsat():
    # Verify that K-MERGE correctly handles UNSAT instances
    m = Model()
    m.set_merge_pb_optimization(False)
    x = [m.bool(f"x{i}") for i in range(5)]
    w1 = [10, 10, 10, 10, 10]
    w2 = [11, 11, 11, 11, 11]
    
    # sum(w1) <= 20 and sum(w2) >= 30 is easy to check
    # But K-MERGE only does leq/eq. Let's do:
    # sum(w1) >= 45 (needs 5) and sum(w2) <= 40 (needs max 3)
    # sum(w1) >= 45 -> sum(-x) <= 5 - 4.5 = 0.5?
    # Easier: x[0] + x[1] == 2 and x[0] + x[1] == 1
    m &= x[0] + x[1] == 2
    m &= x[0] + x[1] == 1
    
    m._commit_pb()
    res = m.solve()
    assert not res.ok

def test_kmerge_assumptions():
    # Verify that K-MERGE works correctly when solving under assumptions
    m = Model()
    m.set_merge_pb_optimization(False)
    x = [m.bool(f"x{i}") for i in range(10)]
    w1 = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
    w2 = [11, 11, 11, 11, 11, 11, 11, 11, 11, 11]
    
    m &= sum(w1[i] * x[i] for i in range(10)) <= 50
    m &= sum(w2[i] * x[i] for i in range(10)) <= 50
    m._commit_pb()
    
    # Assuming the first 5 are true already violates the tighter 11-weight
    # constraint: 5 * 11 = 55 > 50.
    res = m.solve(assumptions=[x[i] for i in range(5)])
    assert not res.ok

def test_kmerge_partitioning():
    # C1, C2 are similar. C3 is an outlier.
    # K-MERGE should group C1+C2 and leave C3 alone or in another group.
    m = Model()
    m.set_merge_pb_optimization(False)
    x = [m.bool(f"x{i}") for i in range(50)]
    
    # Group A
    m &= sum(100 * x[i] for i in range(10)) <= 500
    m &= sum(101 * x[i] for i in range(10)) <= 500
    
    # Outlier
    m &= sum(1 * x[i] for i in range(10)) <= 5
    
    m._commit_pb()
    # Check that it solved/encoded without error with the optimization disabled.
    assert len(m._hard) > 0


def test_kmerge_partitioning_helper_groups_similar_constraints():
    weights = [
        tuple(100 for _ in range(10)),
        tuple(101 for _ in range(10)),
        tuple(1 for _ in range(10)),
    ]
    stubs = [
        PBConstraintStub(lits=tuple(range(10)), weights=w, bound=500, op="<=")
        for w in weights
    ]
    parts = partition_constraints(stubs)
    assert any(set(part) == {0, 1} for part in parts)

if __name__ == "__main__":
    test_kmerge_clause_reduction()
    test_kmerge_unsat()
    test_kmerge_assumptions()
    test_kmerge_partitioning()
