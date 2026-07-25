#include "Aperture.h"

#include <algorithm>
#include <bit>
#include <limits>
#include <queue>
#include <unordered_map>
#include <unordered_set>

#include "solvers/SolverFactory.h"

using namespace std;
using namespace Aperture;

/* Solver and SAT Solving */

template <ValidLiteral TLit, ValidWeight TWeight>
Solver<TLit, TWeight>::Solver(unique_ptr<SatSolver<TLit>> solver,
                              const SolverOptions& options)
    : solver_(std::move(solver)),
      solver_options_(options),
      totalizer_(
          [this]() { return this->NewVar(); },
          [this](Lits<TLit> clause) { return this->AddClause(clause); }) {
  SetVerbosityLevel(solver_options_.verbosity_level);
  SetEnableOutputColoring(solver_options_.output_coloring);
  clause_offsets_.push_back(0);
  InitParamsMap();
}

template <ValidLiteral TLit, ValidWeight TWeight>
Solver<TLit, TWeight>::Solver(
    SolverType solver_type,
    const unordered_map<string, string>& sat_solver_params,
    const SolverOptions& options)
    : Solver(SolverFactory<TLit>::CreateSolver(solver_type, sat_solver_params,
                                               true),
             options) {
  logger_.Log("Using {} as main SAT solver.", SolverTypeToName(solver_type));
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Solver<TLit, TWeight>::AddClause(Lits<TLit> clause) {
  if (should_dump_) logger_.DumpSpan(clause);

  TLit max_var = MaxVar();
  int num_vars_pushed = 0;
  for (TLit l : clause) {
    if (lit_abs<TLit>(l) <= max_var) {
      clauses_.push_back(l);
      num_vars_pushed++;
    } else {
      for (int i = 0; i < num_vars_pushed; ++i) {
        clauses_.pop_back();
      }
      return false;
    }
  }
  bool added = solver_->AddClause(clause);
  if (added) {
    clause_offsets_.push_back(clauses_.size());
  } else {
    for (int i = 0; i < num_vars_pushed; ++i) {
      clauses_.pop_back();
    }
  }
  return added;
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Solver<TLit, TWeight>::InitClauses(vector<TLit>&& clauses,
                                        vector<size_t>&& clause_offsets) {
  if (!clauses_.empty()) {
    return false;
  }

  clauses_ = std::move(clauses);
  clause_offsets_ = std::move(clause_offsets);

  size_t num_clauses = clause_offsets_.size() - 1;
  Lits<TLit> all_clauses(clauses_.data(), clauses_.size());

  for (size_t i = 0; i < num_clauses; ++i) {
    Lits<TLit> clause = all_clauses.subspan(
        clause_offsets_[i], clause_offsets_[i + 1] - clause_offsets_[i]);

    if (should_dump_) logger_.DumpSpan(clause);

    if (!solver_->AddClause(clause)) {
      return false;
    }
  }

  return true;
}

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::Solve(Lits<TLit> assumps) {
  if (should_dump_) logger_.DumpSolve(assumps);

  if (!ValidAssumptions(assumps)) {
    latest_error_reason_ =
        "Invalid assumptions: some literals exceed the maximum variable index.";
    return SolverStatus::ERROR;
  }

  ResetBeforeSolving();

  SolverStatus status = solver_->Solve(assumps);
  if (status == SolverStatus::SAT) {
    SaveLatestSolutionFromSolver();
  }
  return status;
}

template <ValidLiteral TLit, ValidWeight TWeight>
vector<TLitValue> Solver<TLit, TWeight>::GetLatestSolution() const {
  return latest_solution_;
}

template <ValidLiteral TLit, ValidWeight TWeight>
TLit Solver<TLit, TWeight>::NewVar() {
  if (should_dump_) logger_.DumpNewVar();

  return solver_->NewVar();
}

template <ValidLiteral TLit, ValidWeight TWeight>
TLit Solver<TLit, TWeight>::MaxVar() const {
  return solver_->MaxUserVar();
}

template <ValidLiteral TLit, ValidWeight TWeight>
TLitValue Solver<TLit, TWeight>::VarValue(TLit lit) const {
  return latest_solution_[(lit > 0) ? lit : -lit];
}

template <ValidLiteral TLit, ValidWeight TWeight>
TLitValue Solver<TLit, TWeight>::LitValue(TLit lit) const {
  return (lit < 0) ? !latest_solution_[-lit] : latest_solution_[lit];
}

template <ValidLiteral TLit, ValidWeight TWeight>
unique_ptr<SatSolver<TLit>> Solver<TLit, TWeight>::BuildSecondarySolver(
    SolverType solver_type, Lits<TLit> lits, bool fix_target_polarities,
    bool bump_target_scores) {
  unordered_map<string, string> sat_solver_params;
  unique_ptr<SatSolver<TLit>> secondary_solver =
      SolverFactory<TLit>::CreateSolver(solver_type, sat_solver_params);
  TLit max_var = MaxVar();
  for (int var = 1; var <= max_var; ++var) {
    secondary_solver->NewVar();
  }
  for (size_t i = 0; i < clause_offsets_.size() - 1; ++i) {
    Lits<TLit> clause = Lits<TLit>(clauses_).subspan(
        clause_offsets_[i], clause_offsets_[i + 1] - clause_offsets_[i]);
    secondary_solver->AddClause(clause);
  }
  if (fix_target_polarities) {
    FixTargetsPolaritiesOptimisticFor(*secondary_solver, lits);
  }
  if (bump_target_scores) {
    BumpTargetScoresFor(*secondary_solver, lits);
  }
  return secondary_solver;
}

template <ValidLiteral TLit, ValidWeight TWeight>
unique_ptr<SatSolver<TLit>> Solver<TLit, TWeight>::BuildSecondarySolver(
    SolverType solver_type, WLits<TLit, TWeight> wlits,
    bool fix_target_polarities, bool bump_target_scores) {
  unordered_map<string, string> sat_solver_params;
  unique_ptr<SatSolver<TLit>> secondary_solver =
      SolverFactory<TLit>::CreateSolver(solver_type, sat_solver_params);
  TLit max_var = MaxVar();
  for (int var = 1; var <= max_var; ++var) {
    secondary_solver->NewVar();
  }
  for (size_t i = 0; i < clause_offsets_.size() - 1; ++i) {
    Lits<TLit> clause = Lits<TLit>(clauses_).subspan(
        clause_offsets_[i], clause_offsets_[i + 1] - clause_offsets_[i]);
    secondary_solver->AddClause(clause);
  }
  secondary_solver->ClearAllPolarities();
  if (fix_target_polarities) {
    FixTargetsPolaritiesOptimisticFor(*secondary_solver, wlits);
  }
  if (bump_target_scores) {
    BumpTargetScoresFor(*secondary_solver, wlits);
  }
  return secondary_solver;
}

template <ValidLiteral TLit, ValidWeight TWeight>
VerbosityLevel Solver<TLit, TWeight>::GetVerbosityLevel() const {
  return solver_options_.verbosity_level;
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::SetVerbosityLevel(VerbosityLevel level) {
  solver_options_.verbosity_level = level;
  logger_.SetVerbosity(LogSource::SOLVER, level);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::SetEnableOutputColoring(bool enable) {
  solver_options_.output_coloring = enable;
  logger_.SetEnableColoring(LogSource::SOLVER, enable);
}

template <ValidLiteral TLit, ValidWeight TWeight>
string Solver<TLit, TWeight>::GetLatestErrorReason() const {
  return latest_error_reason_;
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::SetParam(const string& param_name, double value) {
  auto it = params_map_.find(param_name);
  if (it == params_map_.end()) {
    throw invalid_argument("Unknown parameter name: " + param_name);
  }
  auto SetParamValue = [&value](auto&& arg) {
    *arg = static_cast<decay_t<decltype(*arg)>>(value);
  };
  visit(SetParamValue, it->second);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::ResetBeforeSolving() {
  latest_solution_.clear();
  latest_error_reason_.clear();
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::SaveLatestSolutionFromSolver(
    const SatSolver<TLit>& solver) {
  SigScopeBlocker block(SIGTERM);

  solver.CopyModelTo(latest_solution_);
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Solver<TLit, TWeight>::ValidAssumptions(Lits<TLit> assumps) const {
  return ValidLits(assumps);
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Solver<TLit, TWeight>::ValidLits(Lits<TLit> lits) const {
  const TLit max_var = MaxVar();
  for (TLit lit : lits) {
    if (lit_abs<TLit>(lit) > max_var) {
      return false;
    }
  }
  return true;
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Solver<TLit, TWeight>::ValidWLits(WLits<TLit, TWeight> wlits) const {
  const TLit max_var = MaxVar();
  for (const auto& [weight, lit] : wlits) {
    if (lit_abs<TLit>(lit) > max_var) {
      return false;
    }
  }
  return true;
}

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::SolveLimited(Lits<TLit> assumps) {
  return solver_->Solve(assumps, solver_options_.conflict_threshold);
}

template <ValidLiteral TLit, ValidWeight TWeight>
TLitValue Solver<TLit, TWeight>::LitValue(TLit lit,
                                          const SatSolver<TLit>& solver) const {
  return solver.LitValue(lit);
}

template <ValidLiteral TLit, ValidWeight TWeight>
size_t Solver<TLit, TWeight>::GetNumClauses() const {
  return clause_offsets_.size() - 1;
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::InitParamsMap() {
  params_map_["use_initial_solver"] = &solver_options_.use_initial_solver;
  params_map_["initial_solver_type"] = &solver_options_.initial_solver_type;
  params_map_["conflict_threshold"] = &solver_options_.conflict_threshold;
  params_map_["polosat_max_epochs"] = &solver_options_.polosat_max_epochs;
  params_map_["polosat_update_bits_on_each_sat_model"] =
      &solver_options_.polosat_update_bits_on_each_sat_model;
  params_map_["polosat_weighted_obv_strategy"] =
      &solver_options_.polosat_weighted_obv_strategy;
  params_map_["solve_optimistically"] = &solver_options_.solve_optimistically;
  params_map_["solve_conservatively"] = &solver_options_.solve_conservatively;
  params_map_["use_target_bumping"] = &solver_options_.use_target_bumping;
  params_map_["max_bump_rand_val"] = &solver_options_.max_bump_rand_val;
  params_map_["target_bump_score_value"] =
      &solver_options_.target_bump_score_value;

  // MaxSAT Solving
  params_map_["use_local_search"] = &solver_options_.use_local_search;
  params_map_["local_search_solver_type"] =
      &solver_options_.local_search_solver_type;
  params_map_["use_sat_based_optimization"] =
      &solver_options_.use_sat_based_optimization;
  params_map_["disable_polosat"] = &solver_options_.disable_polosat;
  params_map_["use_polosat_props_per_model_threshold"] =
      &solver_options_.use_polosat_props_per_model_threshold;
  params_map_["max_props_per_model"] = &solver_options_.max_props_per_model;
  params_map_["use_polosat_model_per_sec_threshold"] =
      &solver_options_.use_polosat_model_per_sec_threshold;
  params_map_["min_models_per_sec"] = &solver_options_.min_models_per_sec;

  // MaxSAT - MRS-Beaver options
  params_map_["mrs_beaver_max_iterations"] =
      &solver_options_.mrs_beaver_max_iterations;
  params_map_["mrs_beaver_max_non_improving_iterations"] =
      &solver_options_.mrs_beaver_max_non_improving_iterations;
  params_map_["mrs_beaver_seed"] = &solver_options_.mrs_beaver_seed;
  params_map_["mrs_beaver_obv_conflict_threshold"] =
      &solver_options_.mrs_beaver_obv_conflict_threshold;
  params_map_["mrs_beaver_use_complete_part_solver"] =
      &solver_options_.mrs_beaver_use_complete_part_solver;
  params_map_["mrs_beaver_complete_part_solver"] =
      &solver_options_.mrs_beaver_complete_part_solver;
  params_map_["mrs_beaver_size_switch_to_complete"] =
      &solver_options_.mrs_beaver_size_switch_to_complete;
}

template <ValidLiteral TLit, ValidWeight TWeight>
TWeight Solver<TLit, TWeight>::UnweightedCostIn(const SatSolver<TLit>& solver,
                                                Lits<TLit> lits) const {
  return UnweightedCostFrom([&](TLit lit) { return LitValue(lit, solver); },
                            lits);
}

template <ValidLiteral TLit, ValidWeight TWeight>
TWeight Solver<TLit, TWeight>::UnweightedCost(Lits<TLit> lits) const {
  return UnweightedCostFrom([&](TLit lit) { return LitValue(lit); }, lits);
}

template <ValidLiteral TLit, ValidWeight TWeight>
TWeight Solver<TLit, TWeight>::UnweightedCostFrom(
    std::function<TLitValue(TLit)> LitValueFunc, Lits<TLit> lits) const {
  TWeight cost = 0;
  if (solver_options_.wcnf_mode) {
    const size_t base_index = solver_options_.wcnf_soft_base_index;
    const TLit max_var = solver_options_.wcnf_max_var + 1;
    int begin = 0;
    int end = 0;
    bool clause_satisfied = false;
    int clause_index = 0;
    for (TLit lit : lits) {
      if (LitValueFunc(lit) == TLitValue::TRUE) {
        clause_index = base_index + (lit - max_var);
        begin = clause_offsets_[clause_index];
        end = clause_offsets_[clause_index + 1];
        clause_satisfied = false;
        for (int i = begin; i < end - 1; i++) {
          if (LitValueFunc(clauses_[i]) == TLitValue::TRUE) {
            clause_satisfied = true;
            break;
          }
        }
        if (!clause_satisfied) {
          cost += 1;
        }
      }
    }
    return cost;
  } else {
    for (TLit lit : lits) {
      if (LitValueFunc(lit) == TLitValue::TRUE) cost += 1;
    }
  }
  return cost;
}

template <ValidLiteral TLit, ValidWeight TWeight>
TWeight Solver<TLit, TWeight>::WeightedCostIn(
    const SatSolver<TLit>& solver, WLits<TLit, TWeight> wlits) const {
  return WeightedCostFrom([&](TLit lit) { return LitValue(lit, solver); },
                          wlits);
}

template <ValidLiteral TLit, ValidWeight TWeight>
TWeight Solver<TLit, TWeight>::WeightedCost(WLits<TLit, TWeight> wlits) const {
  return WeightedCostFrom([&](TLit lit) { return LitValue(lit); }, wlits);
}

template <ValidLiteral TLit, ValidWeight TWeight>
TWeight Solver<TLit, TWeight>::WeightedCostFrom(
    std::function<TLitValue(TLit)> LitValueFunc,
    WLits<TLit, TWeight> wlits) const {
  TWeight cost = 0;
  if (solver_options_.wcnf_mode) {
    const size_t base_index = solver_options_.wcnf_soft_base_index;
    const TLit max_var = solver_options_.wcnf_max_var + 1;
    int begin = 0;
    int end = 0;
    bool clause_satisfied = false;
    int clause_index = 0;
    for (const auto& [weight, lit] : wlits) {
      if (LitValueFunc(lit) == TLitValue::TRUE) {
        clause_index = base_index + (lit - max_var);
        begin = clause_offsets_[clause_index];
        end = clause_offsets_[clause_index + 1];
        clause_satisfied = false;
        for (int i = begin; i < end - 1; i++) {
          if (LitValueFunc(clauses_[i]) == TLitValue::TRUE) {
            clause_satisfied = true;
            break;
          }
        }
        if (!clause_satisfied) {
          cost += weight;
        }
      }
    }
    return cost;
  } else {
    for (const auto& [weight, lit] : wlits) {
      if (LitValueFunc(lit) == TLitValue::TRUE) cost += weight;
    }
  }
  return cost;
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::FixTargetsPolaritiesOptimisticFor(
    SatSolver<TLit>& solver, Lits<TLit> targets) {
  for (TLit lit : targets) {
    solver.FixPolarity(-lit, true);
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::FixTargetsPolaritiesOptimisticFor(
    SatSolver<TLit>& solver, WLits<TLit, TWeight> targets) {
  for (const auto& [weight, lit] : targets) {
    solver.FixPolarity(-lit, true);
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::FixTargetsPolaritiesOptimistic(Lits<TLit> targets) {
  FixTargetsPolaritiesOptimisticFor(*solver_, targets);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::FixTargetsPolaritiesOptimistic(
    WLits<TLit, TWeight> targets) {
  FixTargetsPolaritiesOptimisticFor(*solver_, targets);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::FixNoneTargetsPolaritiesConservative(
    Lits<TLit> targets) {
  unordered_set<TLit> target_set;
  for (TLit lit : targets) {
    target_set.insert(lit);
  }
  TLit max_var = MaxVar();
  for (TLit v = 1; v <= max_var; ++v) {
    if (target_set.count(v) == 0 && target_set.count(-v) == 0) {
      solver_->FixPolarity(VarValue(v) == TLitValue::TRUE ? v : -v);
    }
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::FixNoneTargetsPolaritiesConservative(
    WLits<TLit, TWeight> targets) {
  unordered_set<TLit> target_set;
  for (const auto& [weight, lit] : targets) {
    target_set.insert(lit);
  }
  TLit max_var = MaxVar();
  for (TLit v = 1; v <= max_var; ++v) {
    if (target_set.count(v) == 0 && target_set.count(-v) == 0) {
      solver_->FixPolarity(VarValue(v) == TLitValue::TRUE ? v : -v);
    }
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::BumpTargetScoresFor(SatSolver<TLit>& solver,
                                                Lits<TLit> targets) {
  for (TLit lit : targets) {
    solver.BumpScore(lit, solver_options_.target_bump_score_value);
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::BumpTargetScores(Lits<TLit> targets) {
  BumpTargetScoresFor(*solver_, targets);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::BumpTargetScoresFor(SatSolver<TLit>& solver,
                                                WLits<TLit, TWeight> targets) {
  double min_weight = numeric_limits<double>::max();
  double max_weight = 0.;
  double current_weight = 0.;
  bool problem_weighted = false;
  for (const auto& [weight, lit] : targets) {
    current_weight = static_cast<double>(weight);
    if (current_weight < min_weight) {
      min_weight = current_weight;
    }
    if (current_weight > max_weight) {
      max_weight = current_weight;
    }
    problem_weighted |= (weight != 1);
  }
  if (problem_weighted) {
    const double max_bump_val = solver_options_.target_bump_score_value;
    const double weight_domain = max_weight - min_weight;

    auto GetRandBumpVal = [&]() {
      const int max_rand_val = solver_options_.max_bump_rand_val;
      return max_rand_val == 0 ? 0 : rand() % max_rand_val;
    };

    for (const auto& [weight, lit] : targets) {
      current_weight = static_cast<double>(weight);
      const double bump_val =
          weight_domain == 0
              ? (max_bump_val + static_cast<double>(GetRandBumpVal()))
              : (((current_weight - min_weight) / weight_domain) *
                     max_bump_val +
                 static_cast<double>(GetRandBumpVal()));

      solver.BumpScore(lit, bump_val);
    }
  } else {
    for (const auto& [weight, lit] : targets) {
      solver.BumpScore(lit, solver_options_.target_bump_score_value);
    }
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::BumpTargetScores(WLits<TLit, TWeight> targets) {
  BumpTargetScoresFor(*solver_, targets);
}

template class Aperture::Solver<int32_t, uint64_t>;