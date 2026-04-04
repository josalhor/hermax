from pysat.formula import IDPool, WCNF

from hermax.incremental import EvalMaxSAT


wcnf = WCNF()
vpool = IDPool(start_from=1)
a = vpool.id("A")
b = vpool.id("B")
c = vpool.id("C")

wcnf.append([a, b])          # A OR B: at least one must be true
wcnf.append([-a, c])         # (NOT A) OR C: if A then C
wcnf.append([-b], weight=2)  # soft literal -B: pay 2 if B=True
wcnf.append([-c], weight=1)  # soft literal -C: pay 1 if C=True

solver = EvalMaxSAT(formula=wcnf)
ok = solver.solve()
print("feasible:", ok)
if ok:
    print("status:", solver.get_status().name)
    print("cost:", solver.get_cost())
    print("model:", solver.get_model())
