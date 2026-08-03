from hermax.encoder import CardEnc, CardEncType
from pysat.solvers import Solver


lits = [1, 2, 3, 4]
cnf = CardEnc.atmost(lits=lits, bound=2, top_id=max(lits), encoding=CardEncType.seqcounter)

with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
    three_true = solver.solve(assumptions=[1, 2, 3, -4])
    two_true = solver.solve(assumptions=[1, -2, 3, -4])

print("constraint: x1 + x2 + x3 + x4 <= 2")
print("encoding: seqcounter")
print(f"variables: {cnf.nv}")
print(f"clauses: {len(cnf.clauses)}")
print(f"x1=x2=x3=true: sat={three_true}")
print(f"x1=x3=true: sat={two_true}")
