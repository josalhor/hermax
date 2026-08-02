#pragma once

#include <stdexcept>
#include <unordered_map>

#include "../SatSolver.h"

struct kissat;

namespace Aperture {
template <ValidLiteral TLit = int32_t>
class KissatSatSolver final : public SatSolver<TLit> {
 public:
  KissatSatSolver(
      const std::unordered_map<std::string, std::string>& params = {});
  bool AddClause(Lits<TLit> lits) override;
  std::vector<TLitValue> GetModel() const override;
  void CopyModelTo(std::vector<TLitValue>& model) const override;
  SolverStatus Solve(Lits<TLit> assumps, uint64_t conflict_threshold) override;
  TLit NewVar() override;
  TLit MaxUserVar() const override;
  void FixPolarity(TLit lit, bool target = false) override;
  void ClearPolarity(TLit lit) override;
  uint64_t GetNumImplications() const override {
    throw std::runtime_error(
        "Kissat currently does not support getting the number of "
        "implications.");
  }
  TLitValue LitValue(TLit lit) const override;
  void Interrupt() override;
  void BumpScore(TLit lit, double val) override;
  ~KissatSatSolver() override;

 private:
  kissat* kissat_;
  TLit max_var_;
};
};  // namespace Aperture
