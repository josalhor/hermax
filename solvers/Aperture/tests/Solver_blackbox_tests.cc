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

TEST(BlackBoxTest, TestSolveBlackBox) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));

  auto PbFunc = [&](function<TLitValue(TLit)> LitValueFunc,
                    void *user_ds) -> TWeight {
    TWeight cost = 0;
    for (TLit lit : {v1, v2, v3}) {
      TLitValue val = LitValueFunc(lit);
      if (val == TLitValue::TRUE) {
        cost += 1;
      }
    }
    return cost;
  };

  vector<TLit> observables = {v1, v3};

  SolverStatus status = solver->SolveBlackBox({}, observables, PbFunc);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestBlackBoxValue(), 1);
}

TEST(BlackBoxTest, TestSolveBlackBoxUnsat) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1};
  vector<TLit> hard_clause2 = {-v1};
  vector<TLit> hard_clause3 = {v2};
  vector<TLit> hard_clause4 = {-v2};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(hard_clause3));
  EXPECT_TRUE(solver->AddClause(hard_clause4));

  auto PbFunc = [&](function<TLitValue(TLit)> LitValueFunc,
                    void *user_ds) -> TWeight {
    TWeight cost = 0;
    for (TLit lit : {v1, v2}) {
      TLitValue val = LitValueFunc(lit);
      if (val == TLitValue::TRUE) {
        cost += 1;
      }
    }
    return cost;
  };

  vector<TLit> observables = {v1, v2};

  SolverStatus status = solver->SolveBlackBox({}, observables, PbFunc);

  EXPECT_EQ(SolverStatus::UNSAT, status);
}

TEST(BlackBoxTest, TestSolveBlackBoxNoObservables) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1};

  EXPECT_TRUE(solver->AddClause(hard_clause1));

  vector<TLit> observables;  // Empty observables

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

  SolverStatus status = solver->SolveBlackBox({}, observables, PbFunc);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestBlackBoxValue(), 0);
}

TEST(BlackBoxTest, TestSolveBlackBoxWithAssumptions) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();
  vector<TLit> hard_clause1 = {v1, v2};
  vector<TLit> hard_clause2 = {-v2, v3};
  vector<TLit> hard_clause3 = {v4, v5};

  EXPECT_TRUE(solver->AddClause(hard_clause1));
  EXPECT_TRUE(solver->AddClause(hard_clause2));
  EXPECT_TRUE(solver->AddClause(hard_clause3));

  auto PbFunc = [&](function<TLitValue(TLit)> LitValueFunc,
                    void *user_ds) -> TWeight {
    TWeight cost = 0;
    for (TLit lit : {v1, v3, v4, v5}) {
      TLitValue val = LitValueFunc(lit);
      if (val == TLitValue::TRUE) {
        cost += 1;
      }
    }
    return cost;
  };

  vector<TLit> observables = {v1, v3, v4, v5};
  vector<TLit> assumptions = {-v2};  // This assumption forces v1 be TRUE
  SolverStatus status = solver->SolveBlackBox(assumptions, observables, PbFunc);
  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(solver->GetLatestBlackBoxValue(), 2);
}

TEST(BlackBoxTest, TestSolveBlackBoxCallback) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  vector<TLit> hard_clause1 = {v1, v2};

  EXPECT_TRUE(solver->AddClause(hard_clause1));

  auto PbFunc = [&](function<TLitValue(TLit)> LitValueFunc,
                    void *user_ds) -> TWeight {
    TWeight cost = 0;
    for (TLit lit : {v1, v2}) {
      TLitValue val = LitValueFunc(lit);
      if (val == TLitValue::TRUE) {
        cost += 1;
      }
    }
    return cost;
  };

  vector<TLit> observables = {v1, v2};

  int callback_count = 0;
  auto CallbackOnSolutionFound = [&](Lits<TLit> lits, void *user_ds) -> bool {
    callback_count++;
    return true;
  };

  SolverStatus status = solver->SolveBlackBox({}, observables, PbFunc,
                                              CallbackOnSolutionFound, nullptr);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_EQ(callback_count, 1);
  EXPECT_TRUE(solver->GetLatestBlackBoxValue() >= 1);
}

TEST(BlackBoxTest, TestSolveBlackBoxCallbackComplexPB) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  vector<TLit> hard_clause1 = {v1, v2, v3};

  EXPECT_TRUE(solver->AddClause(hard_clause1));

  auto PbFunc = [&](function<TLitValue(TLit)> LitValueFunc,
                    void *user_ds) -> TWeight {
    TWeight cost = 0;
    for (TLit lit : {v1, v2, v3}) {
      TLitValue val = LitValueFunc(lit);
      if (val == TLitValue::TRUE) {
        cost += (lit == v1) ? 1 : (lit == v2) ? 2 : 3;
      }
    }
    return cost;
  };

  vector<TLit> observables = {v1, v2, v3};

  SolverStatus status = solver->SolveBlackBox({}, observables, PbFunc);

  EXPECT_EQ(SolverStatus::SAT, status);
  EXPECT_LT(solver->GetLatestBlackBoxValue(), 4);
}

TEST(BlackBoxTest, TestSolveBlackBoxIncrementalCalls) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2};

  EXPECT_TRUE(solver->AddClause(hard_clause1));

  auto PbFunc = [&](function<TLitValue(TLit)> LitValueFunc,
                    void *user_ds) -> TWeight {
    TWeight cost = 0;
    for (TLit lit : {v1, v2}) {
      TLitValue val = LitValueFunc(lit);
      if (val == TLitValue::TRUE) {
        cost += 1;
      }
    }
    return cost;
  };

  vector<TLit> observables = {v1, v2};

  // First call
  SolverStatus status1 = solver->SolveBlackBox({}, observables, PbFunc);
  EXPECT_EQ(SolverStatus::SAT, status1);
  EXPECT_EQ(solver->GetLatestBlackBoxValue(), 1);

  // Second call with an additional clause
  vector<TLit> hard_clause2 = {-v1};
  EXPECT_TRUE(solver->AddClause(hard_clause2));

  SolverStatus status2 = solver->SolveBlackBox({}, observables, PbFunc);
  EXPECT_EQ(solver->GetLatestBlackBoxValue(), 1);
}

TEST(BlackBoxTest, TestSolveBlackBoxIncrementalComplexCalls) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> hard_clause1 = {v1, v2, v3};

  EXPECT_TRUE(solver->AddClause(hard_clause1));

  auto PbFunc = [&](function<TLitValue(TLit)> LitValueFunc,
                    void *user_ds) -> TWeight {
    TWeight cost = 0;
    for (TLit lit : {v1, v2, v3}) {
      TLitValue val = LitValueFunc(lit);
      if (val == TLitValue::TRUE) {
        cost += 1;
      }
    }
    return cost;
  };

  vector<TLit> observables = {v1, v2, v3};

  // First call
  SolverStatus status1 = solver->SolveBlackBox({}, observables, PbFunc);
  EXPECT_EQ(SolverStatus::SAT, status1);
  EXPECT_TRUE(solver->GetLatestBlackBoxValue() < 3);

  // Second call with an additional clause
  vector<TLit> hard_clause2 = {-v1, -v2};
  EXPECT_TRUE(solver->AddClause(hard_clause2));

  SolverStatus status2 = solver->SolveBlackBox({}, observables, PbFunc);
  EXPECT_EQ(SolverStatus::SAT, status2);
  EXPECT_TRUE(solver->GetLatestBlackBoxValue() < 3);
}