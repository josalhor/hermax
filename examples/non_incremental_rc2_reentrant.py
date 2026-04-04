from pysat.formula import IDPool, WCNF

from hermax.non_incremental import RC2

wcnf = WCNF()
vpool = IDPool(start_from=1)
a = vpool.id("A")
b = vpool.id("B")
c = vpool.id("C")

# Hard clauses
wcnf.append([-a, -b])  # (NOT A) OR (NOT B): A and B cannot both be true
wcnf.append([b, c])    # B OR C: at least one of them must be true

# Soft clauses
wcnf.append([a], weight=4)  # soft clause [A]: pay 4 if A=False
wcnf.append([b], weight=2)  # soft clause [B]: pay 2 if B=False
wcnf.append([c], weight=1)  # soft clause [C]: pay 1 if C=False

solver = RC2(formula=wcnf)
ok = solver.solve()
print("feasible:", ok)
if ok:
    print("status:", solver.get_status().name)
    print("cost:", solver.get_cost())
    print("model:", solver.get_model())
