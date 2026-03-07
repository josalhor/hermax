from hermax.model import Model

m = Model()

x = m.int("x", lb=0, ub=30)
y = m.int("y", lb=0, ub=30)

# Remove a maintenance window and a single bad value.
m &= x.forbid_interval(10, 20)
m &= y.forbid_value(13)

# Keep the two variables close without PB encoders.
m &= x.distance_at_most(y, 2)

# Prefer larger x and y to make the hole constraints visible.
m.obj[1] += -x.piecewise(base_value=0, steps={k: k for k in range(1, 30)})
m.obj[1] += -y.piecewise(base_value=0, steps={k: k for k in range(1, 30)})

r = m.solve()
assert r.ok

print("x =", r[x])
print("y =", r[y])
print("distance =", abs(r[x] - r[y]))

