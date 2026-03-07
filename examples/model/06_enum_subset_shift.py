from hermax.model import Model


m = Model()

shift = m.enum("shift", choices=["morning", "day", "night", "graveyard"], nullable=False)

m &= shift.is_in(["morning", "day"])  # daytime shifts only
m.obj[4] += ~(shift == "morning")  # pay 4 if morning is chosen
m.obj[1] += ~(shift == "day")      # pay 1 if day is chosen

r = m.solve()

print("status:", r.status)
print("cost:", r.cost)
print("shift:", r[shift])
