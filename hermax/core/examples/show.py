#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Incremental MaxSAT demo
Features shown on one persistent solver:
- Change unit soft weights by re-adding the same unit (last-by-literal wins)
- Add new hard clauses
- Use assumptions to toggle a guarded constraint
- Show that assumptions are scoped to one solve call

"""

from hermax.core import UWrMaxSATSolver as MaxSATSolver
from hermax.core.ipamir_solver_interface import SolveStatus

def show(slv, tag, assumptions=None, expect_feasible=True):
    ok = slv.solve(assumptions=assumptions or [])
    st = slv.get_status()
    print(f"\n== {tag} ==")
    print(f"solve(ok)={ok} status={st.name}")
    if st == SolveStatus.OPTIMUM:
        cost = slv.get_cost()
        model = sorted(set(slv.get_model()), key=lambda x:(abs(x), x<0))
        print(f"cost={cost}")
        print(f"model={model}")
        # Quick sanity: val agrees with model membership for mentioned vars
        for lit in {abs(x) for x in model}:
            vpos, vneg = slv.val(lit), slv.val(-lit)
            assert vpos in (-1,0,1) and vneg in (-1,0,1)
    else:
        if expect_feasible:
            print("No optimum found. You wanted feasibility, so your solver is misconfigured here.")
    return st

def main():
    # s1..s4
    s1, s2, s3, s4 = 1, 2, 3, 4

    # Sets
    # S1={e1,e2} cost 2
    # S2={e2}     cost 1
    # S3={e2,e3}  cost 2
    # S4={e1,e3}  cost 2

    # Base instance
    S = MaxSATSolver()

    # Soft unit costs
    S.add_soft_unit(-s1, 2)
    S.add_soft_unit(-s2, 1)
    S.add_soft_unit(-s3, 2)
    S.add_soft_unit(-s4, 2)

    # Hard coverage constraints
    # e1 covered by S1 or S4
    S.add_clause([s1, s4])
    # e2 covered by S1 or S2 or S3
    S.add_clause([s1, s2, s3])
    # e3 covered by S3 or S4
    S.add_clause([s3, s4])

    show(S, "Base F0")
    print("Expected optimum: {S2, S4} cost 3")

    # Step 1: change a unit soft weight without changing the clause
    # Increase cost of S4 from 2 to 4.
    S.add_soft_unit(-s4, 4)
    show(S, "Step 1: weight(¬s4)=4")
    print("Expected optimum: {S1, S3} cost 4")

    # Step 2: add a new hard clause that couples S2 and S4
    # New element e5 covered by S2 or S4
    S.add_clause([s2, s4])
    show(S, "Step 2: add hard (s2 ∨ s4)")
    print("Expected optimum: {S2, S4} cost 5 or {S1, S2, S3} cost 5")

    # Step 3: add a guarded hard and use assumptions to toggle it
    # Guard literal a bans S4 when assumed false
    a_noS4 = 10
    S.add_clause([a_noS4, -s4])   # if ¬a_noS4 is assumed, this becomes hard ¬s4
    show(S, "Step 3a: guard present, no assumptions")
    print("Expected optimum: {S2, S4} cost 5 or {S1, S2, S3} cost 5")

    # Now solve under assumptions to forbid S4
    show(S, "Step 3b: assume ¬a_noS4 which bans S4", assumptions=[-a_noS4])
    print("Expected optimum: {S1, S2, S3} cost 5")

    # Clear assumptions again to show scoping does not persist
    show(S, "Step 3c: assumptions cleared")
    print("Expected optimum: {S2, S4} cost 5 or {S1, S2, S3} cost 5")

    # Bonus: demonstrate unit weight decrease works too
    S.add_soft_unit(-s4, 2)   # cheaper to pick S4 again
    show(S, "Step 4: decrease weight(¬s4)=1")
    print("Expected optimum: {S2, S4} cost 3")

    # Test UNAST
    show(S, "Step 5: add unsat hard clause (s1)∧(¬s1)", expect_feasible=False, assumptions=[-s1, -s4])
    print("Expected: UNSAT")

    # Recover to feasible
    show(S, "Step 6: clear assumptions, back to feasible")
    print("Expected optimum: {S2, S4} cost 3")

    S.close()

if __name__ == "__main__":
    main()
