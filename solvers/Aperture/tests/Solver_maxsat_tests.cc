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

TEST(MaxSATTest, TestSolveUnweightedMaxSAT) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};

  vector<TLit> soft_clause1 = {-v1};
  vector<TLit> soft_clause2 = {-v3};

  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  soft_clause1.push_back(v4);
  soft_clause2.push_back(v5);

  vector<TLit> soft_lits = {v4, v5};
  vector<pair<TWeight, TLit>> soft_wlits = {{1, v4}, {1, v5}};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  SolverStatus status = solver->SolveMaxSAT({}, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 1);
}

TEST(MaxSATTest, TestSolveWeightedMaxSAT) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};

  vector<TLit> soft_clause1 = {-v1};
  vector<TLit> soft_clause2 = {-v3};

  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  soft_clause1.push_back(v4);
  soft_clause2.push_back(v5);

  vector<pair<TWeight, TLit>> soft_wlits = {{9, v4}, {4, v5}};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  SolverStatus status = solver->SolveWeightedMaxSAT({}, soft_wlits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 4);
}

TEST(MaxSATTest, TestSolveMaxSATIncrementally) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};

  vector<TLit> soft_clause1 = {-v1};
  vector<TLit> soft_clause2 = {-v3};

  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  soft_clause1.push_back(v4);
  soft_clause2.push_back(v5);

  vector<TLit> soft_lits = {v4, v5};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  SolverStatus status = solver->SolveMaxSAT({}, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 1);

  // Add another soft clause
  vector<TLit> soft_clause3 = {-v1, -v3};
  TLit v6 = solver->NewVar();
  soft_clause3.push_back(v6);
  EXPECT_TRUE(solver->AddClause(soft_clause3));
  soft_lits.push_back(v6);

  status = solver->SolveMaxSAT({}, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 1);
}

TEST(MaxSATTest, TestSolveMaxSATIncrementallyNewVarsAndResultValue) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};

  vector<TLit> soft_clause1 = {-v1};
  vector<TLit> soft_clause2 = {-v3};

  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  soft_clause1.push_back(v4);
  soft_clause2.push_back(v5);

  vector<TLit> soft_lits = {v4, v5};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  SolverStatus status = solver->SolveMaxSAT({}, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 1);

  TLit v6 = solver->NewVar();
  TLit v7 = solver->NewVar();
  TLit v8 = solver->NewVar();

  vector<TLit> hard_clause3 = {v6, v7};
  vector<TLit> hard_clause4 = {-v7, v8};

  vector<TLit> soft_clause3 = {-v6};
  vector<TLit> soft_clause4 = {-v8};

  TLit v9 = solver->NewVar();
  TLit v10 = solver->NewVar();

  soft_clause3.push_back(v9);
  soft_clause4.push_back(v10);

  soft_lits.push_back(v9);
  soft_lits.push_back(v10);

  EXPECT_TRUE(solver->AddClause(hard_clause3));
  EXPECT_TRUE(solver->AddClause(hard_clause4));
  EXPECT_TRUE(solver->AddClause(soft_clause3));
  EXPECT_TRUE(solver->AddClause(soft_clause4));

  status = solver->SolveMaxSAT({}, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 2);
}

TEST(MaxSATTest, TestSolveMaxSATWithAssumptions) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);
  solver->SetVerbosityLevel(VerbosityLevel::VVERBOSE);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};

  vector<TLit> soft_clause1 = {-v1};
  vector<TLit> soft_clause2 = {-v3};

  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  soft_clause1.push_back(v4);
  soft_clause2.push_back(v5);

  vector<TLit> soft_lits = {v4, v5};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  vector<TLit> assumptions = {v1, v3};

  SolverStatus status = solver->SolveMaxSAT(assumptions, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 2);

  assumptions = {-v1, v3};

  status = solver->SolveMaxSAT(assumptions, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 1);

  assumptions = {v1, -v3};

  status = solver->SolveMaxSAT(assumptions, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 1);
}

TEST(MaxSATTest, TestSolveWeightedMaxSATWithAssumptions) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};

  vector<TLit> soft_clause1 = {-v1};
  vector<TLit> soft_clause2 = {-v3};

  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  soft_clause1.push_back(v4);
  soft_clause2.push_back(v5);

  vector<pair<TWeight, TLit>> soft_wlits = {{9, v4}, {4, v5}};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  vector<TLit> assumptions = {v1, v3};

  SolverStatus status =
      solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 13);

  assumptions = {-v1, v3};

  status = solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 4);

  assumptions = {v1, -v3};

  status = solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 9);
}

TEST(MaxSATTest, TestMaxSATSoftLiteralsAssumed) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> hard_clause = {v1, v2};

  vector<TLit> soft_clause1 = {-v1};
  vector<TLit> soft_clause2 = {-v2};

  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();

  soft_clause1.push_back(v3);
  soft_clause2.push_back(v4);

  vector<TLit> soft_lits = {v3, v4};

  EXPECT_TRUE(solver->AddClause(hard_clause));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  vector<TLit> assumptions = {v3, v4};

  SolverStatus status = solver->SolveMaxSAT(assumptions, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 2);

  assumptions = {-v3, v4};
  status = solver->SolveMaxSAT(assumptions, soft_lits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 1);

  assumptions = {v3, -v4};
  status = solver->SolveMaxSAT(assumptions, soft_lits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 1);

  assumptions = {-v3, -v4};
  status = solver->SolveMaxSAT(assumptions, soft_lits, false);
  EXPECT_EQ(SolverStatus::UNSAT, status);
}

TEST(MaxSATTest, TestMaxSATWeightedSoftLiteralsAssumed) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> hard_clause = {v1, v2};

  vector<TLit> soft_clause1 = {-v1};
  vector<TLit> soft_clause2 = {-v2};

  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();

  soft_clause1.push_back(v3);
  soft_clause2.push_back(v4);

  vector<pair<TWeight, TLit>> soft_wlits = {{5, v3}, {10, v4}};

  EXPECT_TRUE(solver->AddClause(hard_clause));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  vector<TLit> assumptions = {v3, v4};

  SolverStatus status =
      solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 15);

  assumptions = {-v3, v4};
  status = solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 10);

  assumptions = {v3, -v4};
  status = solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 5);

  assumptions = {-v3, -v4};
  status = solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);
  EXPECT_EQ(SolverStatus::UNSAT, status);
}

TEST(MaxSATTest, TestComplexLitsAndAssumpsMaxSAT) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();
  TLit v6 = solver->NewVar();
  TLit v7 = solver->NewVar();
  TLit v8 = solver->NewVar();
  vector<TLit> hard_clause1 = {v1, -v2, v3};
  vector<TLit> hard_clause2 = {-v3, v4, v5};
  vector<TLit> hard_clause3 = {-v5, -v6, v7};
  vector<TLit> hard_clause4 = {-v7, v8};
  vector<TLit> soft_clause1 = {-v1, v6};
  vector<TLit> soft_clause2 = {-v4, -v8};
  TLit v9 = solver->NewVar();
  TLit v10 = solver->NewVar();
  soft_clause1.push_back(v9);
  soft_clause2.push_back(v10);
  vector<TLit> soft_lits = {v9, v10};
  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(hard_clause3));
  EXPECT_TRUE(solver->AddClause(hard_clause4));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  vector<TLit> assumptions = {v2, -v4, v6, v8};
  SolverStatus status = solver->SolveMaxSAT(assumptions, soft_lits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);

  assumptions = {-v2, -v4, v6, v8};
  status = solver->SolveMaxSAT(assumptions, soft_lits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);

  assumptions = {v2, v4, v6, -v8};
  status = solver->SolveMaxSAT(assumptions, soft_lits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);

  assumptions = {-v2, v4, -v6, -v8};
  status = solver->SolveMaxSAT(assumptions, soft_lits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);
}

TEST(MaxSATTest, TestComplexLitsAndAssumpsWeightedMaxSAT) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();
  TLit v6 = solver->NewVar();
  TLit v7 = solver->NewVar();
  TLit v8 = solver->NewVar();
  vector<TLit> hard_clause1 = {v1, -v2, v3};
  vector<TLit> hard_clause2 = {-v3, v4, v5};
  vector<TLit> hard_clause3 = {-v5, -v6, v7};
  vector<TLit> hard_clause4 = {-v7, v8};
  vector<TLit> soft_clause1 = {-v1, v6};
  vector<TLit> soft_clause2 = {-v4, -v8};
  TLit v9 = solver->NewVar();
  TLit v10 = solver->NewVar();
  soft_clause1.push_back(v9);
  soft_clause2.push_back(v10);
  vector<pair<TWeight, TLit>> soft_wlits = {{3, v9}, {7, v10}};
  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(hard_clause3));
  EXPECT_TRUE(solver->AddClause(hard_clause4));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  vector<TLit> assumptions = {v2, -v4, v6, v8};
  SolverStatus status =
      solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);

  assumptions = {-v2, -v4, v6, v8};
  status = solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);

  assumptions = {v2, v4, v6, -v8};
  status = solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);

  assumptions = {-v2, v4, -v6, -v8};
  status = solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);
}

TEST(MaxSATTest, TestNoSoftLiteralsMaxSAT) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> hard_clause = {v1, v2};

  EXPECT_TRUE(solver->AddClause(hard_clause));

  vector<TLit> soft_lits = {};

  SolverStatus status = solver->SolveMaxSAT({}, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);
}

TEST(MaxSATTest, TestNoSoftLiteralsWeightedMaxSAT) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> hard_clause = {v1, v2};

  EXPECT_TRUE(solver->AddClause(hard_clause));

  vector<pair<TWeight, TLit>> soft_wlits = {};

  SolverStatus status = solver->SolveWeightedMaxSAT({}, soft_wlits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);
}

TEST(MaxSATTest, TEST) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> soft_clause1 = {v1};
  vector<TLit> soft_clause2 = {v2};

  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();

  soft_clause1.push_back(v3);
  soft_clause2.push_back(v4);

  vector<TLit> soft_lits = {v3, v4};

  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  SolverStatus status = solver->SolveMaxSAT({}, soft_lits, false);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);
}

TEST(MaxSATTest, TESTMultipleClausesForLitMaxSAT) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  vector<TLit> soft_clause1 = {v1, v3};
  vector<TLit> soft_clause2 = {v3, v2};

  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  vector<TLit> soft_lits = {v3};
  vector<TLit> assumptions = {v1, v2, -v3};
  SolverStatus status = solver->SolveMaxSAT(assumptions, soft_lits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);
}

TEST(MaxSATTest, TESTFixingModelValueWithZeroCost) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  vector<TLit> soft_lits = {solver->NewVar(), solver->NewVar()};
  vector<TLit> assumptions = {};

  SolverStatus status = solver->SolveMaxSAT(assumptions, soft_lits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->IsLatestMaxSATOptimal(), true);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);
  EXPECT_EQ(solver->IsLatestMaxSATFixedModelValue(), false);

  status = solver->SolveMaxSAT(assumptions, soft_lits, true);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->IsLatestMaxSATOptimal(), true);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);
  EXPECT_EQ(solver->IsLatestMaxSATFixedModelValue(), true);
}

TEST(MaxSATTest, TESTFixingModelValueWithNonZeroCost) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};

  vector<TLit> soft_clause1 = {-v1};
  vector<TLit> soft_clause2 = {-v3};

  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  soft_clause1.push_back(v4);
  soft_clause2.push_back(v5);

  vector<pair<TWeight, TLit>> soft_wlits = {{9, v4}, {4, v5}};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));

  SolverStatus status = solver->SolveWeightedMaxSAT({}, soft_wlits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->IsLatestMaxSATOptimal(), true);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 4);
  EXPECT_EQ(solver->IsLatestMaxSATFixedModelValue(), false);

  vector<TLit> assumptions = {v1};

  SolverStatus status2 =
      solver->SolveWeightedMaxSAT(assumptions, soft_wlits, false);

  EXPECT_EQ(SolverStatus::SAT, status2);
  EXPECT_EQ(solver->IsLatestMaxSATOptimal(), true);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 9);
  EXPECT_EQ(solver->IsLatestMaxSATFixedModelValue(), false);

  SolverStatus status3 = solver->SolveWeightedMaxSAT({}, soft_wlits, true);
  EXPECT_EQ(SolverStatus::SAT, status3);
  EXPECT_EQ(solver->IsLatestMaxSATOptimal(), true);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 4);
  EXPECT_EQ(solver->IsLatestMaxSATFixedModelValue(), true);

  SolverStatus status4 =
      solver->SolveWeightedMaxSAT(assumptions, soft_wlits, true);
  EXPECT_EQ(SolverStatus::UNSAT, status4);
}

TEST(MaxSATTest, TESTFixingModelValueClusters) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};

  vector<TLit> soft_clause1 = {-v4};
  vector<TLit> soft_clause2 = {-v1};
  vector<TLit> soft_clause3 = {-v3};

  TLit v5 = solver->NewVar();
  TLit v6 = solver->NewVar();
  TLit v7 = solver->NewVar();

  soft_clause1.push_back(v5);
  soft_clause2.push_back(v6);
  soft_clause3.push_back(v7);

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(soft_clause1));
  EXPECT_TRUE(solver->AddClause(soft_clause2));
  EXPECT_TRUE(solver->AddClause(soft_clause3));

  vector<pair<TWeight, TLit>> cluster1 = {{14, v5}};
  vector<pair<TWeight, TLit>> cluster2 = {{9, v6}, {4, v7}};

  SolverStatus status = solver->SolveWeightedMaxSAT({}, cluster1, true);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->IsLatestMaxSATOptimal(), true);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 0);
  EXPECT_EQ(solver->IsLatestMaxSATFixedModelValue(), true);

  SolverStatus status2 = solver->SolveWeightedMaxSAT({}, cluster2, false);
  EXPECT_EQ(SolverStatus::SAT, status2);
  EXPECT_EQ(solver->IsLatestMaxSATOptimal(), true);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 4);
  EXPECT_EQ(solver->IsLatestMaxSATFixedModelValue(), false);

  vector<TLit> assumptions = {v4};
  SolverStatus status3 =
      solver->SolveWeightedMaxSAT(assumptions, cluster2, true);
  EXPECT_EQ(SolverStatus::UNSAT, status3);

  SolverStatus status4 = solver->SolveWeightedMaxSAT({}, cluster2, true);
  EXPECT_EQ(SolverStatus::SAT, status4);
  EXPECT_EQ(solver->IsLatestMaxSATOptimal(), true);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 4);
  EXPECT_EQ(solver->IsLatestMaxSATFixedModelValue(), true);

  assumptions = {v1};
  SolverStatus status5 =
      solver->SolveWeightedMaxSAT(assumptions, cluster1, true);
  EXPECT_EQ(SolverStatus::UNSAT, status5);
}