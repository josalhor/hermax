from hermax.model import Model


m = Model()
choices = [str(i) for i in range(1, 10)]
grid = m.enum_matrix("cell", rows=9, cols=9, choices=choices, nullable=False)

for r in range(9):
    m &= grid[r, :].all_different()
for c in range(9):
    m &= grid[:, c].all_different()
for br in range(0, 9, 3):
    for bc in range(0, 9, 3):
        m &= grid[br : br + 3, bc : bc + 3].flatten().all_different()

# Fixed Sudoku instance
givens = [
    (0, 0, "5"), (0, 1, "3"), (0, 4, "7"),
    (1, 0, "6"), (1, 3, "1"), (1, 4, "9"), (1, 5, "5"),
    (2, 1, "9"), (2, 2, "8"), (2, 7, "6"),
    (3, 0, "8"), (3, 4, "6"), (3, 8, "3"),
    (4, 0, "4"), (4, 3, "8"), (4, 5, "3"), (4, 8, "1"),
    (5, 0, "7"), (5, 4, "2"), (5, 8, "6"),
    (6, 1, "6"), (6, 6, "2"), (6, 7, "8"),
    (7, 3, "4"), (7, 4, "1"), (7, 5, "9"), (7, 8, "5"),
    (8, 4, "8"), (8, 7, "7"), (8, 8, "9"),
]

for r, c, v in givens:
    m &= (grid[r, c] == v)

r = m.solve()

print("status:", r.status)
for i in range(9):
    print(f"row_{i + 1}:", r[grid[i, :]])
