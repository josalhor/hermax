from hermax.model import Model


sizes = [4, 8, 1, 4, 2, 1]
capacity = 10
num_items = len(sizes)
num_bins = num_items

m = Model()
place = m.bool_matrix("place", num_items, num_bins)
used = m.bool_vector("used", num_bins)

for i in range(num_items):
    m &= place.row(i).exactly_one()

for b in range(num_bins):
    m &= sum(sizes[i] * place[i][b] for i in range(num_items)) <= capacity
    for i in range(num_items):
        m &= place[i][b].implies(used[b])

for b in range(num_bins - 1):
    m &= used[b + 1].implies(used[b])

for b in range(num_bins):
    m.obj[1] += ~used[b]

r = m.solve()

print("status:", r.status)
print("bins_used:", sum(1 for b in range(num_bins) if r[used[b]]))
for b in range(num_bins):
    if r[used[b]]:
        items = [i for i in range(num_items) if r[place[i][b]]]
        load = sum(sizes[i] for i in items)
        print(f"bin {b}: items={items} load={load}/{capacity}")
