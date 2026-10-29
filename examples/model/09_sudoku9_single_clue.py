from hermax.model import Model


m = Model()
choices = range(1, 10)
grid = m.enum_matrix("cell", rows=9, cols=9, choices=choices, nullable=False)

for r in range(9):
    m &= grid[r, :].all_different()
for c in range(9):
    m &= grid[:, c].all_different()
for br in range(0, 9, 3):
    for bc in range(0, 9, 3):
        m &= grid[br : br + 3, bc : bc + 3].flatten().all_different()

# Starting puzzle: 0 marks an empty cell.
puzzle = [
    [5, 3, 0,  0, 7, 0,  0, 0, 0],
    [6, 0, 0,  1, 9, 5,  0, 0, 0],
    [0, 9, 8,  0, 0, 0,  0, 6, 0],

    [8, 0, 0,  0, 6, 0,  0, 0, 3],
    [4, 0, 0,  8, 0, 3,  0, 0, 1],
    [7, 0, 0,  0, 2, 0,  0, 0, 6],

    [0, 6, 0,  0, 0, 0,  2, 8, 0],
    [0, 0, 0,  4, 1, 9,  0, 0, 5],
    [0, 0, 0,  0, 8, 0,  0, 7, 9],
]

for row, digits in enumerate(puzzle):
    for col, digit in enumerate(digits):
        if digit != 0:
            m &= grid[row, col] == digit

r = m.solve()

print("status:", r.status)
for i in range(9):
    print(f"row_{i + 1}:", r[grid[i, :]])
