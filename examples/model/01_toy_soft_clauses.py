from hermax.model import Model


m = Model()

a = m.bool("a")
b = m.bool("b")
c = m.bool("c")

m &= (a | b)  # a OR b: at least one must be true
m &= (~a | c)  # (NOT a) OR c: if a then c

m.obj[3] += a    # soft clause [a]: pay 3 if a is false
m.obj[2] += ~b   # soft clause [~b]: pay 2 if b is true
m.obj[1] += c    # soft clause [c]: pay 1 if c is false

r = m.solve()

print("status:", r.status)
print("cost:", r.cost)
print("a,b,c:", r[a], r[b], r[c])
