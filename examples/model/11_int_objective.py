from hermax.model import Model


m = Model()

x = m.int("x", lb=0, ub=10)
y = m.int("y", lb=0, ub=10)
use_bonus = m.bool("use_bonus")

m &= (x + y >= 8)
m &= (x + 2 * y <= 14)
m &= (x + use_bonus <= 6)

m.obj[3] += x
m.obj[1] += y
m.obj[2] += ~use_bonus

r = m.solve()

print("status:", r.status)
print("cost:", r.cost)
print("x,y,use_bonus:", r[x], r[y], r[use_bonus])
