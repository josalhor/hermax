import unittest
import aperture as ap

class TestCardinalityConstraints(unittest.TestCase):
    def test_cc_less_than(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        selector = solver.new_var()

        # Empty lits
        lits = ap.lits([])
        self.assertFalse(solver.add_constraint_less_than(lits=lits, rhs=1, selector=selector))

        # One lit
        lits = ap.lits([v1])
        self.assertTrue(solver.add_constraint_less_than(lits=lits, rhs=1, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.lit_value(v1), -v1)

        # Three lits
        lits = ap.lits([v2, v3, v4])
        self.assertTrue(solver.add_constraint_less_than(lits=lits, rhs=2, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        true_count = sum(1 for lit in lits if solver.lit_value(lit) == lit)
        self.assertLess(true_count, 2)

        # Four lits, unsat case
        lits = ap.lits([solver.new_var(), solver.new_var(), solver.new_var(), solver.new_var()])
        self.assertTrue(solver.add_constraint_less_than(lits=lits, rhs=2, selector=selector))
        assumps = ap.lits([-selector])
        solver.add_clause([lits[0]])
        solver.add_clause([lits[1]])
        sat = solver.solve(assumptions=assumps)
        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

    def test_cc_less_than_equal(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        selector = solver.new_var()

        # Empty lits
        lits = ap.lits([])
        self.assertFalse(solver.add_constraint_less_than_equal(lits=lits, rhs=0, selector=selector))

        # One lit
        lits = ap.lits([v1])
        self.assertTrue(solver.add_constraint_less_than_equal(lits=lits, rhs=0, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.lit_value(v1), -v1)

        # Three lits
        lits = ap.lits([v2, v3, v4])
        self.assertTrue(solver.add_constraint_less_than_equal(lits=lits, rhs=1, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        true_count = sum(1 for lit in lits if solver.lit_value(lit) == lit)
        self.assertLessEqual(true_count, 1)

        # Four lits, unsat case
        lits = ap.lits([solver.new_var(), solver.new_var(), solver.new_var(), solver.new_var()])
        self.assertTrue(solver.add_constraint_less_than_equal(lits=lits, rhs=2, selector=selector))
        assumps = ap.lits([-selector])
        solver.add_clause([lits[0]])
        solver.add_clause([lits[1]])
        solver.add_clause([lits[2]])
        sat = solver.solve(assumptions=assumps)
        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

    def test_cc_equal(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        selector = solver.new_var()

        # Empty lits
        lits = ap.lits([])
        self.assertFalse(solver.add_constraint_equal(lits=lits, rhs=0, selector=selector))

        # One lit
        lits = ap.lits([v1])
        solver.add_constraint_equal(lits=lits, rhs=1, selector=selector)
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.lit_value(v1), v1)

        # Two lits
        lits = ap.lits([v2, v3])
        self.assertTrue(solver.add_constraint_equal(lits=lits, rhs=1, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        true_count = sum(1 for lit in lits if solver.lit_value(lit) == lit)
        self.assertEqual(true_count, 1)

        # Three lits
        lits = ap.lits([solver.new_var(), solver.new_var(), solver.new_var()])
        self.assertTrue(solver.add_constraint_equal(lits=lits, rhs=2, selector=selector))
        assumps = ap.lits([-selector])
        solver.add_clause([lits[0]])
        solver.add_clause([lits[1]])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        true_count = sum(1 for lit in lits if solver.lit_value(lit) == lit)
        self.assertEqual(true_count, 2)

        # Four lits, unsat case
        lits = ap.lits([solver.new_var(), solver.new_var(), solver.new_var(), solver.new_var()])
        self.assertTrue(solver.add_constraint_equal(lits=lits, rhs=2, selector=selector))
        assumps = ap.lits([-selector])
        solver.add_clause([lits[0]])
        solver.add_clause([lits[1]])
        solver.add_clause([lits[2]])
        sat = solver.solve(assumptions=assumps)
        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

    def test_cc_greater_than_equal(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        selector = solver.new_var()

        # Empty lits
        lits = ap.lits([])
        self.assertFalse(solver.add_constraint_greater_than_equal(lits=lits, rhs=0, selector=selector))

        # One lit
        lits = ap.lits([v1])
        solver.add_constraint_greater_than_equal(lits=lits, rhs=1, selector=selector)
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.lit_value(v1), v1)

        # Three lits
        lits = ap.lits([v2, v3, v4])
        self.assertTrue(solver.add_constraint_greater_than_equal(lits=lits, rhs=1, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        true_count = sum(1 for lit in lits if solver.lit_value(lit) == lit)
        self.assertGreaterEqual(true_count, 1)

        # Four lits, unsat case
        lits = ap.lits([solver.new_var(), solver.new_var(), solver.new_var(), solver.new_var()])
        self.assertTrue(solver.add_constraint_greater_than_equal(lits=lits, rhs=4, selector=selector))
        assumps = ap.lits([-selector])
        solver.add_clause([-lits[0]])
        solver.add_clause([-lits[1]])
        solver.add_clause([-lits[2]])
        sat = solver.solve(assumptions=assumps)
        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

    def test_cc_greater_than(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        selector = solver.new_var()

        # Empty lits
        lits = ap.lits([])
        self.assertFalse(solver.add_constraint_greater_than(lits=lits, rhs=0, selector=selector))

        # One lit
        lits = ap.lits([v1])
        self.assertTrue(solver.add_constraint_greater_than(lits=lits, rhs=0, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.lit_value(v1), v1)

        # Three lits
        lits = ap.lits([v2, v3, v4])
        self.assertTrue(solver.add_constraint_greater_than(lits=lits, rhs=1, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        true_count = sum(1 for lit in lits if solver.lit_value(lit) == lit)
        self.assertGreater(true_count, 1)

        # Four lits, unsat case
        lits = ap.lits([solver.new_var(), solver.new_var(), solver.new_var(), solver.new_var()])
        self.assertTrue(solver.add_constraint_greater_than(lits=lits, rhs=3, selector=selector))
        assumps = ap.lits([-selector])
        solver.add_clause([-lits[0]])
        sat = solver.solve(assumptions=assumps)
        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

    def test_invalid_cases(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        selector = solver.new_var()

        # Less Than with rhs 0
        lits = ap.lits([v1])
        self.assertFalse(solver.add_constraint_less_than(lits=lits, rhs=0, selector=selector))
        # Equal with rhs greater than lits size
        self.assertFalse(solver.add_constraint_equal(lits=lits, rhs=2, selector=selector))
        # Greater Than Equal with rhs greater than lits size
        self.assertFalse(solver.add_constraint_greater_than_equal(lits=lits, rhs=2, selector=selector))
        # Greater Than with rhs greater than or equal to lits size
        self.assertFalse(solver.add_constraint_greater_than(lits=lits, rhs=1, selector=selector))


if __name__ == '__main__':
    unittest.main()