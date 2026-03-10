import math

from hermax.model import Model


coords = [(0, 0), (2, 4), (5, 2), (7, 6), (1, 5)]
demands = [0, 4, 5, 3, 5]
capacity = 10
vehicles = 2
n = len(demands)

dist = [
    [int(math.hypot(ax - bx, ay - by) * 10) for bx, by in coords]
    for ax, ay in coords
]

m = Model()
edge = m.bool_matrix("edge", n, n)
load = m.int_vector("load", n, lb=0, ub=capacity + 1)

m &= sum(edge.row(0)) == vehicles
m &= sum(edge.col(0)) == vehicles
m &= load[0] == 0

for i in range(n):
    m &= ~edge[i][i]
    if i > 0:
        m &= edge.row(i).exactly_one()
        m &= edge.col(i).exactly_one()
        m &= load[i] >= demands[i]

for i in range(n):
    for j in range(1, n):
        if i != j:
            m &= (load[i] + demands[j] <= load[j]).only_if(edge[i][j])

for i in range(n):
    for j in range(n):
        if i != j:
            m.obj += dist[i][j] * edge[i][j]

res = m.solve()

print("status:", res.status)
print("cost:", res.cost)
for i in range(n):
    for j in range(n):
        if res[edge[i][j]]:
            print(f"{i} -> {j}")
