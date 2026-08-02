#include <gtest/gtest.h>

#include <chrono>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>

#include "Aperture.h"
#include "constraints/Adder.h"
#include "solvers/topor/Solver.h"

using namespace std;
using namespace Aperture;
using TLit = int32_t;
using TWeight = uint64_t;

TEST(TestAdders, AdderLEQUnweightedTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  Adder<TLit, TWeight> adder(
      [&]() { return solver->NewVar(); },
      [&](Lits<TLit> clause) { return solver->AddClause(clause); });

  vector<pair<TWeight, TLit>> wlits;

  for (int i = 0; i < 50; i++) {
    wlits.emplace_back(1, solver->NewVar());

    AdderBits<TLit> adder_bits = adder.EncodeAdder(wlits);
    AdderBits<TLit> leq_bits = adder.LessThanOrEqualBits(adder_bits);

    TWeight total_weight = 0;
    for (const auto& [weight, lit] : wlits) {
      total_weight += weight;
    }
    // Set bound and solve
    for (int i = total_weight; i >= 0; i--) {
      adder.UpdateLEQBound(leq_bits, i);
      SolverStatus status = solver->Solve(leq_bits.Bits());
      if (status != SolverStatus::SAT) {
        FAIL() << "Solver failed to solve with LEQ bound " << i;
      }
      // Verify total weight <= bound
      TWeight total_satisfied_weight = 0;
      for (size_t j = 0; j < wlits.size(); j++) {
        if (solver->LitValue(wlits[j].second) == TLitValue::TRUE) {
          total_satisfied_weight += wlits[j].first;
        }
      }
      EXPECT_LE(total_satisfied_weight, i);
    }
  }
}

TEST(TestAdders, AdderLEQWeightedTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  Adder<TLit, TWeight> adder(
      [&]() { return solver->NewVar(); },
      [&](Lits<TLit> clause) { return solver->AddClause(clause); });

  vector<pair<TWeight, TLit>> wlits;

  for (int i = 0; i < 30; i++) {
    wlits.emplace_back(i, solver->NewVar());

    AdderBits<TLit> adder_bits = adder.EncodeAdder(wlits);
    AdderBits<TLit> leq_bits = adder.LessThanOrEqualBits(adder_bits);

    TWeight total_weight = 0;
    for (const auto& [weight, lit] : wlits) {
      total_weight += weight;
    }
    // Set bound and solve
    for (int i = total_weight; i >= 0; i--) {
      adder.UpdateLEQBound(leq_bits, i);
      SolverStatus status = solver->Solve(leq_bits.Bits());
      if (status != SolverStatus::SAT) {
        cout << "Solver returned status " << static_cast<int>(status) << endl;
        FAIL() << "Solver failed to solve with LEQ bound " << i;
      }
      // Verify total weight <= bound
      TWeight total_satisfied_weight = 0;
      for (size_t j = 0; j < wlits.size(); j++) {
        if (solver->LitValue(wlits[j].second) == TLitValue::TRUE) {
          total_satisfied_weight += wlits[j].first;
        }
      }
      EXPECT_LE(total_satisfied_weight, i);
    }
  }
}

TEST(TestAdders, AdderLEQWithSelectorTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  Adder<TLit, TWeight> adder(
      [&]() { return solver->NewVar(); },
      [&](Lits<TLit> clause) { return solver->AddClause(clause); });

  TLit selector = solver->NewVar();
  vector<pair<TWeight, TLit>> wlits;

  for (int i = 0; i < 30; i++) {
    wlits.emplace_back(i, solver->NewVar());

    AdderBits<TLit> adder_bits = adder.EncodeAdder(wlits, selector);
    AdderBits<TLit> leq_bits = adder.LessThanOrEqualBits(adder_bits, selector);
    vector<TLit> assumptions;
    assumptions.push_back(-selector);

    TWeight total_weight = 0;
    for (const auto& [weight, lit] : wlits) {
      total_weight += weight;
    }
    // Set bound and solve
    for (int i = total_weight; i >= 0; i--) {
      adder.UpdateLEQBound(leq_bits, i);
      assumptions.insert(assumptions.end(), leq_bits.Bits().begin(),
                         leq_bits.Bits().end());
      SolverStatus status = solver->Solve(assumptions);
      assumptions.erase(assumptions.end() - leq_bits.size(), assumptions.end());
      if (status != SolverStatus::SAT) {
        cout << "Solver returned status " << static_cast<int>(status) << endl;
        FAIL() << "Solver failed to solve with LEQ bound " << i;
      }
      // Verify total weight <= bound
      TWeight total_satisfied_weight = 0;
      for (size_t j = 0; j < wlits.size(); j++) {
        if (solver->LitValue(wlits[j].second) == TLitValue::TRUE) {
          total_satisfied_weight += wlits[j].first;
        }
      }
      EXPECT_LE(total_satisfied_weight, i);
    }
  }
}

TEST(TestAdders, AdderTest) {
  unique_ptr<Solver<TLit>> solver =
      make_unique<Solver<TLit>>(SolverType::TOPOR);

  Adder<TLit, TWeight> adder(
      [&]() { return solver->NewVar(); },
      [&](Lits<TLit> clause) { return solver->AddClause(clause); });

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();
  TLit v4 = solver->NewVar();
  TLit v5 = solver->NewVar();

  TLit c1[] = {v1, v2};
  TLit c2[] = {-v2, v3};
  TLit c3[] = {-v1, v4};
  TLit c4[] = {-v3, v5};
  vector<pair<TWeight, TLit>> wlits = {{9, v4}, {4, v5}};

  solver->AddClause(c1);
  solver->AddClause(c2);
  solver->AddClause(c3);
  solver->AddClause(c4);

  AdderBits<TLit> adder_bits = adder.EncodeAdder(wlits);
  AdderBits<TLit> leq_bits = adder.LessThanOrEqualBits(adder_bits);
  vector<TLit> assumptions;

  adder.UpdateLEQBound(leq_bits, 9);

  SolverStatus status = solver->Solve(leq_bits.Bits());
  EXPECT_EQ(status, SolverStatus::SAT);
}