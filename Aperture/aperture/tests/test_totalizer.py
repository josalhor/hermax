import unittest
import aperture as ap

class TestTotalizer(unittest.TestCase):
    def test_totalizer(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        selector = solver.new_var()

        # Empty lits
        lits = ap.lits([])
        totalizer = solver.get_totalizer(lits=lits, selector=selector)

        self.assertEqual(len(totalizer), 0)

        # One lit
        lits = ap.lits([v1])
        totalizer = solver.get_totalizer(lits=lits, selector=selector)
        self.assertEqual(len(totalizer), 1)
        self.assertIn(v1, totalizer)
        self.assertNotIn(0, totalizer)

        # Two lits
        lits = ap.lits([v1, v2])
        totalizer = solver.get_totalizer(lits=lits, selector=selector)
        self.assertEqual(len(totalizer), 2)
        self.assertNotIn(0, totalizer)
        for lit in totalizer:
            self.assertGreater(lit, selector)

        # Four lits
        lits = ap.lits([v1, v2, v3, v4])
        totalizer = solver.get_totalizer(lits=lits, selector=selector)
        self.assertEqual(len(totalizer), 4)
        self.assertNotIn(0, totalizer)
        for lit in totalizer:
            self.assertGreater(lit, selector)

        # Empty lits with rhs simplification
        lits = ap.lits([])
        totalizer = solver.get_totalizer(lits=lits, selector=selector, rhs_simplification=2)
        self.assertEqual(len(totalizer), 0)

        # One lit with rhs simplification
        lits = ap.lits([v1])
        totalizer = solver.get_totalizer(lits=lits, selector=selector, rhs_simplification=1)
        self.assertEqual(len(totalizer), 1)
        self.assertNotIn(0, totalizer)
        self.assertIn(v1, totalizer)

        # Four lits with rhs simplification
        lits = ap.lits([v1, v2, v3, v4])
        totalizer = solver.get_totalizer(lits=lits, selector=selector, rhs_simplification=2)
        self.assertEqual(len(totalizer), 3)
        self.assertNotIn(0, totalizer)
        for lit in totalizer:
            self.assertGreater(lit, selector)

        # Four lits with large rhs simplification
        lits = ap.lits([v1, v2, v3, v4])
        totalizer = solver.get_totalizer(lits=lits, selector=selector, rhs_simplification=10)
        self.assertEqual(len(totalizer), 4)
        self.assertNotIn(0, totalizer)
        for lit in totalizer:
            self.assertGreater(lit, selector)
        
        # Four lits with rhs simplification of zero
        lits = ap.lits([v1, v2, v3, v4])
        totalizer = solver.get_totalizer(lits=lits, selector=selector, rhs_simplification=0)
        self.assertEqual(len(totalizer), 1)
        self.assertNotIn(0, totalizer)
        for lit in totalizer:
            self.assertGreater(lit, selector)

if __name__ == "__main__":  
    unittest.main()