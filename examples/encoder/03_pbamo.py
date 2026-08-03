from hermax.encoder import PBAMOEnc
from hermax.encoder.pbamo import EncType
from pysat.solvers import Solver


lits = [1, 2, 3, 4]
cnf = PBAMOEnc.leq(
    lits=lits,
    weights=[2, 3, 4, 7],
    groups=[[1, 2], [3, 4]],
    bound=8,
    top_id=max(lits),
    encoding=EncType.rggt,
    emit_amo=True,
)

with Solver(name="g3", bootstrap_with=cnf.clauses) as solver:
    feasible = solver.solve(assumptions=[1, -2, 3, -4])
    over_bound = solver.solve(assumptions=[1, -2, -3, 4])
    violates_amo = solver.solve(assumptions=[1, 2, -3, -4])

print("constraint: 2*x1 + 3*x2 + 4*x3 + 7*x4 <= 8")
print("AMO groups: [x1, x2], [x3, x4]")
print("encoding: rggt")
print(f"variables: {cnf.nv}")
print(f"clauses: {len(cnf.clauses)}")
print(f"x1=x3=true: sat={feasible}")
print(f"x1=x4=true: sat={over_bound}")
print(f"x1=x2=true: sat={violates_amo}")
