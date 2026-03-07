from hermax.model import Model

m = Model()

use_truck = m.bool("use_truck")
load = m.int("load", lb=0, ub=20)

# Big-M style indicator constraint:
# if truck is used, load <= 12; otherwise load <= 4
m &= (load - 8 * use_truck <= 4)

# Prefer using the truck, but also prefer larger load.
m.obj[3] += ~use_truck
m.obj[1] += -load.piecewise(base_value=0, steps={k: k for k in range(1, 20)})

r = m.solve()
assert r.ok

print("use_truck =", r[use_truck])
print("load =", r[load])

