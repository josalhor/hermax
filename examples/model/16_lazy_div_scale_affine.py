from hermax.model import Model

m = Model()

x = m.int("x", lb=0, ub=30)
y = m.int("y", lb=0, ub=50)

q = x // 4          # lazy DivExpr
s = x.scale(3)      # lazy ScaleExpr

# These compile through ladder-native fast paths (not generic PB encoders).
m &= (s + 2 <= y)
m &= (q == 3)

# Prefer a smaller y while respecting the affine constraints.
m.obj[1] += y

r = m.solve()
assert r.ok

print("x =", r[x])
print("q = x // 4 =", r[q])
print("s = 3*x =", r[s])
print("y =", r[y])
