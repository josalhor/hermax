#pragma once

#include "../SatSolver.h"
#include "external/solvers/glucose/core/Solver.h"

namespace Aperture {
template <ValidLiteral TLit = int32_t>
class GlucoseSatSolver final : public SatSolver<TLit> {
 public:
  GlucoseSatSolver(
      const std::unordered_map<std::string, std::string>& params = {});
  bool AddClause(Lits<TLit> lits) override;
  SolverStatus Solve(Lits<TLit> assumps, uint64_t conflict_threshold) override;
  std::vector<TLitValue> GetModel() const override;
  void CopyModelTo(std::vector<TLitValue>& model) const override;
  TLit NewVar() override;
  TLit MaxUserVar() const override { return max_var_; }
  void FixPolarity(TLit lit, bool target = false) override;
  void ClearPolarity(TLit lit) override;
  uint64_t GetNumImplications() const override;
  TLitValue LitValue(TLit lit) const override;
  void Interrupt() override;
  void BumpScore(TLit lit, double val) override;

 private:
  ApertureGlucose::Solver glucose_;
  TLit max_var_;

  ApertureGlucose::Var ToGlucoseVar(TLit var) const;
  ApertureGlucose::Lit ToGlucoseLit(TLit lit) const;
};
};  // namespace Aperture