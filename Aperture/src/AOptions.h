#pragma once

#include <string>

#include "ATypes.h"
#include "logging/Logger.h"

namespace Aperture {

struct ExternalOptions {
  std::string input_file;
  SolverType solver_type = SolverType::GLUCOSE;
  SolverMode mode = SolverMode::WCNF;
  // For ACNF mode. If true, user variables must be created using the "n"
  // line prefix. If false, user variables will be created automatically.
  // This is usefull for dumping the problem in ACNF format, so every API call
  // including NewVar() will be reflected in the output file for debugging
  // purposes.
  bool strict_user_vars = false;
};

struct SolverOptions {
  /* Solver and SAT Solving */

  VerbosityLevel verbosity_level = VerbosityLevel::VVERBOSE;
  bool output_coloring = false;
  // Note: WCNF mode enables optimizations for solving a single WCNF instance,
  // but may invalidate the solver state afterwards. Therefore, it should not be
  // used if the user intends to make further incremental solving queries.
  bool wcnf_mode = false;
  uint64_t wcnf_max_var = 0;
  uint64_t wcnf_soft_base_index = 0;

  /* SAT-based Optimization Solving */

  bool use_initial_solver = false;
  SolverType initial_solver_type = SolverType::KISSAT;
  uint64_t conflict_threshold = 10000000;
  int polosat_max_epochs = 1000000;
  bool polosat_update_bits_on_each_sat_model = true;
  bool polosat_weighted_obv_strategy = false;
  bool solve_optimistically = true;
  bool solve_conservatively = true;
  bool use_target_bumping = false;
  int max_bump_rand_val = 552;
  double target_bump_score_value = 50;

  // MaxSAT Solving

  bool use_local_search = true;
  bool use_sat_based_optimization = true;
  LocalSearchSolverType local_search_solver_type = LocalSearchSolverType::BAND;
  bool disable_polosat = false;
  bool use_polosat_props_per_model_threshold = true;
  double max_props_per_model = 1000000;
  bool use_polosat_model_per_sec_threshold = false;
  double min_models_per_sec = 2.5;

  // MaxSAT - MRS-Beaver options

  uint64_t mrs_beaver_max_iterations = 2147483647;
  uint64_t mrs_beaver_max_non_improving_iterations = 50;
  uint64_t mrs_beaver_seed = 1971603567;
  uint64_t mrs_beaver_obv_conflict_threshold = 1000;
  bool mrs_beaver_use_complete_part_solver = false;
  SolverType mrs_beaver_complete_part_solver = SolverType::CADICAL;
  uint64_t mrs_beaver_size_switch_to_complete = 1000000;
};
};  // namespace Aperture