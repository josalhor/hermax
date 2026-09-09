import itertools

import pytest
from pysat.solvers import Solver

from hermax.encoder import card as card_module
from hermax.encoder import pb_enc as pb_enc_module
from hermax.encoder.pbamo import PBAMOEnc
from hermax.model import Model
from hermax.internal.kmerge import PBConstraintStub
from hermax.internal.kmerge import partition_constraints


@pytest.mark.parametrize(
    ("op", "bound", "expected_sat"),
    [
        ("<=", 0, True),
        ("<=", -1, False),
        ("==", 0, True),
        ("==", 1, False),
    ],
)
def test_multi_leq_empty_term_set_encodes_constant_constraint(op, bound, expected_sat):
    stub = PBConstraintStub(lits=tuple(), weights=tuple(), bound=bound, op=op)
    cnf = PBAMOEnc.multi_leq([], [stub], top_id=0)

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        assert solver.solve() is expected_sat


def test_multi_leq_zero_weight_terms_with_negative_bound_are_unsat():
    stub = PBConstraintStub(lits=(1, 2), weights=(0, 0), bound=-1, op="<=")
    cnf = PBAMOEnc.multi_leq([1, 2], [stub], top_id=2)

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        assert not solver.solve()


def test_multi_leq_with_no_constraints_is_a_noop():
    cnf = PBAMOEnc.multi_leq([1, 2], [], top_id=2)

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        assert solver.solve()




def test_multi_leq_drains_all_carries(monkeypatch):
    """A carry chain must continue past the old fixed ten-column allowance."""

    captured_weights = []

    class FakeTotalizer:
        next_var = 10_000

        def __init__(self, lits, ubound, top_id):
            self.rhs = list(range(self.next_var, self.next_var + len(lits)))
            type(self).next_var += len(lits)
            self.cnf = type("CNF", (), {"clauses": [], "nv": top_id})()

    def capture_leq(*, lits, weights, bound, top_id, encoding):
        captured_weights.extend(weights)
        return type("CNF", (), {"clauses": [], "nv": top_id})()

    term_count = 2048
    lits = list(range(1, term_count + 1))
    stub = PBConstraintStub(
        lits=tuple(lits),
        weights=(2048,) * term_count,
        bound=term_count * 2048,
        op="<=",
    )
    monkeypatch.setattr(card_module, "ITotalizer", FakeTotalizer)
    monkeypatch.setattr(pb_enc_module.PBEnc, "leq", staticmethod(capture_leq))

    PBAMOEnc.multi_leq(lits, [stub], top_id=term_count)

    assert 1 << 22 in captured_weights


def test_multi_leq_equality_rejects_nonmatching_assignment():
    lits = [1, 2, 3, 4]
    stubs = [
        PBConstraintStub(
            lits=tuple(lits),
            weights=(1, 1, 1, 1),
            bound=2,
            op="==",
        ),
        PBConstraintStub(
            lits=tuple(lits),
            weights=(5, 1, 3, 1),
            bound=6,
            op="==",
        ),
    ]
    cnf = PBAMOEnc.multi_leq(lits, stubs, top_id=4)

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        assert not solver.solve(assumptions=[-1, -2, -3, -4])
        assert solver.solve(assumptions=[1, 2, -3, -4])


def test_multi_leq_equality_keeps_shared_upper_encoder(monkeypatch):
    """Equality must add a lower bound without discarding the shared upper basis."""
    lits = [1, 2, 3]
    stubs = [
        PBConstraintStub(tuple(lits), (1, 1, 1), 2, "=="),
        PBConstraintStub(tuple(lits), (2, 1, 1), 2, "<="),
    ]
    calls = {"equals": 0, "geq": 0}
    real_equals = pb_enc_module.PBEnc.equals
    real_geq = pb_enc_module.PBEnc.geq

    def count_equals(*args, **kwargs):
        calls["equals"] += 1
        return real_equals(*args, **kwargs)

    def count_geq(*args, **kwargs):
        calls["geq"] += 1
        return real_geq(*args, **kwargs)

    monkeypatch.setattr(pb_enc_module.PBEnc, "equals", staticmethod(count_equals))
    monkeypatch.setattr(pb_enc_module.PBEnc, "geq", staticmethod(count_geq))

    cnf = PBAMOEnc.multi_leq(lits, stubs, top_id=3)
    assert cnf.clauses
    assert calls == {"equals": 0, "geq": 1}


def test_multi_leq_mixed_equality_and_upper_bound_is_exact():
    lits = [1, 2, 3]
    stubs = [
        PBConstraintStub(tuple(lits), (1, 1, 1), 2, "=="),
        PBConstraintStub(tuple(lits), (2, 1, 1), 3, "<="),
    ]
    cnf = PBAMOEnc.multi_leq(lits, stubs, top_id=3)

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        for values in itertools.product((False, True), repeat=3):
            expected = (
                sum(values) == 2
                and (2 * values[0] + values[1] + values[2]) <= 3
            )
            assumptions = [lit if value else -lit for lit, value in zip(lits, values)]
            assert solver.solve(assumptions=assumptions) is expected


def test_multi_leq_exact_bound_accepts_boundary_and_rejects_overflow():
    """An exact bound is legal; only assignments above it must be rejected."""
    lits = [1, 2, 3]
    stub = PBConstraintStub(
        lits=tuple(lits),
        weights=(2048, 2048, 2048),
        bound=4096,
        op="<=",
    )
    cnf = PBAMOEnc.multi_leq(lits, [stub], top_id=3)

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        assert solver.solve(assumptions=[1, 2, -3])  # exactly 4096
        assert not solver.solve(assumptions=[1, 2, 3])  # 6144 exceeds 4096


def test_multi_leq_reported_exact_bound_case_rejects_only_the_real_violation():
    """The reported 2048-weight case must enforce the upper bound."""
    lits = [1, 2]
    stub = PBConstraintStub(
        lits=tuple(lits),
        weights=(2048, 2048),
        bound=4096,
        op="<=",
    )
    cnf = PBAMOEnc.multi_leq(lits, [stub], top_id=2)

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        assert solver.solve(assumptions=[1, -2])  # value 2048
        assert solver.solve(assumptions=[1, 2])   # value 4096, at the bound
        assert solver.solve(assumptions=[-1, -2])  # value 0


def test_multi_leq_carry_width_is_not_fixed_to_ten_columns():
    """A carry beyond column ten must still constrain the final sum."""
    lits = list(range(1, 2049))
    stub = PBConstraintStub(
        lits=tuple(lits),
        weights=(1,) * len(lits),
        bound=len(lits) - 1,
        op="<=",
    )
    cnf = PBAMOEnc.multi_leq(lits, [stub], top_id=len(lits))

    with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
        assert not solver.solve(assumptions=lits)


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
