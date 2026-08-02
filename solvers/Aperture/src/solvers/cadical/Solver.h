#pragma once

#include <string>
#include <unordered_map>

#include "../SatSolver.h"
#include "external/solvers/cadical/src/cadical.hpp"

namespace Aperture {
template <ValidLiteral TLit = int32_t>
class CadicalSatSolver final : public SatSolver<TLit> {
 public:
  CadicalSatSolver(
      const std::unordered_map<std::string, std::string>& params = {})
      : max_var_(0) {}
  bool AddClause(Lits<TLit> lits) override;
  SolverStatus Solve(Lits<TLit> assumps, uint64_t conflict_threshold) override;
  std::vector<Aperture::TLitValue> GetModel() const override;
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
  mutable ApertureCaDiCaL::Solver cadical_;
  TLit max_var_;
  std::vector<TLitValue> latest_model_;
};
};  // namespace Aperture