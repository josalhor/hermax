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

TEST(SolverDumpTests, TestMultipleCallsDump) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();
  TLit v6 = solver->NewVar();
  TLit selector = solver->NewVar();
  vector<TLit> empty_lits = {};
  vector<TLit> lits = {v1, v2, v3};
  vector<TLit> empty_assumps = {};
  vector<TLit> assumps = {v4, v5, v6};
  vector<pair<TWeight, TLit>> empty_wlits = {};
  vector<pair<TWeight, TLit>> wlits = {{1, v1}, {2, v2}, {3, v3}};

  solver->Solve(empty_assumps);
  solver->Solve(assumps);

  solver->SolveMaxSAT(empty_assumps, empty_lits, false);
  solver->SolveMaxSAT(empty_assumps, lits, false);
  solver->SolveMaxSAT(assumps, empty_lits, false);
  solver->SolveMaxSAT(assumps, lits, false);

  solver->SolveWeightedMaxSAT(empty_assumps, empty_wlits, false);
  solver->SolveWeightedMaxSAT(empty_assumps, wlits, false);
  solver->SolveWeightedMaxSAT(assumps, empty_wlits, false);
  solver->SolveWeightedMaxSAT(assumps, wlits, false);

  solver->SolveBlackBox(empty_assumps, empty_lits,
                        [](function<TLitValue(TLit)>, void*) { return 0; });
  solver->SolveBlackBox(empty_assumps, lits,
                        [](function<TLitValue(TLit)>, void*) { return 0; });
  solver->SolveBlackBox(assumps, empty_lits,
                        [](function<TLitValue(TLit)>, void*) { return 0; });
  solver->SolveBlackBox(assumps, lits,
                        [](function<TLitValue(TLit)>, void*) { return 0; });

  solver->SolveOBV(empty_assumps, empty_lits);
  solver->SolveOBV(empty_assumps, lits);
  solver->SolveOBV(assumps, empty_lits);
  solver->SolveOBV(assumps, lits);

  solver->GetTotalizer(empty_lits, selector);
  solver->GetTotalizer(lits, selector);
  solver->GetTotalizer(empty_lits, selector, 2);
  solver->GetTotalizer(lits, selector, 2);

  solver->GetGenTotalizer(empty_wlits, selector);
  solver->GetGenTotalizer(wlits, selector);
  solver->GetGenTotalizer(empty_wlits, selector, 2);
  solver->GetGenTotalizer(wlits, selector, 2);

  solver->AddConstraintLessThan(empty_lits, 2);
  solver->AddConstraintLessThan(lits, 2);
  solver->AddConstraintLessThan(empty_lits, 2, selector);
  solver->AddConstraintLessThan(lits, 2, selector);
  solver->AddConstraintLessThanEqual(empty_lits, 2);
  solver->AddConstraintLessThanEqual(lits, 2);
  solver->AddConstraintLessThanEqual(empty_lits, 2, selector);
  solver->AddConstraintLessThanEqual(lits, 2, selector);
  solver->AddConstraintEqual(empty_lits, 2);
  solver->AddConstraintEqual(lits, 2);
  solver->AddConstraintEqual(empty_lits, 2, selector);
  solver->AddConstraintEqual(lits, 2, selector);
  solver->AddConstraintGreaterThanEqual(empty_lits, 2);
  solver->AddConstraintGreaterThanEqual(lits, 2);
  solver->AddConstraintGreaterThanEqual(empty_lits, 2, selector);
  solver->AddConstraintGreaterThanEqual(lits, 2, selector);
  solver->AddConstraintGreaterThan(empty_lits, 2);
  solver->AddConstraintGreaterThan(lits, 2);
  solver->AddConstraintGreaterThan(empty_lits, 2, selector);
  solver->AddConstraintGreaterThan(lits, 2, selector);

  solver->AddConstraintLessThan(empty_wlits, 2, selector);
  solver->AddConstraintLessThan(wlits, 2, selector);
  solver->AddConstraintLessThanEqual(empty_wlits, 2, selector);
  solver->AddConstraintLessThanEqual(wlits, 2, selector);
}