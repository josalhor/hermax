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

TEST(TotalizerTests, TestTotalizer) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit selector = solver->NewVar();

  // Empty lits
  vector<TLit> lits = {};
  vector<TLit> totalizer = solver->GetTotalizer(lits, selector);
  ASSERT_EQ(totalizer.size(), 0);

  // One lit
  lits = {v1};
  totalizer = solver->GetTotalizer(lits, selector);
  ASSERT_EQ(totalizer.size(), 1);
  for (TLit lit : totalizer) {
    ASSERT_NE(lit, 0);
    ASSERT_EQ(lit_abs<TLit>(lit), v1);
  }

  // Two lits
  lits = {v1, v2};
  totalizer = solver->GetTotalizer(lits, selector);
  ASSERT_EQ(totalizer.size(), 2);
  for (TLit lit : totalizer) {
    ASSERT_NE(lit, 0);
    ASSERT_TRUE(lit_abs<TLit>(lit) > selector);
  }

  // Four lits
  lits = {v1, v2, v3, v4};
  totalizer = solver->GetTotalizer(lits, selector);
  ASSERT_EQ(totalizer.size(), 4);
  for (TLit lit : totalizer) {
    ASSERT_NE(lit, 0);
    ASSERT_TRUE(lit_abs<TLit>(lit) > selector);
  }

  // Empty lits with rhs simplification
  lits = {};
  totalizer = solver->GetTotalizer(lits, selector, 2);
  ASSERT_EQ(totalizer.size(), 0);

  // One lit with rhs simplification
  lits = {v1};
  totalizer = solver->GetTotalizer(lits, selector, 1);
  ASSERT_EQ(totalizer.size(), 1);
  for (TLit lit : totalizer) {
    ASSERT_NE(lit, 0);
    ASSERT_EQ(lit_abs<TLit>(lit), v1);
  }

  // Four lits with rhs simplification
  lits = {v1, v2, v3, v4};
  totalizer = solver->GetTotalizer(lits, selector, 2);
  ASSERT_EQ(totalizer.size(), 3);
  for (TLit lit : totalizer) {
    ASSERT_NE(lit, 0);
    ASSERT_TRUE(lit_abs<TLit>(lit) > selector);
  }

  // Four lits with large rhs simplification
  lits = {v1, v2, v3, v4};
  totalizer = solver->GetTotalizer(lits, selector, 10);
  ASSERT_EQ(totalizer.size(), 4);
  for (TLit lit : totalizer) {
    ASSERT_NE(lit, 0);
    ASSERT_TRUE(lit_abs<TLit>(lit) > selector);
  }

  // Four lits with rhs simplification of zero
  lits = {v1, v2, v3, v4};
  totalizer = solver->GetTotalizer(lits, selector, 0);
  ASSERT_EQ(totalizer.size(), 1);
  for (TLit lit : totalizer) {
    ASSERT_NE(lit, 0);
    ASSERT_TRUE(lit_abs<TLit>(lit) > selector);
  }
}

TEST(TotalizerTests, TestCCLessThan) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit selector = solver->NewVar();

  // Empty lits
  vector<TLit> lits = {};
  solver->AddConstraintLessThan(lits, 1, selector);

  // One lit
  lits = {v1};
  solver->AddConstraintLessThan(lits, 1, selector);
  vector<TLit> assumps = {-selector};
  SolverStatus status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::SAT);
  ASSERT_EQ(solver->LitValue(v1), TLitValue::FALSE);

  // Three lits
  lits = {v2, v3, v4};
  solver->AddConstraintLessThan(lits, 2, selector);
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
  solver->AddConstraintLessThan(lits, 2, selector);
  assumps = {-selector};
  vector<TLit> clause1 = {lits[0]};
  vector<TLit> clause2 = {lits[1]};
  solver->AddClause(clause1);
  solver->AddClause(clause2);
  status = solver->Solve(assumps);
  ASSERT_EQ(status, SolverStatus::UNSAT);
}