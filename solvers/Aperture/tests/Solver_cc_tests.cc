#include <gtest/gtest.h>

#include <chrono>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>

#include "Aperture.h"
#include "solvers/topor/Solver.h"

using namespace std;
using namespace Aperture;
using TLit = int32_t;
using TWeight = uint64_t;

TEST(CCTests, TestCCLessThan) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit selector = solver->NewVar();

  // Empty lits
  vector<TLit> lits = {};
  ASSERT_FALSE(solver->AddConstraintLessThan(lits, 1, selector));

  // One lit
  lits = {v1};
  ASSERT_TRUE(solver->AddConstraintLessThan(lits, 1, selector));
  vector<TLit> assumps = {-selector};
  SolverStatus status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);

  // Three lits
  lits = {v2, v3, v4};
  ASSERT_TRUE(solver->AddConstraintLessThan(lits, 2, selector));
  assumps = {-selector};
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  uint32_t true_count = 0;
  for (TLit lit : lits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      true_count++;
    }
  }
  ASSERT_LT(true_count, 2);

  // Four lits, unsat case
  lits = {solver->NewVar(), solver->NewVar(), solver->NewVar(),
          solver->NewVar()};
  ASSERT_TRUE(solver->AddConstraintLessThan(lits, 2, selector));
  assumps = {-selector};
  vector<TLit> clause1 = {lits[0]};
  vector<TLit> clause2 = {lits[1]};
  solver->AddClause(clause1);
  solver->AddClause(clause2);
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::UNSAT);
}

TEST(CCTests, TestCCLessThanEqual) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit selector = solver->NewVar();

  // Empty lits
  vector<TLit> lits = {};
  ASSERT_FALSE(solver->AddConstraintLessThanEqual(lits, 0, selector));

  // One lit
  lits = {v1};
  ASSERT_TRUE(solver->AddConstraintLessThanEqual(lits, 0, selector));
  vector<TLit> assumps = {-selector};
  SolverStatus status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);

  // Three lits
  lits = {v2, v3, v4};
  ASSERT_TRUE(solver->AddConstraintLessThanEqual(lits, 1, selector));
  assumps = {-selector};
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  uint32_t true_count = 0;
  for (TLit lit : lits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      true_count++;
    }
  }
  ASSERT_LE(true_count, 1);

  // Four lits, unsat case
  lits = {solver->NewVar(), solver->NewVar(), solver->NewVar(),
          solver->NewVar()};
  ASSERT_TRUE(solver->AddConstraintLessThanEqual(lits, 2, selector));
  assumps = {-selector};
  vector<TLit> clause1 = {lits[0]};
  vector<TLit> clause2 = {lits[1]};
  vector<TLit> clause3 = {lits[2]};
  solver->AddClause(clause1);
  solver->AddClause(clause2);
  solver->AddClause(clause3);
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::UNSAT);
}

TEST(CCTests, TestCCEqual) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit selector = solver->NewVar();

  // Empty lits
  vector<TLit> lits = {};
  ASSERT_FALSE(solver->AddConstraintEqual(lits, 0, selector));

  // One lit
  lits = {v1};
  solver->AddConstraintEqual(lits, 1, selector);
  vector<TLit> assumps = {-selector};
  SolverStatus status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::TRUE);

  // Two lits
  lits = {v2, v3};
  ASSERT_TRUE(solver->AddConstraintEqual(lits, 1, selector));
  assumps = {-selector};
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  uint32_t true_count = 0;
  for (TLit lit : lits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      true_count++;
    }
  }
  ASSERT_EQ(true_count, 1);

  // Tree lits
  lits = {solver->NewVar(), solver->NewVar(), solver->NewVar()};
  ASSERT_TRUE(solver->AddConstraintEqual(lits, 2, selector));
  assumps = {-selector};
  vector<TLit> clause1 = {lits[0]};
  vector<TLit> clause2 = {lits[1]};
  solver->AddClause(clause1);
  solver->AddClause(clause2);
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  true_count = 0;
  for (TLit lit : lits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      true_count++;
    }
  }
  ASSERT_EQ(true_count, 2);

  // Four lits, unsat case
  lits = {solver->NewVar(), solver->NewVar(), solver->NewVar(),
          solver->NewVar()};
  ASSERT_TRUE(solver->AddConstraintEqual(lits, 2, selector));
  assumps = {-selector};
  clause1 = {lits[0]};
  clause2 = {lits[1]};
  vector<TLit> clause3 = {lits[2]};
  solver->AddClause(clause1);
  solver->AddClause(clause2);
  solver->AddClause(clause3);
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::UNSAT);
}

TEST(CCTests, TestCCGreaterThanEqual) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit selector = solver->NewVar();

  // Empty lits
  vector<TLit> lits = {};
  ASSERT_FALSE(solver->AddConstraintGreaterThanEqual(lits, 0, selector));

  // One lit
  lits = {v1};
  solver->AddConstraintGreaterThanEqual(lits, 1, selector);
  vector<TLit> assumps = {-selector};
  SolverStatus status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::TRUE);

  // Three lits
  lits = {v2, v3, v4};
  ASSERT_TRUE(solver->AddConstraintGreaterThanEqual(lits, 1, selector));
  assumps = {-selector};
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  uint32_t true_count = 0;
  for (TLit lit : lits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      true_count++;
    }
  }
  ASSERT_GE(true_count, 1);

  // Four lits, unsat case
  lits = {solver->NewVar(), solver->NewVar(), solver->NewVar(),
          solver->NewVar()};
  ASSERT_TRUE(solver->AddConstraintGreaterThanEqual(lits, 4, selector));
  assumps = {-selector};
  vector<TLit> clause1 = {-lits[0]};
  vector<TLit> clause2 = {-lits[1]};
  vector<TLit> clause3 = {-lits[2]};
  solver->AddClause(clause1);
  solver->AddClause(clause2);
  solver->AddClause(clause3);
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::UNSAT);
}

TEST(CCTests, TestCCGreaterThan) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit selector = solver->NewVar();

  // Empty lits
  vector<TLit> lits = {};
  ASSERT_FALSE(solver->AddConstraintGreaterThan(lits, 0, selector));

  // One lit
  lits = {v1};
  ASSERT_TRUE(solver->AddConstraintGreaterThan(lits, 0, selector));
  vector<TLit> assumps = {-selector};
  SolverStatus status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::TRUE);

  // Three lits
  lits = {v2, v3, v4};
  ASSERT_TRUE(solver->AddConstraintGreaterThan(lits, 1, selector));
  assumps = {-selector};
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  uint32_t true_count = 0;
  for (TLit lit : lits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      true_count++;
    }
  }
  ASSERT_GT(true_count, 1);

  // Four lits, unsat case
  lits = {solver->NewVar(), solver->NewVar(), solver->NewVar(),
          solver->NewVar()};
  ASSERT_TRUE(solver->AddConstraintGreaterThan(lits, 3, selector));
  assumps = {-selector};
  vector<TLit> clause1 = {-lits[0]};
  solver->AddClause(clause1);
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::UNSAT);
}

TEST(CCTests, TestInvalidCases) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit selector = solver->NewVar();

  // Less Than with rhs 0
  vector<TLit> lits = {v1};
  ASSERT_FALSE(solver->AddConstraintLessThan(lits, 0, selector));
  // Equal with rhs greater than lits size
  ASSERT_FALSE(solver->AddConstraintEqual(lits, 2, selector));
  // Greater Than Equal with rhs greater than lits size
  ASSERT_FALSE(solver->AddConstraintGreaterThanEqual(lits, 2, selector));
  // Greater Than with rhs greater than or equal to lits size
  ASSERT_FALSE(solver->AddConstraintGreaterThan(lits, 1, selector));
}