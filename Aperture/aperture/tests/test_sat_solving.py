import unittest
import aperture as ap

class TestSatSolving(unittest.TestCase):
    def test_sat_solving(self):
        solver = ap.Solver(sat_solver="topor")
        self.assertIsNotNone(solver)

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        c1 = ap.lits([v1, v2])
        c2 = ap.lits([-v1, v3])
        c3 = ap.lits([-v2, -v3])

        self.assertTrue(solver.add_clause(c1))
        self.assertTrue(solver.add_clause(c2))
        self.assertTrue(solver.add_clause(c3))

        self.assertTrue(solver.solve())

        model = solver.get_latest_solution()
        self.assertEqual(len(model), 3)
    
    def test_sat_solving_unsat(self):
        solver = ap.Solver(sat_solver="topor")
        self.assertIsNotNone(solver)

        v1 = solver.new_var()
        v2 = solver.new_var()

        c1 = ap.lits([v1])
        c2 = ap.lits([-v1])
        c3 = ap.lits([v2])
        c4 = ap.lits([-v2])

        self.assertTrue(solver.add_clause(c1))
        self.assertTrue(solver.add_clause(c2))
        self.assertTrue(solver.add_clause(c3))
        self.assertTrue(solver.add_clause(c4))

        self.assertFalse(solver.solve())

if __name__ == '__main__':    unittest.main()