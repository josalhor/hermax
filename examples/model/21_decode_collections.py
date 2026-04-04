from hermax.model import Model

m = Model()

vec = m.int_vector("vec", length=3, lb=0, ub=5)
mat = m.int_matrix("mat", rows=2, cols=2, lb=0, ub=5)
flags = m.bool_dict("flag", keys=["r1", "r2"])
mode = m.enum_dict("mode", keys=["r1", "r2"], choices=["eco", "boost"], nullable=True)

m &= (vec[0] == 1)
m &= (vec[1] == 3)
m &= (vec[2] == 2)

m &= (mat[0, 0] == 2)
m &= (mat[0, 1] == 4)
m &= (mat[1, 0] == 1)
m &= (mat[1, 1] == 0)

m &= flags["r1"]
m &= ~flags["r2"]

m &= (mode["r1"] == "eco")
m &= (mode["r2"] == "boost")

r = m.solve()
assert r.ok

print("vec        =", r[vec])
print("mat        =", r[mat])
print("mat col 1  =", r[mat[:, 1]])
print("flags      =", r[flags])
print("mode       =", r[mode])
