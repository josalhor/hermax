#include "AIpamirWrapper.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TIpamirLit, ValidWeight TIpamirWeight>
void ApertureIpamir<TIpamirLit, TIpamirWeight>::AddHard(TIpamirLit lit) {
  if (lit == 0) {
    this->AddClause(current_clause_);
    current_clause_.clear();
  } else {
    while (lit_abs<TIpamirLit>(lit) > this->MaxVar()) this->NewVar();
    current_clause_.push_back(lit);
  }
}

template <ValidLiteral TIpamirLit, ValidWeight TIpamirWeight>
void ApertureIpamir<TIpamirLit, TIpamirWeight>::AddSoftLit(
    TIpamirLit lit, TIpamirWeight weight) {
  auto it = soft_lit_to_index_.find(lit);
  if (it != soft_lit_to_index_.end()) {
    soft_lits_[it->second].first = weight;
  } else {
    soft_lit_to_index_[lit] = soft_lits_.size();
    soft_lits_.emplace_back(weight, lit);
  }
}

template <ValidLiteral TIpamirLit, ValidWeight TIpamirWeight>
void ApertureIpamir<TIpamirLit, TIpamirWeight>::Assume(TIpamirLit lit) {
  assumptions_.push_back(lit);
}

template <ValidLiteral TIpamirLit, ValidWeight TIpamirWeight>
int ApertureIpamir<TIpamirLit, TIpamirWeight>::Solve() {
  SolverStatus status =
      this->SolveWeightedMaxSAT(assumptions_, soft_lits_, false,
                                current_callback_on_weighted_solution_found_);

  assumptions_.clear();

  switch (status) {
    case SolverStatus::UNSAT:
      return 20;
    case SolverStatus::SAT:
      return this->IsLatestMaxSATOptimal() ? 30 : 10;
    case SolverStatus::ERROR:
      return 40;
    default:
      return 0;
  }
}

template <ValidLiteral TIpamirLit, ValidWeight TIpamirWeight>
TIpamirWeight ApertureIpamir<TIpamirLit, TIpamirWeight>::GetObjectiveValue()
    const {
  return this->GetLatestMaxSATValue();
}

template <ValidLiteral TIpamirLit, ValidWeight TIpamirWeight>
TIpamirLit ApertureIpamir<TIpamirLit, TIpamirWeight>::GetLitValue(
    TIpamirLit lit) const {
  TLitValue val = this->LitValue(lit);
  switch (val) {
    case TLitValue::TRUE:
      return lit;
    case TLitValue::FALSE:
      return -lit;
    default:
      return 0;
  }
}

template <ValidLiteral TIpamirLit, ValidWeight TIpamirWeight>
void ApertureIpamir<TIpamirLit, TIpamirWeight>::SetTerminate(
    void* state, int (*terminate)(void* state)) {
  if (terminate == nullptr) {
    current_terminate_func_ = nullptr;
    current_terminate_state_ = nullptr;
    current_callback_on_solution_found_ = nullptr;
    current_callback_on_weighted_solution_found_ = nullptr;
    return;
  }
  current_terminate_func_ = terminate;
  current_terminate_state_ = state;

  current_callback_on_solution_found_ = [this](std::span<const TIpamirLit> lits,
                                               void* state) {
    return current_terminate_func_(state);
  };

  current_callback_on_weighted_solution_found_ =
      [this](std::span<const std::pair<TIpamirWeight, TIpamirLit>> wlits,
             void* state) { return current_terminate_func_(state); };
}

template class Aperture::ApertureIpamir<int32_t, uint64_t>;