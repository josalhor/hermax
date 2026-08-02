#pragma once

#include "PyTypes.h"
#include "src/Aperture.h"

namespace nb = nanobind;

namespace Aperture {

class AperturePython : public Solver<TLit, TWeight> {
 public:
  AperturePython(const std::string& sat_solver);

  bool AddClause(TLiterals& clause);
  bool Solve(TLiterals& assumps);
  TLiterals GetLatestSolution() const;
  TLit NewVar();
  TLit LitValue(TLit lit) const;
  int GetVerbosityLevel() const;
  void SetVerbosityLevel(int level);

  TLiterals GetTotalizer(
      TLiterals& lits, TLit selector,
      std::optional<uint64_t> rhs_simplification = std::nullopt);
  TWLiterals GetGenTotalizer(
      TWLiterals& wlits, TLit selector,
      std::optional<uint64_t> rhs_simplification = std::nullopt);
  bool AddConstraintLessThan(TLiterals& lits, uint64_t rhs,
                             std::optional<TLit> selector = std::nullopt);
  bool AddConstraintLessThanEqual(TLiterals& lits, uint64_t rhs,
                                  std::optional<TLit> selector = std::nullopt);
  bool AddConstraintEqual(TLiterals& lits, uint64_t rhs,
                          std::optional<TLit> selector = std::nullopt);
  bool AddConstraintGreaterThanEqual(
      TLiterals& lits, uint64_t rhs,
      std::optional<TLit> selector = std::nullopt);
  bool AddConstraintGreaterThan(TLiterals& lits, uint64_t rhs,
                                std::optional<TLit> selector = std::nullopt);
  bool AddConstraintLessThan(TWLiterals& wlits, uint64_t rhs,
                             std::optional<TLit> selector = std::nullopt);
  bool AddConstraintLessThanEqual(TWLiterals& wlits, uint64_t rhs,
                                  std::optional<TLit> selector = std::nullopt);
  std::string GetLatestSolveStatus() const;

  bool SolveMaxSAT(TLiterals& assumps, TLiterals& soft_lits,
                   bool fix_model_value,
                   std::optional<nb::typed<nb::callable, bool(TLiterals&)>>
                       callback_on_solution_found = std::nullopt);
  bool SolveWeightedMaxSAT(
      TLiterals& assumps, TWLiterals& soft_wlits, bool fix_model_value,
      std::optional<nb::typed<nb::callable, bool(TWLiterals&)>>
          callback_on_solution_found = std::nullopt);

  bool SolveBlackBox(
      TLiterals& assumps, TLiterals& observables,
      nb::typed<nb::callable, TWeight(nb::typed<nb::callable, TLit(TLit)>)>
          pb_func,
      std::optional<nb::typed<nb::callable, bool(TLiterals&)>>
          callback_on_solution_found = std::nullopt);
  bool SolveOBV(TLiterals& assumps, TLiterals& targets,
                std::optional<nb::typed<nb::callable, bool(TLiterals&)>>
                    callback_on_solution_found = std::nullopt);

 private:
  SolverStatus latest_status_;
  std::vector<TLit> user_vars_;

  static SolverType SolverNameToType(const std::string& solver_name);
  static std::string SolverStatusToString(SolverStatus status);
  static bool EqualsIgnoreCase(const std::string& a, const std::string& b);
};
};  // namespace Aperture
