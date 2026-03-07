from hermax.model import Model


m = Model()

universe = ["u1", "u2", "u3", "u4"]
sets = {
    "S1": {"u1", "u2"},
    "S2": {"u2", "u3"},
    "S3": {"u3", "u4"},
    "S4": {"u1", "u4"},
}
set_cost = {"S1": 3, "S2": 2, "S3": 3, "S4": 2}

pick = m.bool_dict("pick", list(sets.keys()))

for u in universe:
    cover_u = [pick[s] for s in sets if u in sets[s]]
    m &= m.vector(cover_u, name=f"cover_{u}").at_least_one()  # some selected set must cover u

for s in sets:
    m.obj[set_cost[s]] += ~pick[s]  # [~pick[s]] is violated when pick[s] is true -> pay cost if selected

r = m.solve()

chosen_sets = [s for s in sets if r[pick[s]]]
print("status:", r.status)
print("cost:", r.cost)
print("chosen_sets:", chosen_sets)
