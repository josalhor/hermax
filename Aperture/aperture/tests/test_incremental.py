import unittest
import aperture as ap

class TestIncrementalSolving(unittest.TestCase):
    def test_solve_incremental_sat(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        v5 = solver.new_var()

        lits = ap.lits([v1, v2, v3, v4, v5])

        for i in range(len(lits)):
            assumps = ap.lits(lits[:i])
            sat = solver.solve(assumptions=assumps)
            self.assertTrue(sat)
            self.assertEqual(solver.get_latest_solve_status(), "SAT")

        for i in reversed(range(len(lits))):
            assumps = ap.lits(lits[:i])
            sat = solver.solve(assumptions=assumps)
            self.assertTrue(sat)
            self.assertEqual(solver.get_latest_solve_status(), "SAT")

        solver.add_clause([v1])
        assumps = ap.lits([-v1])
        sat = solver.solve(assumptions=assumps)
        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

        assumps.pop()
        sat = solver.solve(assumptions=assumps)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")

    def test_solve_incremental_unweighted_maxsat(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        v5 = solver.new_var()

        lits = ap.lits([v1, v2, v3, v4, v5])

        for i in range(len(lits)):
            assumps = ap.lits(lits[:i])
            sat = solver.solve_maxsat(assumptions=assumps, soft_lits=lits, fix_model_value=False)
            self.assertTrue(sat)
            self.assertEqual(solver.get_latest_solve_status(), "SAT")
            self.assertEqual(solver.get_latest_maxsat_value(), i)

        for i in reversed(range(len(lits))):
            assumps = ap.lits(lits[:i])
            sat = solver.solve_maxsat(assumptions=assumps, soft_lits=lits, fix_model_value=False)
            self.assertTrue(sat)
            self.assertEqual(solver.get_latest_solve_status(), "SAT")
            self.assertEqual(solver.get_latest_maxsat_value(), i)

        self.assertTrue(solver.add_clause(ap.lits([v1])))
        assumps = ap.lits([-v1])
        sat = solver.solve_maxsat(assumptions=assumps, soft_lits=lits, fix_model_value=False)
        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

        assumps.pop()
        sat = solver.solve_maxsat(assumptions=assumps, soft_lits=lits, fix_model_value=False)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.get_latest_maxsat_value(), 1)

    def test_solve_incremental_blackbox(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        v5 = solver.new_var()

        assumps = ap.lits([])
        observables = ap.lits([v1, v2, v3, v4, v5])

        def pb_func(lit_value_func):
            return sum(lit_value_func(lit) == lit for lit in observables)

        for i in range(len(observables)):
            assumps = ap.lits(observables[:i])
            sat = solver.solve_black_box(assumptions=assumps, observables=observables, pb_func=pb_func)
            self.assertTrue(sat)
            self.assertEqual(solver.get_latest_solve_status(), "SAT")
            self.assertEqual(solver.get_latest_black_box_value(), i)
        
        for i in reversed(range(len(observables))):
            assumps = ap.lits(observables[:i])
            sat = solver.solve_black_box(assumptions=assumps, observables=observables, pb_func=pb_func)
            self.assertTrue(sat)
            self.assertEqual(solver.get_latest_solve_status(), "SAT")
            self.assertEqual(solver.get_latest_black_box_value(), i)
        
        solver.add_clause([v1])
        assumps = ap.lits([-v1])
        sat = solver.solve_black_box(assumptions=assumps, observables=observables, pb_func=pb_func)
        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

        assumps.pop()
        sat = solver.solve_black_box(assumptions=assumps, observables=observables, pb_func=pb_func)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.get_latest_black_box_value(), 1)

    def test_solve_incremental_obv(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        v5 = solver.new_var()

        assumps = ap.lits([])
        bit_vector = ap.lits([v1, -v2, v3, -v4, v5])

        for i in range(len(bit_vector)):
            assumps = ap.lits(bit_vector[:i])
            sat = solver.solve_obv(assumptions=assumps, targets=bit_vector)
            self.assertTrue(sat)
            self.assertEqual(solver.get_latest_solve_status(), "SAT")
            solution = solver.get_latest_solution()
            for i in range(i):
                self.assertEqual(solution[i], bit_vector[i])

        for i in reversed(range(len(bit_vector))):
            assumps = ap.lits(bit_vector[:i])
            sat = solver.solve_obv(assumptions=assumps, targets=bit_vector)
            self.assertTrue(sat)
            self.assertEqual(solver.get_latest_solve_status(), "SAT")
            solution = solver.get_latest_solution()
            for i in range(i):
                self.assertEqual(solution[i], bit_vector[i])
        
        solver.add_clause([v1])
        assumps = ap.lits([-v1])
        sat = solver.solve_obv(assumptions=assumps, targets=bit_vector)
        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

        assumps.pop()
        sat = solver.solve_obv(assumptions=assumps, targets=bit_vector)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        solution = solver.get_latest_solution()
        self.assertEqual(solution[0], v1)

if __name__ == '__main__':    unittest.main()