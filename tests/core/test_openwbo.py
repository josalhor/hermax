import sys
import os

from hermax.core.openwbo import OLL, PartMSU3

def run_test(solver, solver_name):
    print(f"------ Testing {solver_name} ------", flush=True)
    # Create 3 variables
    print("Creating variables...", flush=True)
    a = solver.newVar()
    b = solver.newVar()
    c = solver.newVar()
    print(f"Variables created: a={a}, b={b}, c={c}", flush=True)

    # Add hard clauses
    print("Adding hard clause...", flush=True)
    solver.addClause([-a, -b])        # !a or !b
    print("Hard clause added.", flush=True)

    # Add soft clauses
    print("Adding soft clauses...", flush=True)
    solver.addClause([a, b], 1)       # a or b
    solver.addClause([c], 1)          # c
    solver.addClause([a, -c], 1)      # a or !c
    solver.addClause([b, -c], 1)      # b or !c
    print("Soft clauses added.", flush=True)

    print("Solving...", flush=True)
    solved = solver.solve()
    print(f"Solved: {solved}", flush=True)

    if not solved:
        print("s UNSATISFIABLE")
        return

    print("s OPTIMUM FOUND", flush=True)
    print("Getting cost...", flush=True)
    cost = solver.getCost()
    print(f"o {cost}", flush=True)
    assert cost == 1, f"Expected cost 1, but got {cost}"

    print("Getting model...", flush=True)
    val_a = solver.getValue(a)
    print(f"a = {val_a}", flush=True)
    val_b = solver.getValue(b)
    print(f"b = {val_b}", flush=True)
    val_c = solver.getValue(c)
    print(f"c = {val_c}", flush=True)
    print("-------------------------------------\n", flush=True)

def test_oll():
    run_test(OLL(), "OLL Solver")

def test_partmsu3():
    run_test(PartMSU3(), "PartMSU3 Solver")

if __name__ == "__main__":
    test_oll()
    test_partmsu3()
