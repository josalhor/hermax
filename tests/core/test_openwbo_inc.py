import sys
import os

# Removed path hacks, relying on pip installation
from hermax.core.openwbo_inc import OpenWBOInc

def test_openwbo():
    solver = OpenWBOInc()

    # Create 3 variables
    a = solver.newVar()
    b = solver.newVar()
    c = solver.newVar()

    # Add hard clauses
    solver.addClause([-a, -b])        # !a or !b

    # Add soft clauses
    solver.addClause([a, b], 1)       # a or b
    solver.addClause([c], 1)          # c
    solver.addClause([a, -c], 1)      # a or !c
    solver.addClause([b, -c], 1)      # b or !c

    print("------ EvalMaxSAT Python Binding Test ------")
    print(f"Variables created: a={a}, b={b}, c={c}")

    if not solver.solve():
        print("s UNSATISFIABLE")
        return

    print("s OPTIMUM FOUND")
    print(f"o {solver.getCost()}")
    print(f"a = {solver.getValue(a)}")
    print(f"b = {solver.getValue(b)}")
    print(f"c = {solver.getValue(c)}")

if __name__ == "__main__":
    test_openwbo()