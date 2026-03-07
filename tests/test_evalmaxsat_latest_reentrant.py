from hermax.core.evalmaxsat_latest_py import EvalMaxSATLatestReentrant
from hermax.core.ipamir_solver_interface import SolveStatus

def test_reentrant():
    print("Testing EvalMaxSATLatestReentrant...")
    solver = EvalMaxSATLatestReentrant()
    print(f"Solver signature: {solver.signature()}")
    
    # x1 or x2
    solver.add_clause([1, 2])
    
    # soft clauses:
    # -x1 (weight 10)
    # -x2 (weight 5)
    solver.add_soft_unit(-1, 10)
    solver.add_soft_unit(-2, 5)
    
    # Optimal should be x1=False, x2=True, cost 5
    res = solver.solve()
    print(f"Solve 1 result: {res}, Cost: {solver.get_cost()}, Model: {solver.get_model()}")
    assert res == True
    assert solver.get_cost() == 5
    
    # Now solve with assumption x1=True.
    # Should force x1=True, x2=False (to satisfy x1 or x2), cost 10
    res2 = solver.solve(assumptions=[1])
    print(f"Solve 2 (assump [1]) result: {res2}, Cost: {solver.get_cost()}, Model: {solver.get_model()}")
    assert res2 == True
    assert solver.get_cost() == 10
    
    # Now solve with assumption x1=True, x2=True. cost 15
    res3 = solver.solve(assumptions=[1, 2])
    print(f"Solve 3 (assump [1, 2]) result: {res3}, Cost: {solver.get_cost()}, Model: {solver.get_model()}")
    assert res3 == True
    assert solver.get_cost() == 15

    print("Reentrant test passed!")

if __name__ == "__main__":
    test_reentrant()
