from hermax.model import Model


m = Model()

# Items: (weight, profit)
items = [(2, 6), (3, 8), (4, 9), (5, 10)]
take = m.bool_vector("take", len(items))

capacity = 8

m &= sum(w * take[i] for i, (w, _) in enumerate(items)) <= capacity

for i, (_, profit) in enumerate(items):
    m.obj[profit] += take[i]

r = m.solve()

chosen = [i for i in range(len(items)) if r[take[i]]]
total_weight = sum(items[i][0] for i in chosen)
total_profit = sum(items[i][1] for i in chosen)

print("status:", r.status)
print("cost:", r.cost)
print("chosen_items:", chosen)
print("total_weight:", total_weight, "capacity:", capacity)
print("total_profit:", total_profit)
