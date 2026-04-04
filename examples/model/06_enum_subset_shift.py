from hermax.model import Model


m = Model()

shift = m.enum("shift", choices=["morning", "day", "night", "graveyard"], nullable=False)

m &= shift.is_in(["morning", "day"])
m.obj[4] += ~(shift == "morning")
m.obj[1] += ~(shift == "day")

r = m.solve()

print("status:", r.status)
print("cost:", r.cost)
print("shift:", r[shift])
