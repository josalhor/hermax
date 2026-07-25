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

TEST(IncrementalTest, TestSolveIncrementalSAT) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  vector<TLit> assumps = {};
  vector<TLit> lits = {v1, v2, v3, v4, v5};

  for (int i = 0; i < lits.size(); i++) {
    vector<TLit> assumps = {};
    for (int j = 0; j < i; j++) {
      assumps.push_back(lits[j]);
    }
    SolverStatus status = solver->Solve(assumps);
    EXPECT_EQ(SolverStatus::SAT, status);
  }
  for (int i = lits.size() - 1; i >= 0; i--) {
    vector<TLit> assumps = {};
    for (int j = 0; j < i; j++) {
      assumps.push_back(lits[j]);
    }
    SolverStatus status = solver->Solve(assumps);
    EXPECT_EQ(SolverStatus::SAT, status);
  }

  solver->AddClause({v1});
  assumps = {-v1};
  SolverStatus status = solver->Solve(assumps);
  EXPECT_EQ(SolverStatus::UNSAT, status);

  assumps.pop_back();
  status = solver->Solve(assumps);
  EXPECT_EQ(SolverStatus::SAT, status);
}

TEST(IncrementalTest, TestSolveIncrementalUnweightedMaxSAT) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  vector<TLit> assumps = {};
  vector<TLit> lits = {v1, v2, v3, v4, v5};

  // Increasing and decreasing value

  for (int i = 0; i < lits.size(); i++) {
    vector<TLit> assumps = {};
    for (int j = 0; j < i; j++) {
      assumps.push_back(lits[j]);
    }
    SolverStatus status = solver->SolveMaxSAT(assumps, lits, false);
    EXPECT_EQ(SolverStatus::SAT, status);
    EXPECT_EQ(solver->GetLatestMaxSATValue(), i);
  }
  for (int i = lits.size() - 1; i >= 0; i--) {
    vector<TLit> assumps = {};
    for (int j = 0; j < i; j++) {
      assumps.push_back(lits[j]);
    }
    SolverStatus status = solver->SolveMaxSAT(assumps, lits, false);
    EXPECT_EQ(SolverStatus::SAT, status);
    EXPECT_EQ(solver->GetLatestMaxSATValue(), i);
  }

  // Unsat then Sat

  solver->AddClause({v1});
  assumps = {-v1};
  SolverStatus status = solver->SolveMaxSAT(assumps, lits, false);
  EXPECT_EQ(SolverStatus::UNSAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), numeric_limits<TWeight>::max());

  assumps.pop_back();
  status = solver->SolveMaxSAT(assumps, lits, false);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestMaxSATValue(), 1);
}

TEST(IncrementalTest, TestSolveIncrementalBlackBox) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  vector<TLit> assumps = {};
  vector<TLit> observables = {v1, v2, v3, v4, v5};

  auto PbFunc = [&](function<TLitValue(TLit)> LitValueFunc,
                    void *user_ds) -> TWeight {
    TWeight cost = 0;
    for (TLit lit : observables) {
      TLitValue val = LitValueFunc(lit);
      if (val == TLitValue::TRUE) {
        cost += 1;
      }
    }
    return cost;
  };

  for (int i = 0; i < observables.size(); i++) {
    vector<TLit> assumps = {};
    for (int j = 0; j < i; j++) {
      assumps.push_back(observables[j]);
    }
    SolverStatus status = solver->SolveBlackBox(assumps, observables, PbFunc);
    EXPECT_EQ(SolverStatus::SAT, status);
    EXPECT_EQ(solver->GetLatestBlackBoxValue(), i);
  }
  for (int i = observables.size() - 1; i >= 0; i--) {
    vector<TLit> assumps = {};
    for (int j = 0; j < i; j++) {
      assumps.push_back(observables[j]);
    }
    SolverStatus status = solver->SolveBlackBox(assumps, observables, PbFunc);
    EXPECT_EQ(SolverStatus::SAT, status);
    EXPECT_EQ(solver->GetLatestBlackBoxValue(), i);
  }

  vector<TLit> hard_clause = {v1};
  EXPECT_TRUE(solver->AddClause(hard_clause));
  assumps = {-v1};
  SolverStatus status = solver->SolveBlackBox(assumps, observables, PbFunc);
  EXPECT_EQ(SolverStatus::UNSAT, status);

  assumps.pop_back();
  status = solver->SolveBlackBox(assumps, observables, PbFunc);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestBlackBoxValue(), 1);
}

TEST(IncrementalTest, TestSolveIncrementalOBV) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  vector<TLit> assumps = {};
  vector<TLit> bit_vector = {v1, -v2, v3, -v4, v5};

  for (int i = 0; i < bit_vector.size(); i++) {
    vector<TLit> assumps = {};
    for (int j = 0; j < i; j++) {
      assumps.push_back(bit_vector[j]);
    }
    SolverStatus status = solver->SolveOBV(assumps, bit_vector);
    EXPECT_EQ(SolverStatus::SAT, status);
    auto solution = solver->GetLatestSolution();
    for (int k = 0; k < i; k++) {
      EXPECT_EQ(solution[bit_vector[k] < 0 ? -bit_vector[k] : bit_vector[k]],
                (bit_vector[k] < 0 ? TLitValue::FALSE : TLitValue::TRUE));
    }
  }
  for (int i = bit_vector.size() - 1; i >= 0; i--) {
    vector<TLit> assumps = {};
    for (int j = 0; j < i; j++) {
      assumps.push_back(bit_vector[j]);
    }
    SolverStatus status = solver->SolveOBV(assumps, bit_vector);
    EXPECT_EQ(SolverStatus::SAT, status);
    auto solution = solver->GetLatestSolution();
    for (int k = 0; k < i; k++) {
      EXPECT_EQ(solution[bit_vector[k] < 0 ? -bit_vector[k] : bit_vector[k]],
                (bit_vector[k] < 0 ? TLitValue::FALSE : TLitValue::TRUE));
    }
  }

  vector<TLit> hard_clause = {v1};
  EXPECT_TRUE(solver->AddClause(hard_clause));
  assumps = {-v1};
  SolverStatus status = solver->SolveOBV(assumps, bit_vector);
  EXPECT_EQ(SolverStatus::UNSAT, status);

  assumps.pop_back();
  status = solver->SolveOBV(assumps, bit_vector);
  EXPECT_EQ(SolverStatus::SAT, status);
  auto solution = solver->GetLatestSolution();
  EXPECT_EQ(solution[v1], TLitValue::TRUE);
}