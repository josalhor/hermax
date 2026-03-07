from hermax.model import Model

m = Model()

x1 = m.bool("x1")
x2 = m.bool("x2")
x3 = m.bool("x3")

# Hard clauses
m &= (x1 | x2)   # x1 OR x2: at least one of x1, x2 must be true
m &= (~x1 | x3)  # (NOT x1) OR x3: if x1 is true, x3 must also be true

# Soft literals
ref_x1 = m.add_soft(~x1, weight=6)  # pay 6 if x1=True
m.add_soft(~x2, weight=2)           # pay 2 if x2=True
m.update_soft_weight(ref_x1, 3)     # update previous penalty on x1

print("Solve with assumption [~x1] (force x1=False):")
r = m.solve(assumptions=[~x1], backend="maxsat")
print("  feasible:", r.ok)
if r.ok:
    print("  status:", r.status)
    print("  cost:", r.cost)
    print("  model:", r.raw_model)

print("Solve with assumption [x2] (force x2=True):")
r = m.solve(assumptions=[x2], backend="maxsat")
print("  feasible:", r.ok)
if r.ok:
    print("  status:", r.status)
    print("  cost:", r.cost)
    print("  model:", r.raw_model)
