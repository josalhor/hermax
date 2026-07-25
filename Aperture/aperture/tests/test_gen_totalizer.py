import unittest
import aperture as ap

class TestGenTotalizer(unittest.TestCase):
    def test_simple_getn_totalizer(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        selector = solver.new_var()

        wlits = ap.wlits([(1, v1), (1, v2)])
        totalizer = solver.get_gen_totalizer(wlits=wlits, selector=selector)

        self.assertEqual(len(totalizer), 2)
    
    def test_rhs_simplification(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        selector = solver.new_var()

        wlits = ap.wlits([(1, v1), (1, v2), (1, v3)])
        totalizer = solver.get_gen_totalizer(wlits=wlits, selector=selector, rhs_simplification=2)
        self.assertEqual(len(totalizer), 3)

    def test_complex_gen_totalizer(self):
        solver = ap.Solver(sat_solver="topor")
        lits = ap.lits([])

        for i in range(16):
            lits.append(solver.new_var())
        
        relaxation_vars = ap.lits([])

        for i in range(10):
            relaxation_vars.append(solver.new_var())
        
        wlits = ap.wlits([(10, relaxation_vars[0]), (6, relaxation_vars[1]), (6, relaxation_vars[2]), 
                        (8, relaxation_vars[3]), (8, relaxation_vars[4]), (7, relaxation_vars[5]), 
                        (7, relaxation_vars[6]), (5, relaxation_vars[7]), (5, relaxation_vars[8]), 
                        (4, relaxation_vars[9])])
        self.assertTrue(solver.add_clause([-lits[0], -lits[1], relaxation_vars[0]]))
        self.assertTrue(solver.add_clause([lits[2], relaxation_vars[1]]))
        self.assertTrue(solver.add_clause([-lits[2], relaxation_vars[2]]))
        self.assertTrue(solver.add_clause([lits[4], relaxation_vars[3]]))
        self.assertTrue(solver.add_clause([-lits[4], relaxation_vars[4]]))
        self.assertTrue(solver.add_clause([lits[6], relaxation_vars[5]]))
        self.assertTrue(solver.add_clause([-lits[6], relaxation_vars[6]]))
        self.assertTrue(solver.add_clause([lits[8], relaxation_vars[7]]))
        self.assertTrue(solver.add_clause([-lits[8], relaxation_vars[8]]))
        self.assertTrue(solver.add_clause([-lits[14], relaxation_vars[9]]))

        self.assertTrue(solver.add_clause([lits[0]]))
        self.assertTrue(solver.add_clause([lits[1]]))
        self.assertTrue(solver.add_clause([-lits[2], lits[3]]))
        self.assertTrue(solver.add_clause([-lits[3], lits[4]]))
        self.assertTrue(solver.add_clause([-lits[4], lits[5]]))
        self.assertTrue(solver.add_clause([-lits[5], lits[6]]))
        self.assertTrue(solver.add_clause([-lits[6], lits[7]]))
        self.assertTrue(solver.add_clause([-lits[7], lits[8]]))
        self.assertTrue(solver.add_clause([-lits[8], lits[9]]))
        self.assertTrue(solver.add_clause([-lits[9], lits[10]]))
        self.assertTrue(solver.add_clause([-lits[10], lits[11]]))
        self.assertTrue(solver.add_clause([-lits[11], lits[12]]))
        self.assertTrue(solver.add_clause([-lits[12], lits[13]]))
        self.assertTrue(solver.add_clause([-lits[13], lits[14]]))
        self.assertTrue(solver.add_clause([-lits[14], lits[15]]))

        selector = solver.new_var()

        totalizer = solver.get_gen_totalizer(wlits=wlits, selector=selector, rhs_simplification=40)
        assumptions = ap.lits([-selector])

        sat = solver.solve(assumptions=assumptions)
        
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        
        assumptions.append(-totalizer[-1][1])
        assumptions.append(-totalizer[-2][1])
        sat = solver.solve(assumptions=assumptions)
        assumptions.pop()
        
        self.assertTrue(sat)
        self.assertEqual(solver.get_latest_solve_status(), "SAT")
        totalizer_value = 0
        for weight, lit in wlits:
            if solver.lit_value(lit) == lit:
                totalizer_value += weight
        
        self.assertLess(totalizer_value, 40)

if __name__ == "__main__":  
    unittest.main()