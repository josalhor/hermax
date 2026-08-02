#include "PythonWrapper.h"

#include "src/logging/Logger.h"

namespace nb = nanobind;
using namespace std;
using namespace Aperture;

AperturePython::AperturePython(const string& sat_solver)
    : Solver<TLit, TWeight>(SolverNameToType(sat_solver)),
      latest_status_(SolverStatus::UNKNOWN) {
  Solver<TLit, TWeight>::SetEnableOutputColoring(true);
  Solver<TLit, TWeight>::SetVerbosityLevel(VerbosityLevel::VVERBOSE);
  Logger::Instance().ResetTimer();
}

bool AperturePython::AddClause(TLiterals& clause) {
  return Solver<TLit, TWeight>::AddClause(clause);
}

bool AperturePython::Solve(TLiterals& assumps) {
  latest_status_ = Solver<TLit, TWeight>::Solve(assumps);
  return latest_status_ == SolverStatus::SAT;
}

TLiterals AperturePython::GetLatestSolution() const {
  vector<TLitValue> latest_solution =
      Solver<TLit, TWeight>::GetLatestSolution();
  if (latest_solution.empty()) return {};

  TLiterals result;
  result.reserve(user_vars_.size());
  for (TLit var : user_vars_) {
    TLitValue value = Solver<TLit, TWeight>::VarValue(var);
    result.push_back(value == TLitValue::TRUE ? var : -var);
  }
  return result;
}

TLit AperturePython::NewVar() {
  TLit new_var = Solver<TLit, TWeight>::NewVar();
  user_vars_.push_back(new_var);
  return new_var;
}

TLit AperturePython::LitValue(TLit lit) const {
  return Solver<TLit, TWeight>::LitValue(lit) == TLitValue::TRUE ? lit : -lit;
}

int AperturePython::GetVerbosityLevel() const {
  return static_cast<int>(Solver<TLit, TWeight>::GetVerbosityLevel());
}

void AperturePython::SetVerbosityLevel(int level) {
  if (level < 0 || level > static_cast<int>(VerbosityLevel::VVERBOSE)) {
    throw invalid_argument("Invalid verbosity level: " + to_string(level));
  }
  Solver<TLit, TWeight>::SetVerbosityLevel(static_cast<VerbosityLevel>(level));
}

TLiterals AperturePython::GetTotalizer(TLiterals& lits, TLit selector,
                                       optional<uint64_t> rhs_simplification) {
  return TLiterals(
      Solver<TLit, TWeight>::GetTotalizer(lits, selector, rhs_simplification));
}

TWLiterals AperturePython::GetGenTotalizer(
    TWLiterals& wlits, TLit selector, optional<uint64_t> rhs_simplification) {
  return TWLiterals(Solver<TLit, TWeight>::GetGenTotalizer(wlits, selector,
                                                           rhs_simplification));
}

bool AperturePython::AddConstraintLessThan(TLiterals& lits, uint64_t rhs,
                                           optional<TLit> selector) {
  return Solver<TLit, TWeight>::AddConstraintLessThan(lits, rhs, selector);
}

bool AperturePython::AddConstraintLessThanEqual(TLiterals& lits, uint64_t rhs,
                                                optional<TLit> selector) {
  return Solver<TLit, TWeight>::AddConstraintLessThanEqual(lits, rhs, selector);
}

bool AperturePython::AddConstraintEqual(TLiterals& lits, uint64_t rhs,
                                        optional<TLit> selector) {
  return Solver<TLit, TWeight>::AddConstraintEqual(lits, rhs, selector);
}

bool AperturePython::AddConstraintGreaterThanEqual(TLiterals& lits,
                                                   uint64_t rhs,
                                                   optional<TLit> selector) {
  return Solver<TLit, TWeight>::AddConstraintGreaterThanEqual(lits, rhs,
                                                              selector);
}

bool AperturePython::AddConstraintGreaterThan(TLiterals& lits, uint64_t rhs,
                                              optional<TLit> selector) {
  return Solver<TLit, TWeight>::AddConstraintGreaterThan(lits, rhs, selector);
}

bool AperturePython::AddConstraintLessThan(TWLiterals& wlits, uint64_t rhs,
                                           optional<TLit> selector) {
  return Solver<TLit, TWeight>::AddConstraintLessThan(wlits, rhs, selector);
}

bool AperturePython::AddConstraintLessThanEqual(TWLiterals& wlits, uint64_t rhs,
                                                optional<TLit> selector) {
  return Solver<TLit, TWeight>::AddConstraintLessThanEqual(wlits, rhs,
                                                           selector);
}

string AperturePython::GetLatestSolveStatus() const {
  return SolverStatusToString(latest_status_);
}

bool AperturePython::SolveMaxSAT(
    TLiterals& assumps, TLiterals& soft_lits, bool fix_model_value,
    optional<nb::typed<nb::callable, bool(TLiterals&)>>
        callback_on_solution_found) {
  function<bool(span<const TLit>, void*)> callback_wrapper = nullptr;
  if (callback_on_solution_found.has_value()) {
    callback_wrapper = [callback_on_solution_found](span<const TLit> lits,
                                                    void* user_data) {
      TLiterals callback_lits(lits.begin(), lits.end());
      return nb::cast<bool>(callback_on_solution_found.value()(callback_lits));
    };
  }
  latest_status_ = Solver<TLit, TWeight>::SolveMaxSAT(
      assumps, soft_lits, fix_model_value, callback_wrapper);
  return latest_status_ == SolverStatus::SAT;
}

bool AperturePython::SolveWeightedMaxSAT(
    TLiterals& assumps, TWLiterals& soft_wlits, bool fix_model_value,
    optional<nb::typed<nb::callable, bool(TWLiterals&)>>
        callback_on_solution_found) {
  function<bool(WLits<TLit, TWeight>, void*)> callback_wrapper = nullptr;
  if (callback_on_solution_found.has_value()) {
    callback_wrapper = [callback_on_solution_found](WLits<TLit, TWeight> wlits,
                                                    void* user_data) {
      TWLiterals callback_wlits(wlits.begin(), wlits.end());
      return nb::cast<bool>(callback_on_solution_found.value()(callback_wlits));
    };
  }
  latest_status_ = Solver<TLit, TWeight>::SolveWeightedMaxSAT(
      assumps, soft_wlits, fix_model_value, callback_wrapper);
  return latest_status_ == SolverStatus::SAT;
}

bool AperturePython::SolveBlackBox(
    TLiterals& assumps, TLiterals& observables,
    nb::typed<nb::callable, TWeight(nb::typed<nb::callable, TLit(TLit)>)>
        pb_func,
    optional<nb::typed<nb::callable, bool(TLiterals&)>>
        callback_on_solution_found) {
  function<TWeight(function<TLitValue(TLit)>, void*)> pb_func_wrapper =
      [&pb_func](function<TLitValue(TLit)> lit_value_func, void* user_data) {
        auto lit_value_func_python =
            nb::cpp_function([lit_value_func](TLit lit) -> TLit {
              return lit_value_func(lit) == TLitValue::TRUE ? lit : -lit;
            });
        return nb::cast<TWeight>(pb_func(lit_value_func_python));
      };
  function<bool(span<const TLit>, void*)> callback_wrapper = nullptr;
  if (callback_on_solution_found.has_value()) {
    callback_wrapper = [callback_on_solution_found](span<const TLit> lits,
                                                    void* user_data) {
      TLiterals callback_lits(lits.begin(), lits.end());
      return nb::cast<bool>(callback_on_solution_found.value()(callback_lits));
    };
  }
  latest_status_ = Solver<TLit, TWeight>::SolveBlackBox(
      assumps, observables, pb_func_wrapper, callback_wrapper);
  return latest_status_ == SolverStatus::SAT;
}

bool AperturePython::SolveOBV(
    TLiterals& assumps, TLiterals& targets,
    optional<nb::typed<nb::callable, bool(TLiterals&)>>
        callback_on_solution_found) {
  function<bool(span<const TLit>, void*)> callback_wrapper = nullptr;
  if (callback_on_solution_found.has_value()) {
    callback_wrapper = [callback_on_solution_found](span<const TLit> lits,
                                                    void* user_data) {
      TLiterals callback_lits(lits.begin(), lits.end());
      return nb::cast<bool>(callback_on_solution_found.value()(callback_lits));
    };
  }
  latest_status_ =
      Solver<TLit, TWeight>::SolveOBV(assumps, targets, callback_wrapper);
  return latest_status_ == SolverStatus::SAT;
}

SolverType AperturePython::SolverNameToType(const string& solver_name) {
  std::string solver_name_lower = solver_name;
  std::transform(solver_name_lower.begin(), solver_name_lower.end(),
                 solver_name_lower.begin(), ::tolower);
  auto it = kSolverTypeMap.find(solver_name_lower);
  if (it != kSolverTypeMap.end()) {
    return it->second;
  }
  throw invalid_argument("Unknown solver name: " + solver_name);
}

string AperturePython::SolverStatusToString(SolverStatus status) {
  switch (status) {
    case SolverStatus::UNSAT:
      return "UNSAT";
    case SolverStatus::SAT:
      return "SAT";
    case SolverStatus::ERROR:
      return "ERROR";
    case SolverStatus::GLOBAL_CONTRADICTION:
      return "GLOBAL_CONTRADICTION";
    case SolverStatus::UNKNOWN:
      return "UNKNOWN";
    default:
      return "INVALID_STATUS";
  }
}
