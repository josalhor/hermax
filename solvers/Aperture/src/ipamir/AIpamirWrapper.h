#pragma once

#include "../Aperture.h"

namespace Aperture {

template <ValidLiteral TIpamirLit = int32_t,
          ValidWeight TIpamirWeight = uint64_t>
class ApertureIpamir : public Solver<TIpamirLit, TIpamirWeight> {
 public:
  ApertureIpamir() : Solver<TIpamirLit, TIpamirWeight>(SolverType::GLUCOSE) {}
  void AddHard(TIpamirLit lit);
  void AddSoftLit(TIpamirLit lit, TIpamirWeight weight);
  void Assume(TIpamirLit lit);
  int Solve();
  TIpamirWeight GetObjectiveValue() const;
  TIpamirLit GetLitValue(TIpamirLit lit) const;
  void SetTerminate(void* state, int (*terminate)(void* state));

 private:
  std::vector<TIpamirLit> current_clause_;
  std::vector<TIpamirLit> assumptions_;

  // Add Soft Lit (and ChangeWeight)

  std::vector<std::pair<TIpamirWeight, TIpamirLit>> soft_lits_;
  std::unordered_map<TIpamirLit, size_t> soft_lit_to_index_;
  std::vector<TIpamirLit> uwlits_;

  // Set Terminate

  int (*current_terminate_func_)(void* state) = nullptr;
  void* current_terminate_state_ = nullptr;
  std::function<bool(std::span<const TIpamirLit>, void*)>
      current_callback_on_solution_found_ = nullptr;
  std::function<bool(std::span<const std::pair<TIpamirWeight, TIpamirLit>>,
                     void*)>
      current_callback_on_weighted_solution_found_ = nullptr;
};
};  // namespace Aperture