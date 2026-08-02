import unittest
import aperture as ap

class TestOBVSolving(unittest.TestCase):
    def test_solve_simple_obv(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        bit_vector = ap.lits([v1, v2, v3])
        assumps = ap.lits([])

        sat = solver.solve_obv(assumptions=assumps, targets=bit_vector)

        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.lit_value(v1), -v1)
        self.assertEqual(solver.lit_value(v2), -v2)
        self.assertEqual(solver.lit_value(v3), -v3)

    def test_constrained_obv(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()

        bit_vector = ap.lits([v1, v2, v3, v4])
        assumps = ap.lits([])

        self.assertTrue(solver.add_clause([v1, v2, v3, v4]))

        sat = solver.solve_obv(assumptions=assumps, targets=bit_vector)

        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.lit_value(v1), -v1)
        self.assertEqual(solver.lit_value(v2), -v2)
        self.assertEqual(solver.lit_value(v3), -v3)
        self.assertEqual(solver.lit_value(v4), v4)
    
    def test_multiple_constrained_obv(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()

        bit_vector = ap.lits([v1, v2, v3, v4])
        assumps = ap.lits([])

        self.assertTrue(solver.add_clause(ap.lits([v1, v2, v3, v4])))
        self.assertTrue(solver.add_constraint_less_than(lits=bit_vector, rhs=3))
        self.assertTrue(solver.add_constraint_greater_than(lits=bit_vector, rhs=1))

        sat = solver.solve_obv(assumptions=assumps, targets=bit_vector)

        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.lit_value(v1), -v1)
        self.assertEqual(solver.lit_value(v2), -v2)
        self.assertEqual(solver.lit_value(v3), v3)
        self.assertEqual(solver.lit_value(v4), v4)

if __name__ == '__main__':     unittest.main()