from pysat.formula import IDPool

from hermax.incremental import EvalMaxSATIncr

solver = EvalMaxSATIncr()
vpool = IDPool(start_from=1)
x1 = vpool.id("x1")
x2 = vpool.id("x2")
x3 = vpool.id("x3")

# Hard clause
solver.add_clause([x1, x2])  # x1 OR x2: at least one must be true

# Unit soft clause
solver.add_soft_unit(-x1, 3)  # pay 3 if x1=True

# Non-unit soft clause (x1 OR x3) with weight 5.
# We encode it using a relaxation variable b:
# hard: (x1 OR x3 OR b), soft: (-b, 5)
b = solver.new_var()
solver.add_soft_relaxed([x1, x3], weight=5, relax_var=b)

ok = solver.solve()
print("feasible:", ok)
if ok:
    print("status:", solver.get_status().name)
    print("cost:", solver.get_cost())
    print("model:", solver.get_model())
