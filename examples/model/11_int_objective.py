from hermax.model import Model


m = Model()

x = m.int("x", lb=0, ub=10)
y = m.int("y", lb=0, ub=10)
use_bonus = m.bool("use_bonus")

m &= (x + y >= 8)             # total production requirement
m &= (x + 2 * y <= 14)        # resource limit
m &= (x + use_bonus <= 6)     # if bonus is used, x capacity is tighter

m.obj[3] += x                 # minimize x with weight 3
m.obj[1] += y                 # minimize y with weight 1
m.obj[2] += ~use_bonus        # pay 2 if bonus is used

r = m.solve()

print("status:", r.status)
print("cost:", r.cost)
print("x,y,use_bonus:", r[x], r[y], r[use_bonus])
