import unittest
import aperture as ap

class TestBlackBoxSolving(unittest.TestCase):
    def test_solve_black_box(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        self.assertTrue(solver.add_clause([v1, v2]))
        self.assertTrue(solver.add_clause([-v2, v3]))

        def pb_func(lit_value_func):
            cost = 0
            for lit in [v1, v2, v3]:
                val = lit_value_func(lit)
                if val == lit:
                    cost += 1
            return cost

        observables = ap.lits([v1, v3])

        sat = solver.solve_black_box(assumptions=ap.lits([]), observables=observables, pb_func=pb_func)

        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.get_latest_black_box_value(), 1)
    
    def test_solve_black_box_unsat(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()

        self.assertTrue(solver.add_clause([v1]))
        self.assertTrue(solver.add_clause([-v1]))
        self.assertTrue(solver.add_clause([v2]))
        self.assertTrue(solver.add_clause([-v2]))

        def pb_func(lit_value_func):
            cost = 0
            for lit in [v1, v2]:
                val = lit_value_func(lit)
                if val == lit:
                    cost += 1
            return cost

        observables = ap.lits([v1, v2])

        sat = solver.solve_black_box(assumptions=ap.lits([]), observables=observables, pb_func=pb_func)

        self.assertFalse(sat)
        self.assertEqual(solver.get_latest_solve_status(), "UNSAT")

    def test_solve_black_box_no_observables(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()

        self.assertTrue(solver.add_clause([v1]))

        observables = ap.lits([])

        def pb_func(lit_value_func):
            return sum(1 for lit in observables if lit_value_func(lit) == lit)

        sat = solver.solve_black_box(assumptions=ap.lits([]), observables=observables, pb_func=pb_func)

        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.get_latest_black_box_value(), 0)
    
    def test_solve_black_box_with_assumptions(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        v5 = solver.new_var()

        c1 = ap.lits([v1, v2])
        c2 = ap.lits([-v2, v3])
        c3 = ap.lits([v4, v5])

        self.assertTrue(solver.add_clause(c1))
        self.assertTrue(solver.add_clause(c2))
        self.assertTrue(solver.add_clause(c3))

        def pb_func(lit_value_func):
            cost = 0
            for lit in [v1, v3, v4, v5]:
                val = lit_value_func(lit)
                if val == lit:
                    cost += 1
            return cost
        
        observables = ap.lits([v1, v3, v4, v5])
        assumptions = ap.lits([-v2])
        sat = solver.solve_black_box(assumptions=assumptions, observables=observables, pb_func=pb_func)
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.get_latest_black_box_value(), 2)
    
    def test_solve_black_box_call_back(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()

        self.assertTrue(solver.add_clause([v1, v2]))

        def pb_func(lit_value_func):
            cost = 0
            for lit in [v1, v2]:
                val = lit_value_func(lit)
                if val == lit:
                    cost += 1
            return cost

        observables = ap.lits([v1, v2])

        callback_count = 0

        def callback(observables):
            nonlocal callback_count
            callback_count += 1
            return True

        sat = solver.solve_black_box(assumptions=ap.lits([]), observables=observables, 
                                     pb_func=pb_func, callback_on_solution_found=callback)

        self.assertTrue(sat)
        self.assertEqual(callback_count, 1)
        self.assertGreaterEqual(solver.get_latest_black_box_value(), 1)

    def test_solve_black_box_complex_pb(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        self.assertTrue(solver.add_clause([v1, v2, v3]))

        def pb_func(lit_value_func):
            cost = 0
            for lit in [v1, v2, v3]:
                val = lit_value_func(lit)
                if val == lit:
                    cost += lit
            return cost
        
        observables = ap.lits([v1, v2, v3])

        sat = solver.solve_black_box(assumptions=ap.lits([]), observables=observables, pb_func=pb_func)

        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertLess(solver.get_latest_black_box_value(), 4)

    def test_solve_black_box_incremental_calls(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()

        self.assertTrue(solver.add_clause([v1, v2]))

        def pb_func(lit_value_func):
            cost = 0
            for lit in [v1, v2]:
                val = lit_value_func(lit)
                if val == lit:
                    cost += 1
            return cost

        observables = ap.lits([v1, v2])

        # First call
        sat1 = solver.solve_black_box(assumptions=ap.lits([]), observables=observables, pb_func=pb_func)
        self.assertTrue(sat1)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.get_latest_black_box_value(), 1)

        # Second call with additional clause
        self.assertTrue(solver.add_clause([-v1]))
        sat2 = solver.solve_black_box(assumptions=ap.lits([]), observables=observables, pb_func=pb_func)
        self.assertTrue(sat2)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertEqual(solver.get_latest_black_box_value(), 1)

    def test_solve_black_box_incremental_complex_calls(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        self.assertTrue(solver.add_clause([v1, v2, v3]))

        def pb_func(lit_value_func):
            cost = 0
            for lit in [v1, v2, v3]:
                val = lit_value_func(lit)
                if val == lit:
                    cost += lit
            return cost
        
        observables = ap.lits([v1, v2, v3])

        # First call
        sat1 = solver.solve_black_box(assumptions=ap.lits([]), observables=observables, pb_func=pb_func)
        self.assertTrue(sat1)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertLess(solver.get_latest_black_box_value(), 3)

        # Second call with additional clause
        self.assertTrue(solver.add_clause([-v1, -v2]))
        sat2 = solver.solve_black_box(assumptions=ap.lits([]), observables=observables, pb_func=pb_func)
        self.assertTrue(sat2)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        self.assertLess(solver.get_latest_black_box_value(), 3)

if __name__ == '__main__':     unittest.main()