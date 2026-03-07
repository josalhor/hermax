from pysat.formula import IDPool

from hermax.incremental import UWrMaxSAT

solver = UWrMaxSAT()
vpool = IDPool(start_from=1)

x1 = vpool.id("x1")
x2 = vpool.id("x2")
x3 = vpool.id("x3")

# Hard clauses
solver.add_clause([x1, x2])   # x1 OR x2: at least one of x1, x2 must be true
solver.add_clause([-x1, x3])  # (NOT x1) OR x3: if x1 is true, x3 must also be true

# Soft literals
solver.set_soft(-x1, 6)       # soft literal -x1: pay 6 if x1=True
solver.set_soft(-x2, 2)       # soft literal -x2: pay 2 if x2=True
solver.set_soft(-x1, 3)       # update the previous penalty on x1 (last write wins)

print("Solve with assumption [-x1] (force x1=False):")
ok = solver.solve(assumptions=[-x1])
print("  feasible:", ok)
if ok:
    print("  status:", solver.get_status().name)
    print("  cost:", solver.get_cost())
    print("  model:", solver.get_model())

print("Solve with assumption [x2] (force x2=True):")
ok = solver.solve(assumptions=[x2])
print("  feasible:", ok)
if ok:
    print("  status:", solver.get_status().name)
    print("  cost:", solver.get_cost())
    print("  model:", solver.get_model())
