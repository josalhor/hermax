from hermax.model import Model

m = Model()

load = m.int("load", lb=0, ub=12)

# Piecewise tariff over load:
# [0,4) -> 10, [4,8) -> 25, [8,12) -> 60
tariff = load.piecewise(base_value=10, steps={4: 25, 8: 60})

# Hard budget cap on the tariff itself (compiled through PBExpr machinery).
m &= (tariff <= 25)

# Minimize load plus tariff to show piecewise composition in the objective.
m.obj[1] += load
m.obj[1] += tariff

r = m.solve()
assert r.ok

print("load =", r[load])
print("cost =", r.cost)

