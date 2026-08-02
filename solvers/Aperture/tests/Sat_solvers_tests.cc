#include <gtest/gtest.h>

#include <memory>
#include <string>
#include <type_traits>
#include <vector>

#include "solvers/SatSolver.h"
#include "solvers/cadical/Solver.h"
#include "solvers/glucose/Solver.h"
#include "solvers/kissat/Solver.h"
#include "solvers/topor/Solver.h"

using namespace std;
using namespace Aperture;
using TLit = int32_t;

template <typename SolverT>
class SolverWrapperTest : public ::testing::Test {};

using SolverWrapperTypes =
    ::testing::Types<ToporSatSolver<TLit>, CadicalSatSolver<TLit>,
                     GlucoseSatSolver<TLit>, KissatSatSolver<TLit>>;

struct SolverTypeNames {
  template <typename T>
  static std::string GetName(int /*index*/) {
    if constexpr (std::is_same_v<T, ToporSatSolver<TLit>>) {
      return "Topor";
    } else if constexpr (std::is_same_v<T, CadicalSatSolver<TLit>>) {
      return "CaDiCaL";
    } else if constexpr (std::is_same_v<T, GlucoseSatSolver<TLit>>) {
      return "Glucose";
    } else if constexpr (std::is_same_v<T, KissatSatSolver<TLit>>) {
      return "Kissat";
    } else {
      return "UnknownSolver";
    }
  }
};

TYPED_TEST_SUITE(SolverWrapperTest, SolverWrapperTypes, SolverTypeNames);

template <typename SolverT>
unique_ptr<SatSolver<TLit>> MakeSolver() {
  return make_unique<SolverT>();
}

TYPED_TEST(SolverWrapperTest, InitSolverTest) {
  [[maybe_unused]] TypeParam stack_solver;
  SatSolver<TLit>* ptr_solver = new TypeParam();
  delete ptr_solver;
  unique_ptr<SatSolver<TLit>> unq_ptr_solver = make_unique<TypeParam>();
}

TYPED_TEST(SolverWrapperTest, SolveNoAssumpsSatTest) {
  auto solver = MakeSolver<TypeParam>();

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

TYPED_TEST(SolverWrapperTest, SolveNoAssumpsUnsatTest) {
  auto solver = MakeSolver<TypeParam>();

  TLit v1 = solver->NewVar();

  vector<TLit> clause1 = {v1};
  vector<TLit> clause2 = {-v1};

  EXPECT_TRUE(solver->AddClause(clause1));
  solver->AddClause(clause2);

  vector<TLit> assumptions = {};
  EXPECT_EQ(SolverStatus::UNSAT, solver->Solve(assumptions));
}

TYPED_TEST(SolverWrapperTest, SolveWithAssumpsSatTest) {
  auto solver = MakeSolver<TypeParam>();

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

TYPED_TEST(SolverWrapperTest, SolveWithAssumpsUnsatTest) {
  auto solver = MakeSolver<TypeParam>();

  TLit v1 = solver->NewVar();
  TLit v2 = solver->NewVar();
  TLit v3 = solver->NewVar();

  vector<TLit> clause1 = {v1, v2};
  vector<TLit> clause2 = {-v2, v3};
  vector<TLit> clause3 = {-v3};

  EXPECT_TRUE(solver->AddClause(clause1));
  EXPECT_TRUE(solver->AddClause(clause2));
  EXPECT_TRUE(solver->AddClause(clause3));

  vector<TLit> assumptions = {-v1};
  EXPECT_EQ(SolverStatus::UNSAT, solver->Solve(assumptions));
}

TYPED_TEST(SolverWrapperTest, GetModelTest) {
  auto solver = MakeSolver<TypeParam>();

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

  vector<TLitValue> model = solver->GetModel();
  EXPECT_EQ(model.size(), 4);
  EXPECT_EQ(model[1], TLitValue::TRUE);
  EXPECT_EQ(model[2], TLitValue::FALSE);
  EXPECT_EQ(model[3], TLitValue::FALSE);
}

TYPED_TEST(SolverWrapperTest, GetLastModelAndValueAfterUnsat) {
  if constexpr (std::is_same_v<TypeParam, KissatSatSolver<TLit>>) {
    // Kissat is not required to be incremental
    GTEST_SKIP();
  }

  auto solver = MakeSolver<TypeParam>();

  TLit v1 = solver->NewVar();

  vector<TLit> clause1 = {v1};

  EXPECT_TRUE(solver->AddClause(clause1));

  vector<TLit> assumptions = {};
  EXPECT_EQ(SolverStatus::SAT, solver->Solve(assumptions));

  vector<TLit> clause2 = {-v1};
  solver->AddClause(clause2);

  EXPECT_EQ(SolverStatus::UNSAT, solver->Solve(assumptions));

  vector<TLitValue> model = solver->GetModel();
  EXPECT_EQ(model.size(), 2);
  EXPECT_EQ(model[1], TLitValue::TRUE);
}