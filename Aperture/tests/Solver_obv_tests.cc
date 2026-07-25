#include <gtest/gtest.h>

#include <chrono>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>

#include "Aperture.h"
#include "solvers/cadical/Solver.h"
#include "solvers/glucose/Solver.h"
#include "solvers/topor/Solver.h"

using namespace std;
using namespace Aperture;
using TLit = int32_t;
using TWeight = uint64_t;

TEST(ObvTest, TestSolveSimpleObv) {
  unique_ptr<SatSolver<TLit>> sat_solver = make_unique<ToporSatSolver<TLit>>();
  unique_ptr<Solver<TLit>> solver = make_unique<Solver<TLit>>(move(sat_solver));

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> bit_vector = {v1, v2, v3};
  vector<TLit> assumps = {};

  SolverStatus status = solver->SolveOBV(assumps, bit_vector);

  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v2), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v3), TLitValue::FALSE);
}

TEST(ObvTest, TestSolveObvUnsat) {
  unique_ptr<SatSolver<TLit>> sat_solver = make_unique<ToporSatSolver<TLit>>();
  unique_ptr<Solver<TLit>> solver = make_unique<Solver<TLit>>(move(sat_solver));

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> bit_vector = {v1, v2};
  vector<TLit> assumps = {};

  vector<TLit> clause1 = {-v1};
  vector<TLit> clause2 = {v1};

  solver->AddClause(clause1);
  solver->AddClause(clause2);

  SolverStatus status = solver->SolveOBV(assumps, bit_vector);

  ASSERT_EQ(status, SolverStatus::UNSAT);
}

TEST(ObvTest, TestSolveObvWithAssumptions) {
  unique_ptr<SatSolver<TLit>> sat_solver = make_unique<ToporSatSolver<TLit>>();
  unique_ptr<Solver<TLit>> solver = make_unique<Solver<TLit>>(move(sat_solver));

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();

  vector<TLit> bit_vector = {v1, v2, v3, v4};
  vector<TLit> assumps = {-v1, -v3};

  SolverStatus status = solver->SolveOBV(assumps, bit_vector);

  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v2), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v3), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v4), TLitValue::FALSE);
}

TEST(ObvTest, TestObsWithCardinalityConstraint) {
  unique_ptr<SatSolver<TLit>> sat_solver = make_unique<ToporSatSolver<TLit>>();
  unique_ptr<Solver<TLit>> solver = make_unique<Solver<TLit>>(move(sat_solver));

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();

  vector<TLit> bit_vector = {v1, v2, v3, v4};
  vector<TLit> assumps = {};

  ASSERT_TRUE(solver->AddConstraintGreaterThan(bit_vector, 0));

  solver->SolveOBV(assumps, bit_vector);

  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v2), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v3), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v4), TLitValue::TRUE);

  ASSERT_TRUE(solver->AddConstraintGreaterThan(bit_vector, 1));

  SolverStatus status = solver->SolveOBV(assumps, bit_vector);

  ASSERT_EQ(status, SolverStatus::SAT);

  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v2), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v3), TLitValue::TRUE);
  ASSERT_EQ(solver->LitValue(v4), TLitValue::TRUE);

  ASSERT_TRUE(solver->AddConstraintGreaterThan(bit_vector, 2));

  status = solver->SolveOBV(assumps, bit_vector);

  ASSERT_EQ(status, SolverStatus::SAT);

  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v2), TLitValue::TRUE);
  ASSERT_EQ(solver->LitValue(v3), TLitValue::TRUE);
  ASSERT_EQ(solver->LitValue(v4), TLitValue::TRUE);

  ASSERT_TRUE(solver->AddConstraintGreaterThan(bit_vector, 3));

  status = solver->SolveOBV(assumps, bit_vector);

  ASSERT_EQ(status, SolverStatus::SAT);

  ASSERT_EQ(solver->LitValue(v1), TLitValue::TRUE);
  ASSERT_EQ(solver->LitValue(v2), TLitValue::TRUE);
  ASSERT_EQ(solver->LitValue(v3), TLitValue::TRUE);
  ASSERT_EQ(solver->LitValue(v4), TLitValue::TRUE);
}

TEST(ObvTest, TestConstrainedObv) {
  unique_ptr<SatSolver<TLit>> sat_solver = make_unique<ToporSatSolver<TLit>>();
  unique_ptr<Solver<TLit>> solver = make_unique<Solver<TLit>>(move(sat_solver));

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();

  vector<TLit> bit_vector = {v1, v2, v3, v4};
  vector<TLit> assumps = {};

  vector<TLit> clause = {v1, v2, v3, v4};

  solver->AddClause(clause);

  SolverStatus status = solver->SolveOBV(assumps, bit_vector);

  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v2), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v3), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v4), TLitValue::TRUE);
}

TEST(ObvTest, TestMultipleConstrainedObv) {
  unique_ptr<SatSolver<TLit>> sat_solver = make_unique<ToporSatSolver<TLit>>();
  unique_ptr<Solver<TLit>> solver = make_unique<Solver<TLit>>(move(sat_solver));

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();

  vector<TLit> bit_vector = {v1, v2, v3, v4};
  vector<TLit> assumps = {};

  vector<TLit> clause1 = {v1, v2, v3, v4};

  ASSERT_TRUE(solver->AddClause(clause1));
  ASSERT_TRUE(solver->AddConstraintLessThan(bit_vector, 3));
  ASSERT_TRUE(solver->AddConstraintGreaterThan(bit_vector, 1));

  SolverStatus status = solver->SolveOBV(assumps, bit_vector);

  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v2), TLitValue::FALSE);
  ASSERT_EQ(solver->LitValue(v3), TLitValue::TRUE);
  ASSERT_EQ(solver->LitValue(v4), TLitValue::TRUE);
}