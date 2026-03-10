from hermax.model import Model

m = Model()

x = m.int("x", lb=0, ub=30)
y = m.int("y", lb=0, ub=30)

m &= x.forbid_interval(10, 20)
m &= y.forbid_value(11)

m &= x.distance_at_most(y, 2)

score_x = sum((20 - abs(k - 16)) * (x == k) for k in range(30))
score_y = sum((20 - abs(k - 11)) * (y == k) for k in range(30))
m.obj[1] += -(score_x + score_y)

r = m.solve()
assert r.ok

print("x =", r[x])
print("y =", r[y])
print("distance =", abs(r[x] - r[y]))
