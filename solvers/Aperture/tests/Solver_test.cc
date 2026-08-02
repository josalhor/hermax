#include "solvers/topor/Solver.h"

#include <gtest/gtest.h>

#include <chrono>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>

#include "Aperture.h"

using namespace std;
using namespace Aperture;
using TLit = int32_t;
using TWeight = uint64_t;

TEST(SolverTest, InitSolverTest) {
  Solver<TLit> stack_solver(SolverType::TOPOR);
  Solver<TLit>* ptr_solver = new Solver<TLit>(SolverType::TOPOR);
  delete ptr_solver;
  unique_ptr<Solver<TLit>> unq_ptr_solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);
};

TEST(SolverTest, AddClauseWithValidLiteralTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> clause1 = {v1, -v2};

  EXPECT_NO_THROW(solver->AddClause(clause1));
}

TEST(SolverTest, SolveNoAssumpsSatTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();

  vector<TLit> clause1 = {v1, -v3, v4};
  vector<TLit> clause2 = {-v1, v2};
  vector<TLit> clause3 = {-v2, v3};
  vector<TLit> clause4 = {-v4};

  EXPECT_TRUE(solver->AddClause(clause1));
  EXPECT_TRUE(solver->AddClause(clause2));
  EXPECT_TRUE(solver->AddClause(clause3));
  EXPECT_TRUE(solver->AddClause(clause4));

  vector<TLit> assumptions = {};
  EXPECT_EQ(SolverStatus::SAT, solver->Solve(assumptions));
}

TEST(SolverTest, SolveNoAssumpsUnsatTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();

  vector<TLit> clause1 = {v1};
  vector<TLit> clause2 = {-v1};

  EXPECT_TRUE(solver->AddClause(clause1));
  EXPECT_TRUE(solver->AddClause(clause2));

  vector<TLit> assumptions = {};
  EXPECT_EQ(SolverStatus::UNSAT, solver->Solve(assumptions));
}

TEST(SolverTest, SolveWithAssumpsSatTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> clause1 = {v1, v2};
  vector<TLit> clause2 = {-v2, v3};
  vector<TLit> clause3 = {-v3};

  EXPECT_TRUE(solver->AddClause(clause1));
  EXPECT_TRUE(solver->AddClause(clause2));
  EXPECT_TRUE(solver->AddClause(clause3));

  vector<TLit> assumptions = {v1};
  EXPECT_EQ(SolverStatus::SAT, solver->Solve(assumptions));
}

TEST(SolverTest, SolveWithAssumpsUnsatTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> clause1 = {v1, v2};
  vector<TLit> clause2 = {-v2};
  vector<TLit> clause3 = {-v1};

  EXPECT_TRUE(solver->AddClause(clause1));
  EXPECT_TRUE(solver->AddClause(clause2));
  EXPECT_TRUE(solver->AddClause(clause3));

  vector<TLit> assumptions = {v1};
  EXPECT_EQ(SolverStatus::UNSAT, solver->Solve(assumptions));
}

TEST(SolverTest, GetLatestSolutionTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> clause1 = {v1, v2};
  vector<TLit> clause2 = {-v2, v3};
  vector<TLit> clause3 = {-v3};

  EXPECT_TRUE(solver->AddClause(clause1));
  EXPECT_TRUE(solver->AddClause(clause2));
  EXPECT_TRUE(solver->AddClause(clause3));

  vector<TLit> assumptions = {v1};
  EXPECT_EQ(SolverStatus::SAT, solver->Solve(assumptions));

  vector<TLitValue> solution = solver->GetLatestSolution();
  EXPECT_EQ(solution.size(), 4);
  EXPECT_EQ(solution[1], TLitValue::TRUE);
  EXPECT_EQ(solution[2], TLitValue::FALSE);
  EXPECT_EQ(solution[3], TLitValue::FALSE);
}

TEST(SolverTest, AddClauseWithInvalidLiteralTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit invalid = solver->NewVar() + 1;

  vector<TLit> clause1 = {v1, invalid};

  EXPECT_FALSE(solver->AddClause(clause1));
}

TEST(SolverTest, VarValueAndLitValueTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> clause1 = {v1};
  vector<TLit> clause2 = {-v2};

  EXPECT_TRUE(solver->AddClause(clause1));
  EXPECT_TRUE(solver->AddClause(clause2));

  vector<TLit> assumptions = {};
  EXPECT_EQ(SolverStatus::SAT, solver->Solve(assumptions));

  EXPECT_EQ(solver->VarValue(v1), TLitValue::TRUE);
  EXPECT_EQ(solver->VarValue(v2), TLitValue::FALSE);
  EXPECT_EQ(solver->LitValue(v1), TLitValue::TRUE);
  EXPECT_EQ(solver->LitValue(-v2), TLitValue::TRUE);
}

TEST(SolverTest, WeightedCostTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> clause1 = {v1};
  vector<TLit> clause2 = {-v2};

  EXPECT_TRUE(solver->AddClause(clause1));
  EXPECT_TRUE(solver->AddClause(clause2));

  vector<TLit> assumptions = {};
  EXPECT_EQ(SolverStatus::SAT, solver->Solve(assumptions));

  vector<pair<TWeight, TLit>> wlits = {{3, v1}, {5, -v2}};
  // EXPECT_EQ(solver->WeightedCost(wlits), 8);
}

TEST(SolverTest, UnweightedCostTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> clause1 = {v1};
  vector<TLit> clause2 = {-v2};

  EXPECT_TRUE(solver->AddClause(clause1));
  EXPECT_TRUE(solver->AddClause(clause2));

  vector<TLit> assumptions = {};
  EXPECT_EQ(SolverStatus::SAT, solver->Solve(assumptions));

  vector<TLit> lits = {v1, -v2};
  // EXPECT_EQ(solver->UnweightedCost(lits), 2);
}