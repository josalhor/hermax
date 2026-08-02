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

TEST(GenTotalizerTests, TestSimpleGenTotalizer) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit selector = solver->NewVar();

  vector<pair<TWeight, TLit>> pb_lits = {{1, v1}, {1, v2}};
  vector<pair<TWeight, TLit>> totalizer =
      solver->GetGenTotalizer(pb_lits, selector);

  ASSERT_EQ(totalizer.size(), 2);
}

TEST(GenTotalizerTests, TestRhsSimplification) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit selector = solver->NewVar();

  vector<pair<TWeight, TLit>> pb_lits = {{1, v1}, {1, v2}, {1, v3}};
  TWeight rhs_simplification = 2;
  vector<pair<TWeight, TLit>> totalizer =
      solver->GetGenTotalizer(pb_lits, selector, rhs_simplification);

  ASSERT_EQ(totalizer.size(), 3);
}

TEST(GenTotalizerTests, TestComplexGenTotalizer) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);
  vector<TLit> vars;
  for (int i = 0; i < 16; i++) {
    vars.push_back(solver->NewVar());
  }
  vector<TLit> relaxation_vars;
  // create the following relaxed soft clauses
  /*
  10  -1 -2 0
  6    3 0
  6   -3 0
  8    5 0
  8   -5 0
  7    7 0
  7   -7 0
  5    9 0
  5   -9 0
  4   -15 0
  */

  vector<pair<TWeight, TLit>> wlits;
  for (int i = 0; i < 10; i++) {
    TLit relax_var = solver->NewVar();
    relaxation_vars.push_back(relax_var);
  }

  wlits = {
      {10, relaxation_vars[0]}, {6, relaxation_vars[1]},
      {6, relaxation_vars[2]},  {8, relaxation_vars[3]},
      {8, relaxation_vars[4]},  {7, relaxation_vars[5]},
      {7, relaxation_vars[6]},  {5, relaxation_vars[7]},
      {5, relaxation_vars[8]},  {4, relaxation_vars[9]},
  };
  solver->AddClause({-vars[0], -vars[1], relaxation_vars[0]});
  solver->AddClause({vars[2], relaxation_vars[1]});
  solver->AddClause({-vars[2], relaxation_vars[2]});
  solver->AddClause({vars[4], relaxation_vars[3]});
  solver->AddClause({-vars[4], relaxation_vars[4]});
  solver->AddClause({vars[6], relaxation_vars[5]});
  solver->AddClause({-vars[6], relaxation_vars[6]});
  solver->AddClause({vars[8], relaxation_vars[7]});
  solver->AddClause({-vars[8], relaxation_vars[8]});
  solver->AddClause({-vars[14], relaxation_vars[9]});

  // Add the following Hard clauses
  /*
  h  1 0
  h  2 0
  h -3 4 0
  h -4 5 0
  h -5 6 0
  h -6 7 0
  h -7 8 0
  h -8 9 0
  h -9 10 0
  h -10 11 0
  h -11 12 0
  h -12 13 0
  h -13 14 0
  h -14 15 0
  */

  solver->AddClause({vars[0]});
  solver->AddClause({vars[1]});
  solver->AddClause({-vars[2], vars[3]});
  solver->AddClause({-vars[3], vars[4]});
  solver->AddClause({-vars[4], vars[5]});
  solver->AddClause({-vars[5], vars[6]});
  solver->AddClause({-vars[6], vars[7]});
  solver->AddClause({-vars[7], vars[8]});
  solver->AddClause({-vars[8], vars[9]});
  solver->AddClause({-vars[9], vars[10]});
  solver->AddClause({-vars[10], vars[11]});
  solver->AddClause({-vars[11], vars[12]});
  solver->AddClause({-vars[12], vars[13]});
  solver->AddClause({-vars[13], vars[14]});
  solver->AddClause({-vars[14], vars[15]});

  TLit selector = solver->NewVar();

  vector<pair<TWeight, TLit>> totalizer =
      solver->GetGenTotalizer(wlits, selector, 40);

  vector<TLit> assumptions;
  assumptions.push_back(-selector);
  SolverStatus status = solver->Solve(assumptions);
  EXPECT_EQ(status, SolverStatus::SAT);

  assumptions.push_back(-totalizer[totalizer.size() - 1].second);
  assumptions.push_back(-totalizer[totalizer.size() - 2].second);
  status = solver->Solve(assumptions);
  assumptions.pop_back();
  EXPECT_EQ(status, SolverStatus::SAT);
  TWeight totalizer_value = 0;
  for (const auto& [weight, lit] : wlits) {
    if (solver->LitValue(lit) == TLitValue::TRUE) {
      totalizer_value += weight;
    }
  }
  EXPECT_LT(totalizer_value, 40);
}