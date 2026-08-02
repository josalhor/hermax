import unittest
import aperture as ap

class TestPseudoBooleanConstraints(unittest.TestCase):
    def test_simple_pb(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        selector = solver.new_var()

        pb_lits = ap.wlits([(1, v1), (1, v2)])
        self.assertTrue(solver.add_constraint_less_than(wlits=pb_lits, rhs=2, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        total_weight = sum(weight for weight, lit in pb_lits if solver.lit_value(lit) == lit)
        self.assertLess(total_weight, 2)

        pb_lits = ap.wlits([(2, v3), (3, v4)])
        self.assertTrue(solver.add_constraint_less_than_equal(wlits=pb_lits, rhs=2, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        total_weight = sum(weight for weight, lit in pb_lits if solver.lit_value(lit) == lit)
        self.assertLessEqual(total_weight, 2)

        pb_lits = ap.wlits([(2, solver.new_var()), (3, solver.new_var()), (4, solver.new_var())])
        self.assertTrue(solver.add_constraint_less_than(wlits=pb_lits, rhs=8, selector=selector))
        assumps = ap.lits([-selector])
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        total_weight = sum(weight for weight, lit in pb_lits if solver.lit_value(lit) == lit)
        self.assertLess(total_weight, 8)

    def test_invalid_cases(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        selector = solver.new_var()

        wlits = ap.wlits([(1, v1), (1, v2)])
        self.assertFalse(solver.add_constraint_less_than(wlits=wlits, rhs=0, selector=selector))
        self.assertFalse(solver.add_constraint_less_than_equal(wlits=wlits, rhs=0, selector=selector))


if __name__ == '__main__':     unittest.main()