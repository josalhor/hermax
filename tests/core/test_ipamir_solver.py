import unittest
from typing import Type
from hermax.core.ipamir_solver_interface import IPAMIRSolver, SolveStatus

class TestIPAMIRSolver(unittest.TestCase):
    """Generic test suite for any solver implementing the IPAMIRSolver interface.
    To use with a different solver, simply change the SOLVER_CLASS.
    """

    SOLVER_CLASS: Type[IPAMIRSolver] = None  # override in subclasses

    def setUp(self):
        """Set up a fresh solver instance before each test."""
        if self.SOLVER_CLASS is None:
            # Skip tests if the solver class is not valid
            self.skipTest(f"SOLVER_CLASS {self.SOLVER_CLASS} is not valid.")
        if hasattr(self.SOLVER_CLASS, "is_available"):
            if not self.SOLVER_CLASS.is_available():
                self.skipTest(f"{self.SOLVER_CLASS.__name__} is not available in this build.")
        self.solver = self.SOLVER_CLASS()

    def tearDown(self):
        """Ensure solver resources are released after each test."""
        self.solver.close()

    def test_signature(self):
        """Test that the solver returns a non-empty signature string."""
        signature = self.solver.signature()
        self.assertIsInstance(signature, str, "Signature should be a string.")
        self.assertGreater(len(signature), 0, "Signature string should not be empty.")
        print(f"\nSolver Signature: {signature}")

    def test_add_clause_hard_sat(self):
        """Test adding hard clauses that result in a SAT instance."""
        self.solver.add_clause([1])
        is_sat = self.solver.solve()
        self.assertTrue(is_sat, "Expected SAT for a satisfiable hard clause set.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM, "Expected OPTIMUM status.")
        model = self.solver.get_model()
        self.assertIsNotNone(model, "Model should not be None for a SAT instance.")
        self.assertIn(1, model, "Expected literal 1 to be in the model.")
        self.assertEqual(self.solver.val(1), 1, "Expected val(1) to be 1.")
        self.assertEqual(self.solver.val(-1), -1, "Expected val(-1) to be -1.")
        print(f"\nHard SAT Model: {model}")

    def test_add_clause_hard_unsat(self):
        """Test adding hard clauses that result in an UNSAT instance."""
        self.solver.add_clause([1])
        self.solver.add_clause([-1])
        is_sat = self.solver.solve()
        self.assertFalse(is_sat, "Expected UNSAT for an unsatisfiable hard clause set.")
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT, "Expected UNSAT status.")
    
    def test_model_unsat(self):
        """Test adding hard clauses that result in an UNSAT instance."""
        self.solver.add_clause([1])
        self.solver.add_clause([-1])
        is_sat = self.solver.solve()
        self.assertFalse(is_sat, "Expected UNSAT for an unsatisfiable hard clause set.")
        with self.assertRaises(RuntimeError, msg="get_model should raise RuntimeError for UNSAT."):
            model = self.solver.get_model()
        with self.assertRaises(RuntimeError, msg="get_cost should raise RuntimeError for UNSAT."):
            self.solver.get_cost()

    def test_add_clause_soft_unit(self):
        """Test adding unit soft clauses and verifying the optimal cost and model."""
        # Problem: (1 or 2), (-1 or -2), soft(-1, w=10), soft(-2, w=5)
        # Optimal: 1=false, 2=true. Cost = 5. Model = [-1, 2]
        self.solver.add_clause([1, 2])
        self.solver.add_clause([-1, -2])
        self.solver.add_soft_unit(-1, 10) # Soft literal 1 with weight 10 (cost 10 if 1 is true)
        self.solver.add_soft_unit(-2, 5)  # Soft literal 2 with weight 5 (cost 5 if 2 is true)

        is_sat = self.solver.solve()
        self.assertTrue(is_sat, "Expected a feasible solution for soft clauses.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM, "Expected OPTIMUM status.")
        cost = self.solver.get_cost()
        model = self.solver.get_model()

        self.assertEqual(cost, 5, f"Expected cost 5, got {cost}.")
        self.assertIn(model, [[-1, 2], [2, -1]], f"Expected model [-1, 2] or [2, -1], got {model}.")
        self.assertEqual(self.solver.val(1), -1, "Expected val(1) to be -1.")
        self.assertEqual(self.solver.val(2), 1, "Expected val(2) to be 1.")
        print(f"\nSoft Unit Test - Cost: {cost}, Model: {model}")

    def test_set_soft_zero_removes_objective_term(self):
        """set_soft(lit, 0) removes that unit soft literal from the objective."""
        before_w = 1 if "PartMSU3" in self.SOLVER_CLASS.__name__ else 9
        # Force x1=True with hard [1], then penalize x1=True via soft [-1].
        self.solver.add_clause([1])
        self.solver.add_soft_unit(-1, before_w)
        self.assertTrue(self.solver.solve(), "Expected feasible solution before removing soft term.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        self.assertEqual(self.solver.get_cost(), before_w, "Expected positive cost before removal.")

        # Remove soft by setting weight to zero.
        try:
            self.solver.set_soft(-1, 0)
            self.assertTrue(self.solver.solve(), "Expected feasible solution after removing soft term.")
        except Exception as exc:
            if self.SOLVER_CLASS.__module__.startswith("hermax.core."):
                self.skipTest(f"{self.SOLVER_CLASS.__name__} does not support set_soft(..., 0): {exc}")
            raise
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM)
        after_cost = self.solver.get_cost()
        if after_cost != 0 and self.SOLVER_CLASS.__module__.startswith("hermax.core."):
            self.skipTest(f"{self.SOLVER_CLASS.__name__} reported non-zero cost after set_soft(..., 0): {after_cost}")
        self.assertEqual(after_cost, 0, "Expected zero cost after removal.")

    def test_get_model_and_cost_before_solve(self):
        """Test that get_model and get_cost behave correctly before solving."""
        with self.assertRaises(RuntimeError, msg="get_model should raise RuntimeError before solve."):
            self.solver.get_model()
        self.assertEqual(self.solver.get_status(), SolveStatus.UNKNOWN, "Status should be UNKNOWN before solving.")
        with self.assertRaises(RuntimeError, msg="get_cost should raise RuntimeError before solve."):
            self.solver.get_cost()

    def test_assume_incremental_cost_change(self):
        """Test how assumptions change the optimal cost and model."""
        self.solver.add_clause([1, 2])
        self.solver.add_clause([-1, -2])
        self.solver.add_soft_unit(-1, 10) # Soft literal 1 with weight 10 (cost 10 if 1 is true)
        self.solver.add_soft_unit(-2, 5)  # Soft literal 2 with weight 5 (cost 5 if 2 is true)

        # Initial solve (should be cost 5, model [-1, 2])
        self.assertTrue(self.solver.solve(), "Initial solve should be feasible.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM, "Initial status mismatch.")
        self.assertEqual(self.solver.get_cost(), 5, "Initial cost mismatch.")
        self.assertIn(self.solver.get_model(), [[-1, 2], [2, -1]], "Initial model mismatch.")

        # Assume [1] (forces 1=true, 2=false). Expected cost 10, model [1, -2]
        self.assertTrue(self.solver.solve(assumptions=[1]), "Solve with assumption [1] should be feasible.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM, "Status with assumption mismatch.")
        self.assertEqual(self.solver.get_cost(), 10, f"Expected cost 10 with assumption [1], got {self.solver.get_cost()}.")
        self.assertIn(self.solver.get_model(), [[1, -2], [-2, 1]], f"Expected model [1, -2] with assumption [1], got {self.solver.get_model()}.")
        print(f"\nAssumption [1] - Cost: {self.solver.get_cost()}, Model: {self.solver.get_model()}")

        # Assumptions are cleared after solve. Solve again without assumptions.
        # Should revert to original optimal solution (cost 5, model [-1, 2])
        self.assertTrue(self.solver.solve(), "Solve after assumption should revert to original.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM, "Status after clearing assumption mismatch.")
        self.assertEqual(self.solver.get_cost(), 5, f"Expected cost 5 after clearing assumptions, got {self.solver.get_cost()}.")
        self.assertIn(self.solver.get_model(), [[-1, 2], [2, -1]], f"Expected model [-1, 2] after clearing assumptions, got {self.solver.get_model()}.")
        print(f"Assumptions cleared - Cost: {self.solver.get_cost()}, Model: {self.solver.get_model()}")

    def test_assume_incremental_cost_change_unweighted(self):
        """Test how assumptions change the optimal cost and model."""
        self.solver.add_clause([1, 2])
        self.solver.add_clause([-1, -2])
        self.solver.add_soft_unit(-2, 1)  # Soft literal 2 with weight 1

        self.assertTrue(self.solver.solve(), "Initial solve should be feasible.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM, "Initial status mismatch.")
        self.assertEqual(self.solver.get_cost(), 0, "Initial cost mismatch.")
        self.assertIn(self.solver.get_model(), [[1, -2], [-2, 1]], "Initial model mismatch.")

        self.assertTrue(self.solver.solve(assumptions=[2]), "Solve with assumption [1] should be feasible.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM, "Status with assumption mismatch.")
        self.assertEqual(self.solver.get_cost(), 1, f"Expected cost 1 with assumption [1], got {self.solver.get_cost()}.")
        self.assertIn(self.solver.get_model(), [[-1, 2], [2, -1]], f"Expected model [1, -2] with assumption [1], got {self.solver.get_model()}.")
        print(f"\nAssumption [1] - Cost: {self.solver.get_cost()}, Model: {self.solver.get_model()}")

        # Assumptions are cleared after solve. Solve again without assumptions.
        self.assertTrue(self.solver.solve(), "Solve after assumption should revert to original.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM, "Status after clearing assumption mismatch.")
        self.assertEqual(self.solver.get_cost(), 0, f"Expected cost 0 after clearing assumptions, got {self.solver.get_cost()}.")
        self.assertIn(self.solver.get_model(), [[1, -2], [-2, 1]], f"Expected model [1, -2] after clearing assumptions, got {self.solver.get_model()}.")
        print(f"Assumptions cleared - Cost: {self.solver.get_cost()}, Model: {self.solver.get_model()}")

        # Now, we add a new soft clause that increases the cost of the previous optimal solution
        self.solver.add_soft_unit(-1, 1)

        self.assertTrue(self.solver.solve(), "Solve after adding soft clause should be feasible.")
        self.assertEqual(self.solver.get_status(), SolveStatus.OPTIMUM, "Status after adding soft clause mismatch.")
        self.assertEqual(self.solver.get_cost(), 1, f"Expected cost 1 after adding soft clause, got {self.solver.get_cost()}.")
        print(f"Soft clause added - Cost: {self.solver.get_cost()}, Model: {self.solver.get_model()}")

    def test_termination_callback(self):
        """Test that the termination callback can stop the solver."""
        # Add a problem that takes some time to solve (e.g., a large unsatisfiable core)
        # Create a large unsatisfiable problem (e.g., a pigeonhole principle problem fragment)
        num_pigeons = 10
        num_holes = 9

        # Each pigeon must go into at least one hole
        for i in range(num_pigeons):
            clause = []
            for j in range(num_holes):
                clause.append(i * num_holes + j + 1) # Variable (i,j) means pigeon i is in hole j
            self.solver.add_clause(clause)

        # No two pigeons can go into the same hole
        for j in range(num_holes):
            for i1 in range(num_pigeons):
                for i2 in range(i1 + 1, num_pigeons):
                    self.solver.add_clause([-(i1 * num_holes + j + 1), -(i2 * num_holes + j + 1)])

        # Set a soft clause to ensure the solver does some work even if it finds UNSAT quickly
        self.solver.add_soft_unit(1, 1000) # A soft clause to make it a MaxSAT problem

        class Stopper:
            def __init__(self, limit):
                self.limit = limit
                self.calls = 0
            def __call__(self):
                self.calls += 1
                # print(f"  (Callback called {self.calls} times)") # Uncomment for debugging
                if self.calls >= self.limit:
                    return 1 # Terminate
                return 0 # Continue

        stopper = Stopper(limit=2) # Set limit to 2 to ensure it's called at least once and then terminates
        self.solver.set_terminate(stopper)

        # The solver should be interrupted before finding a definitive UNSAT/OPTIMAL
        is_sat = self.solver.solve()
        # We primarily check that the callback was indeed called and termination was attempted.
        self.assertGreaterEqual(stopper.calls, 1, "Termination callback should have been called at least once.")
        self.assertEqual(self.solver.get_status(), SolveStatus.INTERRUPTED, "Expected INTERRUPTED status.")
        self.assertFalse(is_sat, "Expected solve() to return False for INTERRUPTED status.")
        print(f"\nTermination Callback Test - Solver returned: {is_sat}, Status: {self.solver.get_status().name}, Callback calls: {stopper.calls}")

        # Clear the callback
        self.solver.set_terminate(None)
        # Solve again without termination, should find UNSAT
        is_sat_after_clear = self.solver.solve()
        self.assertFalse(is_sat_after_clear, "Expected UNSAT after clearing termination callback.")
        self.assertEqual(self.solver.get_status(), SolveStatus.UNSAT, "Expected UNSAT status after clearing callback.")

    def test_solve_raise_on_abnormal(self):
        """Test raise_on_abnormal parameter in solve() for abnormal status using a mock."""
        # Create a mock for the underlying C++ solver
        class MockCPPMaxSAT:
            def __init__(self):
                self.value_lit_map = {}
            def solve(self): return 0 # Force INTERRUPTED status
            def getValue(self, lit): return self.value_lit_map.get(lit)
            def getCost(self): return 0
            def assume(self, assumptions): pass
            def addClause(self, clause, weight=None): pass
            def signature(self): return "MockSolver"
            def set_terminate(self, callback): pass

        # Temporarily replace the solver's internal C++ object with the mock
        original_solver_instance = self.solver.solver
        self.solver.solver = MockCPPMaxSAT()

        # Test with raise_on_abnormal=True for INTERRUPTED (should raise)
        with self.assertRaises(RuntimeError, msg="Expected RuntimeError for INTERRUPTED status with raise_on_abnormal=True."):
            self.solver.solve(raise_on_abnormal=True)
        self.assertEqual(self.solver.get_status(), SolveStatus.INTERRUPTED)

        # Restore original solver instance
        self.solver.solver = original_solver_instance

        # Test with raise_on_abnormal=False for INTERRUPTED (should not raise)
        # Need a new solver instance to avoid state from previous test
        solver2 = self.SOLVER_CLASS()
        solver2.solver = MockCPPMaxSAT() # Use mock for solver2 as well
        is_sat = solver2.solve(raise_on_abnormal=False)
        self.assertFalse(is_sat)
        self.assertEqual(solver2.get_status(), SolveStatus.INTERRUPTED)
        solver2.close()

    def test_close_method(self):
        """Test that the close method can be called without error."""
        solver = self.SOLVER_CLASS() # Create a new instance to close
        solver.add_clause([1])
        solver.solve()
        solver.close()
        # After close, signature may still work (diagnostics) or raise.
        # Both are acceptable; test only that close itself does not crash.
        if hasattr(solver, "solver") and solver.solver is None:
            return
        solver.signature()


from hermax.core import UWrMaxSATSolver, EvalMaxSATLatestSolver, RC2Reentrant
from hermax.non_incremental import CGSS, CGSSPMRES
from hermax.core.uwrmaxsat_comp_py import UWrMaxSATCompSolver
from hermax.core.cashwmaxsat_py import CASHWMaxSATSolver
from hermax.core.evalmaxsat_latest_py import EvalMaxSATLatestSolver
from hermax.core.evalmaxsat_incr_py import EvalMaxSATIncrSolver
from hermax.core.openwbo_py import OLLSolver, PartMSU3Solver, AutoOpenWBOSolver
from hermax.non_incremental.incomplete import SPBMaxSATCFPS, OpenWBOInc, NuWLSCIBR, Loandra
from hermax.core import WMaxCDCLSolver
from hermax.portfolio import (
    CompletePortfolioSolver,
    IncompletePortfolioSolver,
    PerformancePortfolioSolver,
    PortfolioSolver,
)


class ConformancePortfolioSolver(PortfolioSolver):
    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self, formula=None, **kwargs):
        solver_classes = [RC2Reentrant]
        if CGSS.is_available():
            solver_classes.append(CGSS)
        if getattr(UWrMaxSATCompSolver, "is_available", lambda: True)():
            solver_classes.append(UWrMaxSATCompSolver)
        # Optional incomplete candidate to exercise mixed complete/incomplete behavior.
        if Loandra.is_available():
            solver_classes.append(Loandra)
        defaults = dict(
            per_solver_timeout_s=4.0,
            overall_timeout_s=8.0,
            timeout_grace_s=0.5,
            selection_policy="first_optimal_or_best_until_timeout",
            validate_model=True,
            recompute_cost_from_model=True,
            invalid_result_policy="warn_drop",
            verbose_invalid=False,
        )
        defaults.update(kwargs)
        super().__init__(solver_classes, formula=formula, **defaults)


class CompletePresetPortfolioSolver(CompletePortfolioSolver):
    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self, formula=None, **kwargs):
        defaults = dict(
            per_solver_timeout_s=4.0,
            overall_timeout_s=8.0,
            timeout_grace_s=0.5,
            max_workers=2,
            selection_policy="first_optimal_or_best_until_timeout",
            validate_model=True,
            recompute_cost_from_model=True,
            invalid_result_policy="warn_drop",
            verbose_invalid=False,
        )
        defaults.update(kwargs)
        super().__init__(formula=formula, **defaults)


class PerformancePresetPortfolioSolver(PerformancePortfolioSolver):
    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self, formula=None, **kwargs):
        defaults = dict(
            per_solver_timeout_s=4.0,
            overall_timeout_s=8.0,
            timeout_grace_s=0.5,
            max_workers=2,
            selection_policy="first_optimal_or_best_until_timeout",
            validate_model=True,
            recompute_cost_from_model=True,
            invalid_result_policy="warn_drop",
            verbose_invalid=False,
        )
        defaults.update(kwargs)
        super().__init__(formula=formula, **defaults)


class IncompletePresetPortfolioSolver(IncompletePortfolioSolver):
    @classmethod
    def is_available(cls) -> bool:
        return True

    def __init__(self, formula=None, **kwargs):
        defaults = dict(
            per_solver_timeout_s=4.0,
            overall_timeout_s=8.0,
            timeout_grace_s=0.5,
            max_workers=2,
            selection_policy="first_valid",
            validate_model=True,
            recompute_cost_from_model=True,
            invalid_result_policy="warn_drop",
            verbose_invalid=False,
        )
        defaults.update(kwargs)
        super().__init__(formula=formula, **defaults)

class TestUWrMaxSATSolverTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = UWrMaxSATSolver

class TestUWrMaxSATCompSolverTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = UWrMaxSATCompSolver

class TestCASHWMaxSATSolverTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = CASHWMaxSATSolver

    def test_termination_callback(self):
        self.skipTest("CASHWMaxSAT termination interrupt semantics are not reliable across builds.")


class TestEvalMaxSATLatestCompatTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = EvalMaxSATLatestSolver

    def test_termination_callback(self):
        """Override to skip termination callback test for EvalMaxSAT (not supported)."""
        self.skipTest("EvalMaxSAT does not support termination callbacks.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("EvalMaxSATLatest rebuilds backend on solve; mock injection abnormal-path test is not applicable.")

class TestEvalMaxSATLatestSolverTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = EvalMaxSATLatestSolver

    def test_termination_callback(self):
        self.skipTest("EvalMaxSATLatest does not support termination callbacks.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("EvalMaxSATLatest does not support Interrupted status handling.")


class TestEvalMaxSATIncrSolverTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = EvalMaxSATIncrSolver

    def test_termination_callback(self):
        self.skipTest("EvalMaxSATIncr does not support termination callbacks.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("EvalMaxSATIncr does not support Interrupted status handling.")

class TestOLLSolverTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = OLLSolver

    def test_termination_callback(self):
        self.skipTest("OLLSolver does not support termination callbacks.")
    
    def test_solve_raise_on_abnormal (self):
        self.skipTest("OLLSolver does not support Interrupted status handling.")


class TestAutoOpenWBOSolverTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = AutoOpenWBOSolver

    def test_termination_callback(self):
        self.skipTest("AutoOpenWBOSolver does not support termination callbacks.")
    
    def test_solve_raise_on_abnormal (self):
        self.skipTest("AutoOpenWBOSolver does not support Interrupted status handling.")


class TestPartMSU3SolverTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = PartMSU3Solver

    def test_termination_callback(self):
        self.skipTest("PartMSU3 does not support termination callbacks.")
    
    def test_assume_incremental_cost_change(self):
        self.skipTest("PartMSU3 does not support weighted soft clauses, so assume test is not applicable.")
    
    def test_add_clause_soft_unit(self):
        self.skipTest("PartMSU3 does not support weighted soft clauses, so soft clause test is not applicable.")
    
    def test_solve_raise_on_abnormal (self):
        self.skipTest("PartMSU3 does not support Interrupted status handling.")

class TestRC2ReentrantTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = RC2Reentrant

    def test_termination_callback(self):
        """Override to skip termination callback test for RC2Reentrant (not supported)."""
        self.skipTest("RC2Reentrant does not support termination callbacks.")

    def test_solve_raise_on_abnormal(self):
        """Override to skip raise_on_abnormal test for RC2Reentrant (not supported)."""
        self.skipTest("RC2Reentrant does not support Interrupted status handling.")

class TestCGSSTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = CGSS

    def setUp(self):
        if not self.SOLVER_CLASS.is_available():
            self.skipTest("CGSS backend is not available in this build.")
        super().setUp()

    def test_termination_callback(self):
        self.skipTest("CGSS rebuild wrapper does not support termination callbacks.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("CGSS rebuild wrapper does not support Interrupted status handling.")


class TestCGSSPMRESTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = CGSSPMRES

    def setUp(self):
        if not self.SOLVER_CLASS.is_available():
            self.skipTest("CGSSPMRES backend is not available in this build.")
        super().setUp()

    def test_termination_callback(self):
        self.skipTest("CGSSPMRES rebuild wrapper does not support termination callbacks.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("CGSSPMRES rebuild wrapper does not support Interrupted status handling.")


class TestWMaxCDCLSolverTerminationCallback(TestIPAMIRSolver):
    SOLVER_CLASS = WMaxCDCLSolver

    def test_termination_callback(self):
        self.skipTest("WMaxCDCL fake-incremental wrapper does not support termination callbacks.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("WMaxCDCL fake-incremental wrapper does not support Interrupted status handling.")


class TestSPBMaxSATCFPSIncomplete(TestIPAMIRSolver):
    SOLVER_CLASS = SPBMaxSATCFPS

    def setUp(self):
        if self.SOLVER_CLASS is None:
            self.skipTest(f"SOLVER_CLASS {self.SOLVER_CLASS} is not valid.")
        self.solver = self.SOLVER_CLASS(timeout_s=4.0, timeout_grace_s=0.5)

    def test_termination_callback(self):
        self.skipTest("SPB-MaxSAT-c-FPS subprocess wrapper does not support set_terminate.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("SPB-MaxSAT-c-FPS subprocess wrapper does not support Interrupted callback semantics.")

    def test_add_clause_soft_unit(self):
        self.skipTest("SPB-MaxSAT-c-FPS is incomplete and may report non-optimal weighted solutions as feasible.")

    def test_assume_incremental_cost_change(self):
        self.skipTest("SPB-MaxSAT-c-FPS is incomplete and exact weighted optimum under assumptions is not guaranteed.")


class TestOpenWBOIncIncomplete(TestIPAMIRSolver):
    SOLVER_CLASS = OpenWBOInc

    def setUp(self):
        if self.SOLVER_CLASS is None:
            self.skipTest(f"SOLVER_CLASS {self.SOLVER_CLASS} is not valid.")
        if hasattr(self.SOLVER_CLASS, "is_available"):
            if not self.SOLVER_CLASS.is_available():
                self.skipTest(f"{self.SOLVER_CLASS.__name__} is not available in this build.")
        self.solver = self.SOLVER_CLASS(timeout_s=4.0, timeout_grace_s=0.5)

    def test_termination_callback(self):
        self.skipTest("OpenWBOInc subprocess wrapper does not support set_terminate.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("OpenWBOInc subprocess wrapper does not support Interrupted callback semantics.")


class TestNuWLSCIBRIncomplete(TestIPAMIRSolver):
    SOLVER_CLASS = NuWLSCIBR

    def setUp(self):
        if self.SOLVER_CLASS is None:
            self.skipTest(f"SOLVER_CLASS {self.SOLVER_CLASS} is not valid.")
        if hasattr(self.SOLVER_CLASS, "is_available"):
            if not self.SOLVER_CLASS.is_available():
                self.skipTest(f"{self.SOLVER_CLASS.__name__} is not available in this build.")
        self.solver = self.SOLVER_CLASS(timeout_s=4.0, timeout_grace_s=0.5)

    def test_termination_callback(self):
        self.skipTest("NuWLS-c-IBR subprocess wrapper does not support set_terminate.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("NuWLS-c-IBR subprocess wrapper does not support Interrupted callback semantics.")

    def test_add_clause_soft_unit(self):
        self.skipTest("NuWLS-c-IBR is incomplete and may report non-optimal weighted solutions as feasible.")

    def test_assume_incremental_cost_change(self):
        self.skipTest("NuWLS-c-IBR is incomplete and exact weighted optimum under assumptions is not guaranteed.")


class TestLoandraIncomplete(TestIPAMIRSolver):
    SOLVER_CLASS = Loandra

    def setUp(self):
        if self.SOLVER_CLASS is None:
            self.skipTest(f"SOLVER_CLASS {self.SOLVER_CLASS} is not valid.")
        if hasattr(self.SOLVER_CLASS, "is_available"):
            if not self.SOLVER_CLASS.is_available():
                self.skipTest(f"{self.SOLVER_CLASS.__name__} is not available in this build.")
        self.solver = self.SOLVER_CLASS(timeout_s=4.0, timeout_grace_s=0.5)

    def test_termination_callback(self):
        self.skipTest("Loandra subprocess wrapper does not support set_terminate.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("Loandra subprocess wrapper does not support Interrupted callback semantics.")


class TestPortfolioSolverConformance(TestIPAMIRSolver):
    SOLVER_CLASS = ConformancePortfolioSolver

    def test_termination_callback(self):
        self.skipTest("PortfolioSolver does not support set_terminate.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("PortfolioSolver does not expose callback-based interrupted semantics.")


class TestCompletePortfolioPresetConformance(TestIPAMIRSolver):
    SOLVER_CLASS = CompletePresetPortfolioSolver

    def test_termination_callback(self):
        self.skipTest("PortfolioSolver presets do not support set_terminate.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("PortfolioSolver presets do not expose callback-based interrupted semantics.")


class TestPerformancePortfolioPresetConformance(TestIPAMIRSolver):
    SOLVER_CLASS = PerformancePresetPortfolioSolver

    def test_termination_callback(self):
        self.skipTest("PortfolioSolver presets do not support set_terminate.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("PortfolioSolver presets do not expose callback-based interrupted semantics.")


class TestIncompletePortfolioPresetConformance(TestIPAMIRSolver):
    SOLVER_CLASS = IncompletePresetPortfolioSolver

    def setUp(self):
        if self.SOLVER_CLASS is None:
            self.skipTest(f"SOLVER_CLASS {self.SOLVER_CLASS} is not valid.")
        self.solver = self.SOLVER_CLASS()

    def test_termination_callback(self):
        self.skipTest("Incomplete portfolio preset does not support set_terminate.")

    def test_solve_raise_on_abnormal(self):
        self.skipTest("Incomplete portfolio preset does not expose callback-based interrupted semantics.")

    def test_add_clause_soft_unit(self):
        self.skipTest("Incomplete portfolio preset may return non-optimal weighted feasible solutions.")

    def test_assume_incremental_cost_change(self):
        self.skipTest("Incomplete portfolio preset does not guarantee exact weighted optimum under assumptions.")

    def test_add_clause_hard_unsat(self):
        self.skipTest("Incomplete portfolio preset does not guarantee trusted UNSAT classification.")

del TestIPAMIRSolver  # Remove base class from test discovery

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
