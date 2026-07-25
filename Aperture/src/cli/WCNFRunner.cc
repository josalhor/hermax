#include "WCNFRunner.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
int WCNFRunner<TLit, TWeight>::Run(const string& wcnf_file_path,
                                   SolverType solver_type,
                                   SolverOptions& solver_options) {
  signal(SIGINT, print_results_and_exit);
  signal(SIGTERM, print_results_and_exit);

  Reset();

  // WCNF Parsing

  WCNFData<TLit, TWeight> wcnf_data(wcnf_file_path);
  double parsing_time_seconds = logger.GetExactTimeInSeconds();
  PrintProblemStatistics(wcnf_data, parsing_time_seconds);

  bool weighted_maxsat = wcnf_data.weighted;
  if (weighted_maxsat) {
    problem_type = ProblemType::WEIGHTED_MAXSAT;
  } else {
    problem_type = ProblemType::MAXSAT;
  }

  /* Options for specific SAT solvers */

  unordered_map<string, string> sat_solver_params;

  solver_options.wcnf_max_var = wcnf_data.max_var;
  solver_options.wcnf_soft_base_index = wcnf_data.num_hard_clauses;
  if (weighted_maxsat) {
    solver_options.use_polosat_props_per_model_threshold = true;
    solver_options.polosat_weighted_obv_strategy = true;
    solver_options.max_props_per_model = 100000000;
    solver_options.mrs_beaver_size_switch_to_complete = 3500000;
    solver_options.mrs_beaver_seed = 1;
  } else {
    srand(solver_options.mrs_beaver_seed);
    solver_options.mrs_beaver_max_non_improving_iterations = 80;
  }
  switch (solver_type) {
    case SolverType::TOPOR: {
      solver_options.use_target_bumping = true;
      solver_options.target_bump_score_value = 50;
      if (weighted_maxsat) {
        sat_solver_params["mode"] = "5";
        solver_options.use_polosat_model_per_sec_threshold = true;
        solver_options.min_models_per_sec = 0.25;
        solver_options.target_bump_score_value = 750;
        solver_options.max_bump_rand_val = 1000;
      }
      break;
    }
    case SolverType::GLUCOSE:
      sat_solver_params["chrono"] = weighted_maxsat ? "-1" : "100";
      sat_solver_params["confl_to_chrono"] = "0";
    case SolverType::CADICAL:
      if (!weighted_maxsat) {
        solver_options.use_polosat_model_per_sec_threshold = true;
        solver_options.min_models_per_sec = 2.5;
        solver_options.use_polosat_props_per_model_threshold = false;
      } else {
        solver_options.min_models_per_sec = 0;
        solver_options.use_target_bumping = true;
        solver_options.target_bump_score_value = 113;
      }
    default:
      break;
  }

  /* -------------------------------- */

  // Solver initialization

  solver = make_unique<Solver<TLit, TWeight>>(solver_type, sat_solver_params,
                                              solver_options);

  // Add variables

  max_var = wcnf_data.max_var;
  for (TLit v = 1; v <= max_var; ++v) {
    solver->NewVar();
  }

  vector<TLit> clauses = std::move(wcnf_data.hard_clauses);
  vector<size_t> offsets = std::move(wcnf_data.hard_offsets);
  clauses.reserve(clauses.size() + wcnf_data.soft_clauses.size());
  offsets.reserve(offsets.size() + wcnf_data.soft_offsets.size());

  // Relax soft clauses and prepare weighted literals for MaxSAT

  vector<TLit> lits;
  vector<pair<TWeight, TLit>> wlits;
  if (weighted_maxsat) {
    wlits.reserve(wcnf_data.soft_clauses_weights.size());
  } else {
    lits.reserve(wcnf_data.soft_clauses_weights.size());
  }
  int soft_clause_index = 0;
  for (size_t i = 0; i < wcnf_data.soft_clauses.size(); ++i) {
    clauses.push_back(wcnf_data.soft_clauses[i]);
    if (clauses[clauses.size() - 1] == 0) {
      TLit relax_lit = solver->NewVar();
      clauses[clauses.size() - 1] = relax_lit;
      TWeight weight = wcnf_data.soft_clauses_weights[soft_clause_index++];
      weighted_maxsat ? wlits.push_back({weight, relax_lit})
                      : lits.push_back(relax_lit);
      offsets.push_back(clauses.size());
    }
  }

  // Add clauses

  solver->InitClauses(std::move(clauses), std::move(offsets));

  wcnf_data.Clear();

  logger.Log(kExternal, "Done setup. Time: {:.4f}",
             logger.GetExactTimeInSeconds());

  /* --------------- Solving --------------- */

  if (weighted_maxsat) {
    solver_return_status = solver->SolveWeightedMaxSAT({}, wlits, true);
  } else {
    solver_return_status = solver->SolveMaxSAT({}, lits, true);
  }

  /* --------------------------------------- */

  PrintResults();

  return SolverStatusCode();
}

template <ValidLiteral TLit, ValidWeight TWeight>
void WCNFRunner<TLit, TWeight>::Reset() {
  problem_type = ProblemType::SAT;
  solver_return_status = SolverStatus::UNKNOWN;
  max_var = 0;
}

template <ValidLiteral TLit, ValidWeight TWeight>
int WCNFRunner<TLit, TWeight>::SolverStatusCode() {
  switch (solver_return_status) {
    case SolverStatus::SAT:
      if (solver->IsLatestMaxSATOptimal()) {
        return 30;
      }
      return 10;
    case SolverStatus::UNSAT:
      return 20;
    default:
      return 0;
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void WCNFRunner<TLit, TWeight>::PrintProblemStatistics(
    const WCNFData<TLit, TWeight>& wcnf_data, double parsing_time_seconds) {
  size_t hard = wcnf_data.num_hard_clauses;
  size_t soft = wcnf_data.num_soft_clauses;
  size_t total = hard + soft;

  logger.Log(kExternal,
             "==========================================================");
  logger.Log(kExternal, "Problem Statistics");
  logger.Log(kExternal,
             "----------------------------------------------------------");
  logger.Log(kExternal, "{:<28} {:>10}", "Variables:", wcnf_data.max_var);
  if (soft > 0) {
    logger.Log(kExternal, "{:<28} {:>10}", "Hard clauses:", hard);
    logger.Log(kExternal, "{:<28} {:>10}", "Soft clauses:", soft);
  } else {
    logger.Log(kExternal, "{:<28} {:>10}", "Clauses:", hard);
  }

  logger.Log(kExternal, "{:<28} {:>10}", "Total clauses:", total);

  std::string problem_type;
  if (soft == 0) {
    problem_type = "MaxSAT (no soft clauses, redundant...)";
  } else {
    problem_type = (wcnf_data.weighted ? " Weighted" : " Unweighted");
    problem_type += (hard > 0 ? " Partial" : "");
    problem_type += " MaxSAT";
  }
  logger.Log(kExternal, "{:<28} {:>10}", "Problem type:", problem_type);

  logger.Log(kExternal, "{:<28} {:>10.4f} seconds",
             "Parsing time:", parsing_time_seconds);
  logger.Log(kExternal,
             "==========================================================");
}

template <ValidLiteral TLit, ValidWeight TWeight>
void WCNFRunner<TLit, TWeight>::PrintModel(span<const TLitValue> model) {
  if (model.empty()) return;
  fmt::memory_buffer buffer;
  buffer.reserve(model.size());
  for (TLit v = 1; v <= max_var; ++v) {
    buffer.push_back(model[v] == TLitValue::TRUE ? '1' : '0');
  }
  logger.LogV(kPrintRegardless, kExternal,
              fmt::string_view(buffer.data(), buffer.size()));
}

template <ValidLiteral TLit, ValidWeight TWeight>
void WCNFRunner<TLit, TWeight>::PrintValue(TWeight value) {
  logger.LogO(kPrintRegardless, kExternal, value);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void WCNFRunner<TLit, TWeight>::PrintResults() {
  const auto& latest_solution = solver->GetLatestSolution();
  if (!latest_solution.empty() &&
      solver_return_status == SolverStatus::UNKNOWN) {
    solver_return_status = SolverStatus::SAT;
  }
  switch (solver_return_status) {
    case SolverStatus::SAT: {
      if (solver->IsLatestMaxSATOptimal()) {
        logger.LogS(kPrintRegardless, kExternal, "OPTIMUM FOUND");
      } else {
        logger.LogS(kPrintRegardless, kExternal, "SATISFIABLE");
      }

      PrintValue(solver->GetLatestMaxSATValue());
      PrintModel(latest_solution);
      break;
    }
    case SolverStatus::UNSAT:
      logger.LogS(kPrintRegardless, kExternal, "UNSATISFIABLE");
      break;
    case SolverStatus::ERROR:
      logger.LogS(kPrintRegardless, kExternal, "ERROR");
      break;
    case SolverStatus::GLOBAL_CONTRADICTION:
      logger.LogS(kPrintRegardless, kExternal, "GLOBAL CONTRADICTION");
      break;
    case SolverStatus::UNKNOWN:
      logger.LogS(kPrintRegardless, kExternal, "UNKNOWN");
      break;
  }
}

template class Aperture::WCNFRunner<int32_t, uint64_t>;