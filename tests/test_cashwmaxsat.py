from hermax.core.cashwmaxsat_py import CASHWMaxSATSolver
from hermax.core.ipamir_solver_interface import SolveStatus

def test_simple():
    print("Testing CASHWMaxSATSolver...")
    solver = CASHWMaxSATSolver()
    print(f"Solver signature: {solver.signature()}")
    
    # x1 or x2
    solver.add_clause([1, 2])
    
    # soft clauses:
    # -x1 (weight 10)
    # -x2 (weight 5)
    solver.add_clause([-1], 10)
    solver.add_clause([-2], 5)
    
    # Optimal should be x1=False, x2=True, cost 5
    res = solver.solve()
    print(f"Solve result: {res}")
    print(f"Status: {solver.get_status()}")
    
    if res:
        print(f"Cost: {solver.get_cost()}")
        print(f"Model: {solver.get_model()}")
        print(f"Value of x1: {solver.val(1)}")
        print(f"Value of x2: {solver.val(2)}")
        
        assert solver.get_cost() == 5
        assert solver.val(1) == -1
        assert solver.val(2) == 1
        print("Test passed!")
    else:
        print("Test failed: No solution found.")
        sys.exit(1)

if __name__ == "__main__":
    test_simple()
