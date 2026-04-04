from hermax.model import Model


m = Model()

cpu = m.int("cpu", lb=0, ub=6)
ram = m.int("ram", lb=0, ub=9)
mobo = m.int("mobo", lb=0, ub=6)

valid_configs = [
    (1, 2, 1),
    (2, 4, 2),
    (3, 4, 3),
    (4, 8, 5),
]

spec = m.vector([cpu, ram, mobo], name="system_spec")
m &= spec.is_in(valid_configs)

m &= (cpu == 2)
m &= (ram == 4)

r = m.solve()

print("status:", r.status)
print("system_spec:", r[spec])
print("cpu/ram/mobo:", r[cpu], r[ram], r[mobo])
