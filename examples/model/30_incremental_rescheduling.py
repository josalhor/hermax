from hermax.model import Model


m = Model()
tasks = ["T1", "T2", "T3"]
machines = ["M1", "M2"]

assign = m.enum_dict("assign", tasks, choices=machines, nullable=False)

def objective(t3_m1_weight: int):
    return (
        1 * (assign["T1"] == "M1")
        + 3 * (assign["T1"] == "M2")
        + 1 * (assign["T2"] == "M1")
        + 3 * (assign["T2"] == "M2")
        + t3_m1_weight * (assign["T3"] == "M1")
        + 3 * (assign["T3"] == "M2")
    )


m.obj = objective(1)

r1 = m.solve()
assert r1.ok
print("--- Baseline Plan ---")
print("cost:", r1.cost)
print("assignments:", r1[assign])

m &= ~(assign["T2"] == "M1")

r2 = m.solve()
assert r2.ok
print("--- Adjusted Plan (T2 on M1 forbidden) ---")
print("cost:", r2.cost)
print("assignments:", r2[assign])

r3 = m.solve(assumptions=[assign["T1"] == "M2"])
assert r3.ok
print("--- What-if (assume T1 on M2) ---")
print("cost:", r3.cost)
print("assignments:", r3[assign])

r4 = m.solve()
assert r4.ok
print("--- Back to model state (assumption removed) ---")
print("cost:", r4.cost)
print("assignments:", r4[assign])

m.obj = objective(5)

r5 = m.solve()
assert r5.ok
print("--- After objective update (T3 on M1 penalty raised) ---")
print("cost:", r5.cost)
print("assignments:", r5[assign])
