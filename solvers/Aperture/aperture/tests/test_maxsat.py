import unittest
import aperture as ap

class TestMaxSATSolving(unittest.TestCase):
    def test_unweighted_maxsat_solving(self):
        solver = ap.Solver(sat_solver="topor")
        self.assertIsNotNone(solver)

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        hard_clause_1 = ap.lits([v1, v2])
        hard_clause_2 = ap.lits([-v2, v3])

        soft_clause_1 = ap.lits([-v1])
        soft_clause_2 = ap.lits([-v3])

        v4 = solver.new_var()
        v5 = solver.new_var()

        soft_clause_1.append(v4)
        soft_clause_2.append(v5)

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        soft_lits = ap.lits([v4, v5])
        assumptions = ap.lits([])

        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 1)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertFalse(fixed_model_value)

    def test_weighted_maxsat_solving(self):
        solver = ap.Solver(sat_solver="topor")
        self.assertIsNotNone(solver)

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        hard_clause_1 = ap.lits([v1, v2])
        hard_clause_2 = ap.lits([-v2, v3])

        soft_clause_1 = ap.lits([-v1])
        soft_clause_2 = ap.lits([-v3])

        v4 = solver.new_var()
        v5 = solver.new_var()

        soft_clause_1.append(v4)
        soft_clause_2.append(v5)

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        soft_wlits = ap.wlits([(9, v4), (4, v5)])
        assumptions = ap.lits([])

        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 4)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertFalse(fixed_model_value)

    def test_solve_maxsat_incrementally(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        hard_clause_1 = ap.lits([v1, v2])
        hard_clause_2 = ap.lits([-v2, v3])

        soft_clause_1 = ap.lits([-v1])
        soft_clause_2 = ap.lits([-v3])

        v4 = solver.new_var()
        v5 = solver.new_var()

        soft_clause_1.append(v4)
        soft_clause_2.append(v5)

        soft_lits = ap.lits([v4, v5])

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        sat = solver.solve_maxsat(ap.lits([]), soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 1)

        # Add another soft clause
        soft_clause_3 = ap.lits([-v1, -v3])
        v6 = solver.new_var()
        soft_clause_3.append(v6)
        self.assertTrue(solver.add_clause(soft_clause_3))
        soft_lits.append(v6)

        sat = solver.solve_maxsat(ap.lits([]), soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 1)

    def test_solve_maxsat_incrementally_new_vars_and_result_value(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        hard_clause_1 = ap.lits([v1, v2])
        hard_clause_2 = ap.lits([-v2, v3])

        soft_clause_1 = ap.lits([-v1])
        soft_clause_2 = ap.lits([-v3])

        v4 = solver.new_var()
        v5 = solver.new_var()

        soft_clause_1.append(v4)
        soft_clause_2.append(v5)

        soft_lits = ap.lits([v4, v5])

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        sat = solver.solve_maxsat(ap.lits([]), soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 1)

        # Add new variables and clauses
        v6 = solver.new_var()
        v7 = solver.new_var()
        v8 = solver.new_var()

        hard_clause_3 = ap.lits([v6, v7])
        hard_clause_4 = ap.lits([-v7, v8])

        soft_clause_3 = ap.lits([-v6])
        soft_clause_4 = ap.lits([-v8])

        v9 = solver.new_var()
        v10 = solver.new_var()

        soft_clause_3.append(v9)
        soft_clause_4.append(v10)

        soft_lits.append(v9)
        soft_lits.append(v10)

        self.assertTrue(solver.add_clause(hard_clause_3))
        self.assertTrue(solver.add_clause(hard_clause_4))
        self.assertTrue(solver.add_clause(soft_clause_3))
        self.assertTrue(solver.add_clause(soft_clause_4))

        sat = solver.solve_maxsat(ap.lits([]), soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 2)

    def test_solve_maxsat_with_assumptions(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        hard_clause_1 = ap.lits([v1, v2])
        hard_clause_2 = ap.lits([-v2, v3])

        soft_clause_1 = ap.lits([-v1])
        soft_clause_2 = ap.lits([-v3])

        v4 = solver.new_var()
        v5 = solver.new_var()

        soft_clause_1.append(v4)
        soft_clause_2.append(v5)

        soft_lits = ap.lits([v4, v5])

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        assumptions = ap.lits([v1, v3])

        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 2)

        assumptions = ap.lits([-v1, v3])
        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 1)

        assumptions = ap.lits([v1, -v3])
        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 1)

    def test_solve_weighted_maxsat_with_assumptions(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        hard_clause_1 = ap.lits([v1, v2])
        hard_clause_2 = ap.lits([-v2, v3])

        soft_clause_1 = ap.lits([-v1])
        soft_clause_2 = ap.lits([-v3])

        v4 = solver.new_var()
        v5 = solver.new_var()

        soft_clause_1.append(v4)
        soft_clause_2.append(v5)

        soft_wlits = ap.wlits([(9, v4), (4, v5)])

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        assumptions = ap.lits([v1, v3])

        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 13)

        assumptions = ap.lits([-v1, v3])
        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 4)

        assumptions = ap.lits([v1, -v3])
        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 9)

    def test_maxsat_soft_literals_assumed(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()

        hard_clause = ap.lits([v1, v2])

        soft_clause_1 = ap.lits([-v1])
        soft_clause_2 = ap.lits([-v2])

        v3 = solver.new_var()
        v4 = solver.new_var()

        soft_clause_1.append(v3)
        soft_clause_2.append(v4)

        soft_lits = ap.lits([v3, v4])

        self.assertTrue(solver.add_clause(hard_clause))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        assumptions = ap.lits([v3, v4])

        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 2)

        assumptions = ap.lits([-v3, v4])
        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 1)

        assumptions = ap.lits([v3, -v4])
        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 1)

        assumptions = ap.lits([-v3, -v4])
        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)
        self.assertFalse(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "UNSAT")

    def test_maxsat_weighted_soft_literals_assumed(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()

        hard_clause = ap.lits([v1, v2])

        soft_clause_1 = ap.lits([-v1])
        soft_clause_2 = ap.lits([-v2])

        v3 = solver.new_var()
        v4 = solver.new_var()

        soft_clause_1.append(v3)
        soft_clause_2.append(v4)

        soft_wlits = ap.wlits([(5, v3), (10, v4)])

        self.assertTrue(solver.add_clause(hard_clause))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        assumptions = ap.lits([v3, v4])

        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 15)

        assumptions = ap.lits([-v3, v4])
        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 10)

        assumptions = ap.lits([v3, -v4])
        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 5)

        assumptions = ap.lits([-v3, -v4])
        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)
        self.assertFalse(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "UNSAT")

    def test_complex_lits_and_assumptions_maxsat(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        v5 = solver.new_var()
        v6 = solver.new_var()
        v7 = solver.new_var()
        v8 = solver.new_var()

        hard_clause_1 = ap.lits([v1, -v2, v3])
        hard_clause_2 = ap.lits([-v3, v4, v5])
        hard_clause_3 = ap.lits([-v5, -v6, v7])
        hard_clause_4 = ap.lits([-v7, v8])

        soft_clause_1 = ap.lits([-v1, v6])
        soft_clause_2 = ap.lits([-v4, -v8])

        v9 = solver.new_var()
        v10 = solver.new_var()

        soft_clause_1.append(v9)
        soft_clause_2.append(v10)

        soft_lits = ap.lits([v9, v10])

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(hard_clause_3))
        self.assertTrue(solver.add_clause(hard_clause_4))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        assumptions = ap.lits([v2, -v4, v6, v8])
        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

        assumptions = ap.lits([-v2, -v4, v6, v8])
        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

        assumptions = ap.lits([v2, v4, v6, -v8])
        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

        assumptions = ap.lits([-v2, v4, -v6, -v8])
        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

    def test_complex_lits_and_assumptions_weighted_maxsat(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()
        v5 = solver.new_var()
        v6 = solver.new_var()
        v7 = solver.new_var()
        v8 = solver.new_var()

        hard_clause_1 = ap.lits([v1, -v2, v3])
        hard_clause_2 = ap.lits([-v3, v4, v5])
        hard_clause_3 = ap.lits([-v5, -v6, v7])
        hard_clause_4 = ap.lits([-v7, v8])

        soft_clause_1 = ap.lits([-v1, v6])
        soft_clause_2 = ap.lits([-v4, -v8])

        v9 = solver.new_var()
        v10 = solver.new_var()

        soft_clause_1.append(v9)
        soft_clause_2.append(v10)

        soft_wlits = ap.wlits([(3, v9), (7, v10)])

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(hard_clause_3))
        self.assertTrue(solver.add_clause(hard_clause_4))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        assumptions = ap.lits([v2, -v4, v6, v8])
        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

        assumptions = ap.lits([-v2, -v4, v6, v8])
        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

        assumptions = ap.lits([v2, v4, v6, -v8])
        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

        assumptions = ap.lits([-v2, v4, -v6, -v8])
        sat = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)
        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

    def test_no_soft_literals_maxsat(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()

        hard_clause = ap.lits([v1, v2])

        self.assertTrue(solver.add_clause(hard_clause))

        soft_lits = ap.lits([])

        sat = solver.solve_maxsat(ap.lits([]), soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

    def test_no_soft_literals_weighted_maxsat(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()

        hard_clause = ap.lits([v1, v2])

        self.assertTrue(solver.add_clause(hard_clause))

        soft_wlits = ap.wlits([])

        sat = solver.solve_weighted_maxsat(ap.lits([]), soft_wlits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

    def test_maxsat_with_no_hard_clauses(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()

        soft_clause_1 = ap.lits([v1])
        soft_clause_2 = ap.lits([v2])

        v3 = solver.new_var()
        v4 = solver.new_var()

        soft_clause_1.append(v3)
        soft_clause_2.append(v4)

        soft_lits = ap.lits([v3, v4])

        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        sat = solver.solve_maxsat(ap.lits([]), soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

    def test_maxsat_multiple_clauses_for_same_soft_lit(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        soft_clause_1 = ap.lits([v1, v3])
        soft_clause_2 = ap.lits([v3, v2])

        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        soft_lits = ap.lits([v3])
        assumptions = ap.lits([v1, v2, -v3])

        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)

        self.assertTrue(sat)
        status = solver.get_latest_solve_status()
        self.assertEqual(status, "SAT")
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)

    def test_maxsat_fixing_model_value_with_zero_cost(self):
        solver = ap.Solver(sat_solver="topor")

        soft_lits = ap.lits([solver.new_var(), solver.new_var()])
        assumptions = ap.lits([])

        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=False)
        self.assertTrue(sat)
        self.assertTrue(solver.is_latest_maxsat_optimal())
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertFalse(fixed_model_value)

        sat = solver.solve_maxsat(assumptions, soft_lits, fix_model_value=True)
        self.assertTrue(sat)
        self.assertTrue(solver.is_latest_maxsat_optimal())
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertTrue(fixed_model_value)

    def test_maxsat_fixing_model_value_with_non_zero_cost(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()

        hard_clause_1 = ap.lits([v1, v2])
        hard_clause_2 = ap.lits([-v2, v3])

        soft_clause_1 = ap.lits([-v1])
        soft_clause_2 = ap.lits([-v3])

        v4 = solver.new_var()
        v5 = solver.new_var()

        soft_clause_1.append(v4)
        soft_clause_2.append(v5)

        soft_wlits = ap.wlits([(9, v4), (4, v5)])

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))

        sat = solver.solve_weighted_maxsat(ap.lits([]), soft_wlits, fix_model_value=False)
        self.assertTrue(sat)
        self.assertTrue(solver.is_latest_maxsat_optimal())
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 4)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertFalse(fixed_model_value)

        assumptions = ap.lits([v1])

        sat2 = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=False)
        self.assertTrue(sat2)
        self.assertTrue(solver.is_latest_maxsat_optimal())
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 9)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertFalse(fixed_model_value)

        sat3 = solver.solve_weighted_maxsat(ap.lits([]), soft_wlits, fix_model_value=True)
        self.assertTrue(sat3)
        self.assertTrue(solver.is_latest_maxsat_optimal())
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 4)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertTrue(fixed_model_value)

        sat4 = solver.solve_weighted_maxsat(assumptions, soft_wlits, fix_model_value=True)
        self.assertFalse(sat4)

    def test_maxsat_fixing_model_value_clusters(self):
        solver = ap.Solver(sat_solver="topor")

        v1 = solver.new_var()
        v2 = solver.new_var()
        v3 = solver.new_var()
        v4 = solver.new_var()

        hard_clause_1 = ap.lits([v1, v2])
        hard_clause_2 = ap.lits([-v2, v3])

        soft_clause_1 = ap.lits([-v4])
        soft_clause_2 = ap.lits([-v1])
        soft_clause_3 = ap.lits([-v3])

        v5 = solver.new_var()
        v6 = solver.new_var()
        v7 = solver.new_var()

        soft_clause_1.append(v5)
        soft_clause_2.append(v6)
        soft_clause_3.append(v7)

        self.assertTrue(solver.add_clause(hard_clause_1))
        self.assertTrue(solver.add_clause(hard_clause_2))
        self.assertTrue(solver.add_clause(soft_clause_1))
        self.assertTrue(solver.add_clause(soft_clause_2))
        self.assertTrue(solver.add_clause(soft_clause_3))

        cluster_1 = ap.wlits([(14, v5)])
        cluster_2 = ap.wlits([(9, v6), (4, v7)])

        sat = solver.solve_weighted_maxsat(ap.lits([]), cluster_1, fix_model_value=True)
        self.assertTrue(sat)
        self.assertTrue(solver.is_latest_maxsat_optimal())
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 0)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertTrue(fixed_model_value)

        sat2 = solver.solve_weighted_maxsat(ap.lits([]), cluster_2, fix_model_value=False)
        self.assertTrue(sat2)
        self.assertTrue(solver.is_latest_maxsat_optimal())
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 4)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertFalse(fixed_model_value)

        assumptions = ap.lits([v4])
        sat3 = solver.solve_weighted_maxsat(assumptions, cluster_2, fix_model_value=True)
        self.assertFalse(sat3)

        sat4 = solver.solve_weighted_maxsat(ap.lits([]), cluster_2, fix_model_value=True)
        self.assertTrue(sat4)
        self.assertTrue(solver.is_latest_maxsat_optimal())
        value = solver.get_latest_maxsat_value()
        self.assertEqual(value, 4)
        fixed_model_value = solver.is_latest_maxsat_fixed_model_value()
        self.assertTrue(fixed_model_value)

        assumptions = ap.lits([v1])
        sat5 = solver.solve_weighted_maxsat(assumptions, cluster_1, fix_model_value=True)
        self.assertFalse(sat5)


if __name__ == '__main__':
    unittest.main()