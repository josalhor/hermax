from hermax.model import Model


m = Model()
grid = m.enum_matrix("cell", rows=9, cols=9, choices=[str(i) for i in range(1, 10)], nullable=False)

for r in range(9):
    m &= grid[r, :].all_different()  # all digits in row r must differ
for c in range(9):
    m &= grid[:, c].all_different()  # all digits in column c must differ
for br in range(0, 9, 3):
    for bc in range(0, 9, 3):
        m &= grid[br : br + 3, bc : bc + 3].flatten().all_different()  # 3x3 subgrid all-different

m &= (grid[4, 4] == "5")  # one clue

r = m.solve()

print("status:", r.status)
print("center:", r[grid[4, 4]])
print("first_row:", r[grid[0, :]])
