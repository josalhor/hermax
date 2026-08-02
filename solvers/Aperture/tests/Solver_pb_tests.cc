#include <gtest/gtest.h>

#include <chrono>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>

#include "Aperture.h"
#include "constraints/Totalizer.h"
#include "solvers/topor/Solver.h"

using namespace std;
using namespace Aperture;
using TLit = int32_t;
using TWeight = uint64_t;

TEST(PBTests, TestSimplePB) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit selector = solver->NewVar();

  vector<pair<TWeight, TLit>> pb_lits = {{1, v1}, {1, v2}};
  ASSERT_TRUE(solver->AddConstraintLessThan(pb_lits, 2, selector));
  vector<TLit> assumps = {-selector};
  SolverStatus status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  TWeight total_weight = 0;
  for (const auto& [weight, lit] : pb_lits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      total_weight += weight;
    }
  }
  ASSERT_LT(total_weight, 2);

  pb_lits = {{2, v3}, {3, v4}};
  ASSERT_TRUE(solver->AddConstraintLessThanEqual(pb_lits, 2, selector));
  assumps = {-selector};
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  total_weight = 0;
  for (const auto& [weight, lit] : pb_lits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      total_weight += weight;
    }
  }
  ASSERT_LE(total_weight, 2);

  pb_lits = {
      {2, solver->NewVar()}, {3, solver->NewVar()}, {4, solver->NewVar()}};
  ASSERT_TRUE(solver->AddConstraintLessThan(pb_lits, 8, selector));
  assumps = {-selector};
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  total_weight = 0;
  for (const auto& [weight, lit] : pb_lits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      total_weight += weight;
    }
  }
  ASSERT_LT(total_weight, 8);
}

TEST(PBTests, TestInvalidCases) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit selector = solver->NewVar();

  vector<pair<TWeight, TLit>> wlits = {{1, v1}, {1, v2}};
  vector<pair<TWeight, TLit>> empty_wlits;
  ASSERT_FALSE(solver->AddConstraintLessThan(wlits, 0, selector));
  ASSERT_FALSE(solver->AddConstraintLessThanEqual(wlits, 0, selector));
}

TEST(PBTests, TestNumClauses) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);
  int num_clauses_added = 0;
  Totalizer<TLit, TWeight> totalizer(
      [&solver]() { return solver->NewVar(); },
      [&solver, &num_clauses_added](Lits<TLit> clause) {
        num_clauses_added++;
        return solver->AddClause(clause);
      });

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit selector = solver->NewVar();

  vector<pair<TWeight, TLit>> wlits = {{1, v1}, {1, v2}, {1, v3}, {1, v4}};
  vector<pair<TWeight, TLit>> totalizer_output =
      totalizer.EncodeGenTotalizer(wlits, selector);
}