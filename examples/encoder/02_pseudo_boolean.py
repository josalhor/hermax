from hermax.encoder import PBEnc, PBEncType
from pysat.solvers import Solver


lits = [1, 2, 3]
cnf = PBEnc.leq(lits=lits, weights=[2, 3, 5], bound=5, top_id=max(lits), encoding=PBEncType.bdd)

with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
    within_bound = solver.solve(assumptions=[1, 2, -3])
    over_bound = solver.solve(assumptions=[1, -2, 3])

print("constraint: 2*x1 + 3*x2 + 5*x3 <= 5")
print("encoding: bdd")
print(f"variables: {cnf.nv}")
print(f"clauses: {len(cnf.clauses)}")
print(f"x1=x2=true: sat={within_bound}")
print(f"x1=x3=true: sat={over_bound}")
