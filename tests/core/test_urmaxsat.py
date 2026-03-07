import sys
import os
from hermax.core.urmaxsat_py import UWrMaxSAT

def test_urmaxsat():

    solver = UWrMaxSAT()



    # UWrMaxSAT doesn't have a direct newVar function, variables are implicitly created.

    # We'll use arbitrary positive integers for variables.

    a = 1

    b = 2

    c = 3



    # Add hard clauses

    solver.addClause([-a, -b])        # !a or !b



    # Add soft clauses

    solver.addClause([a, b], 1)       # a or b

    solver.addClause([c], 1)          # c

    solver.addClause([a, -c], 1)      # a or !c

    solver.addClause([b, -c], 1)      # b or !c



    print("------ UWrMaxSAT Python Binding Test ------")

    print(f"Variables used: a={a}, b={b}, c={c}")



    result = solver.solve()



    if result == 20: # UNSAT

        print("s UNSATISFIABLE")

        return

    elif result == 30: # OPTIMAL

        print("s OPTIMUM FOUND")

    elif result == 10: # SAT (feasible solution found, but not necessarily optimal)

        print("s FEASIBLE SOLUTION FOUND")

    else:

        print(f"s SOLVER RETURNED: {result}")

        return



    print(f"o {solver.getCost()}")



    print(f"a = {solver.getValue(a)}")

    print(f"b = {solver.getValue(b)}")

    print(f"c = {solver.getValue(c)}")



if __name__ == "__main__":

    test_urmaxsat()