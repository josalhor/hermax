import unittest
import aperture as ap

class TestSolver(unittest.TestCase):
    def test_init_solver(self):
        solver = ap.Solver()
        self.assertIsNotNone(solver)

        solver = ap.Solver(sat_solver="topor")
        self.assertIsNotNone(solver)

        solver = ap.Solver(sat_solver="glucose")
        self.assertIsNotNone(solver)

        solver = ap.Solver(sat_solver="cadical")
        self.assertIsNotNone(solver)

        self.assertRaises(ValueError, lambda: ap.Solver(sat_solver="kissat"))

        self.assertRaises(ValueError, lambda: ap.Solver(sat_solver="invalid_solver"))

if __name__ == '__main__':    unittest.main()
