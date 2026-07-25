#include "DeepDist.h"

#include <signal.h>

#include "../Aperture.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::DeepDist(
    Lits<TLit> assumps, WLits<TLit, TWeight> wlits,
    function<bool()> ShouldExitAfterSolutionFound) {
  unordered_set<TLit> assump_lits(assumps.begin(), assumps.end());

  deepdist::DeepDist dd_solver;
  dd_solver.problem_weighted = 0;

  unsigned long long dd_topclauseweight = 0;
  unsigned long long unsat_assumps_soft_weight = 0;

  unordered_map<TLit, TWeight> target_lit_to_weights;
  for (const auto& [weight, lit] : wlits) {
    target_lit_to_weights[lit] += weight;
    dd_topclauseweight += weight;
    if (weight != 1) dd_solver.problem_weighted = 1;
  }
  dd_topclauseweight += 1;

  deepdist::lit** dd_clause_lit;
  int* dd_clause_lit_count;
  int dd_nvars = MaxVar();
  int dd_nclauses =
      GetNumClauses() +
      (solver_options_.wcnf_mode ? 0 : static_cast<int>(wlits.size()));
  unsigned long long* dd_clause_weight;

  // dd_num_hclauses: the number of hard clauses
  dd_clause_lit = new deepdist::lit*[dd_nclauses + 10];
  dd_clause_lit_count = new int[dd_nclauses + 10];
  dd_clause_weight = new unsigned long long[dd_nclauses + 10];

  int* redunt_test = new int[dd_nvars + 10];
  memset(redunt_test, 0, sizeof(int) * (dd_nvars + 10));

  int tem_v, tem_sense, tem_lit_count;
  bool clause_reduent;
  // c counts the number of clauses (will be identical to
  // maxsat_formula->dd_nclauses, if no redundant clauses are identified)
  int c = 0;
  // maxsat_formula->nHard(): the number of hard clauses
  // The loop goes over every hard clause. It copies the clauses to dd's
  // data structures, while skipping tautologies and removing identical
  // literals. There is a very similar loop for soft clauses coming up next
  bool soft_clause = false;
  TWeight clause_weight = 0;
  vector<pair<size_t, TLit>> clause_relaxed_by;  // For ACNF mode

  auto SaveSolutionAndValue = [&]() {
    SigScopeBlocker block(SIGTERM);

    latest_maxsat_value_ = (TWeight)dd_solver.opt_unsat_weight;

    for (int v = 1; v <= dd_solver.num_vars; ++v) {
      if (dd_solver.cur_soln[v] == 0)
        latest_solution_[v] = TLitValue::FALSE;
      else
        latest_solution_[v] = TLitValue::TRUE;
    }

    for (const auto& [clause_idx, relaxed_by] : clause_relaxed_by) {
      // Clause UNSAT -> Relaxation literal must be SAT
      if (dd_solver.sat_count[clause_idx] == 0) {
        latest_solution_[lit_abs(relaxed_by)] =
            (relaxed_by < 0) ? TLitValue::FALSE : TLitValue::TRUE;
      } else {
        // Clause SAT -> Relaxation literal must be UNSAT
        latest_solution_[lit_abs(relaxed_by)] =
            (relaxed_by < 0) ? TLitValue::TRUE : TLitValue::FALSE;
      }
    }
  };

  if (solver_options_.wcnf_mode) {
    TLit max_wcnf_var = static_cast<TLit>(solver_options_.wcnf_max_var);
    for (size_t i = 0; i < clause_offsets_.size() - 1; ++i) {
      Lits<TLit> clause = Lits<TLit>(clauses_).subspan(
          clause_offsets_[i], clause_offsets_[i + 1] - clause_offsets_[i]);
      // allocate storage for the worst-case
      dd_clause_lit_count[c] = static_cast<int>(clause.size());
      dd_clause_lit[c] = new deepdist::lit[dd_clause_lit_count[c] + 1];
      clause_reduent = false;
      soft_clause = false;
      tem_lit_count = 0;
      for (TLit lit : clause) {
        if (lit_abs(lit) > max_wcnf_var) {
          soft_clause = true;
          clause_weight = target_lit_to_weights[lit];
          continue;
        }

        tem_v = lit_abs(lit);
        tem_sense = (lit < 0) ? 0 : 1;
        if (tem_v <= 0 || tem_v > dd_nvars) {
          clause_reduent = true;
        }
        if (redunt_test[tem_v] == 0) {
          redunt_test[tem_v] = tem_sense - 2;
          dd_clause_lit[c][tem_lit_count].var_num = tem_v;
          dd_clause_lit[c][tem_lit_count].sense = tem_sense;
          dd_clause_lit[c][tem_lit_count].clause_num = c;
          ++tem_lit_count;
        } else if (redunt_test[tem_v] == tem_sense - 2) {
          continue;
        } else {
          clause_reduent = true;
        }
      }

      // reset redunt_test only for literals we actually set
      for (int k = 0; k < tem_lit_count; ++k) {
        redunt_test[dd_clause_lit[c][k].var_num] = 0;
      }

      if (!clause_reduent && tem_lit_count > 0) {
        dd_clause_weight[c] = soft_clause ? clause_weight : dd_topclauseweight;
        dd_clause_lit_count[c] =
            tem_lit_count;  // actual size after skipping soft lits
        dd_clause_lit[c][tem_lit_count].var_num = 0;
        dd_clause_lit[c][tem_lit_count].sense = false;
        dd_clause_lit[c][tem_lit_count].clause_num = -1;
        ++c;
      } else {
        // nothing kept for this clause
        if (tem_lit_count == 0 && soft_clause) {
          unsat_assumps_soft_weight += clause_weight;
        }
        delete[] dd_clause_lit[c];
      }
    }
  } else {
    unordered_map<TLit, int> targets_num_appearences;
    bool target_found_in_clause = false;
    TLit first_target_found = 0;
    for (size_t i = 0; i < clause_offsets_.size() - 1; ++i) {
      size_t start = clause_offsets_[i];
      size_t len = clause_offsets_[i + 1] - start;
      target_found_in_clause = false;
      first_target_found = 0;
      for (size_t j = 0; j < len; ++j) {
        TLit lit = clauses_[start + j];
        if (target_lit_to_weights.count(lit) != 0) {
          if (target_found_in_clause) {
            // Multiple targets in the same clause
            targets_num_appearences[lit] = 2;
            targets_num_appearences[-lit] = 2;
            if (first_target_found != 0) {
              targets_num_appearences[first_target_found] = 2;
              targets_num_appearences[-first_target_found] = 2;
              first_target_found = 0;
            }
            continue;
          }
          // Potential relaxation literal
          targets_num_appearences[lit]++;
          target_found_in_clause = true;
          first_target_found = lit;
        }
        if (target_lit_to_weights.count(-lit) != 0) {
          // The target negation is also a target
          targets_num_appearences[-lit] = 2;
          targets_num_appearences[lit] = 2;
        }
      }
    }

    bool lit_assumed_false = false;
    bool lit_assumed_true = false;
    bool reduent_because_assumed = false;
    bool already_relaxed = false;
    TLit already_relaxed_by = 0;
    bool relax_lit_assumed = false;
    for (size_t i = 0; i < clause_offsets_.size() - 1; ++i) {
      Lits<TLit> clause = Lits<TLit>(clauses_).subspan(
          clause_offsets_[i], clause_offsets_[i + 1] - clause_offsets_[i]);
      // allocate storage for the worst-case
      dd_clause_lit_count[c] = static_cast<int>(clause.size());
      dd_clause_lit[c] = new deepdist::lit[dd_clause_lit_count[c] + 1];
      clause_reduent = false;
      reduent_because_assumed = false;
      tem_lit_count = 0;
      soft_clause = false;
      clause_weight = 0;
      already_relaxed = false;
      already_relaxed_by = 0;

      for (TLit lit : clause) {
        lit_assumed_false = false;
        lit_assumed_true = false;
        if (assump_lits.count(-lit) != 0) {
          lit_assumed_false = true;
        } else if (assump_lits.count(lit) != 0) {
          clause_reduent = reduent_because_assumed = true;
          lit_assumed_true = true;
        }

        auto it = targets_num_appearences.find(lit);
        if (it != targets_num_appearences.end() && it->second == 1) {
          if (already_relaxed) {
            // Relaxation literal must be unique
            soft_clause = false;
            targets_num_appearences[already_relaxed_by] = 2;
            targets_num_appearences[lit] = 2;
            relax_lit_assumed = false;
          } else if (target_lit_to_weights.count(-lit) == 0) {
            soft_clause = true;
            already_relaxed = true;
            already_relaxed_by = lit;
            relax_lit_assumed = lit_assumed_true || lit_assumed_false;
          }
          if (lit_assumed_true) {
            unsat_assumps_soft_weight += target_lit_to_weights[lit];
          } else {
            clause_weight += target_lit_to_weights[lit];
          }
          continue;
        }
        if (lit_assumed_false) continue;

        tem_v = lit_abs(lit);
        tem_sense = (lit < 0) ? 0 : 1;
        if (tem_v <= 0 || tem_v > dd_nvars) {
          clause_reduent = true;
        }
        if (redunt_test[tem_v] == 0) {
          redunt_test[tem_v] = tem_sense - 2;
          dd_clause_lit[c][tem_lit_count].var_num = tem_v;
          dd_clause_lit[c][tem_lit_count].sense = tem_sense;
          dd_clause_lit[c][tem_lit_count].clause_num = c;
          ++tem_lit_count;
        } else if (redunt_test[tem_v] == tem_sense - 2) {
          continue;
        } else {
          clause_reduent = true;
        }
      }

      // reset redunt_test only for literals we actually set
      for (int k = 0; k < tem_lit_count; ++k) {
        redunt_test[dd_clause_lit[c][k].var_num] = 0;
      }

      if (!clause_reduent && tem_lit_count > 0) {
        dd_clause_weight[c] = soft_clause ? clause_weight : dd_topclauseweight;
        dd_clause_lit_count[c] =
            tem_lit_count;  // actual size after skipping soft lits
        dd_clause_lit[c][tem_lit_count].var_num = 0;
        dd_clause_lit[c][tem_lit_count].sense = false;
        dd_clause_lit[c][tem_lit_count].clause_num = -1;
        if (soft_clause) {
          clause_relaxed_by.emplace_back(c, already_relaxed_by);
        }
        ++c;
      } else {
        // nothing kept for this clause
        if ((reduent_because_assumed || tem_lit_count == 0) && soft_clause) {
          unsat_assumps_soft_weight += clause_weight;
        }
        if (soft_clause && tem_lit_count > 0 && !relax_lit_assumed) {
          latest_solution_[lit_abs(already_relaxed_by)] =
              (already_relaxed_by < 0) ? TLitValue::TRUE : TLitValue::FALSE;
        }
        delete[] dd_clause_lit[c];
      }
    }

    for (const auto& [weight, lit] : wlits) {
      // Skip relaxation literals
      if (targets_num_appearences[lit] == 1 &&
          target_lit_to_weights.count(-lit) == 0) {
        continue;
      }
      // Skip satisfied (assumed) soft literals
      if (assump_lits.count(lit) != 0) {
        unsat_assumps_soft_weight += weight;
        continue;
      }
      // Collect unsatisfied (assumed) soft literal weights
      if (assump_lits.count(-lit) != 0) continue;

      dd_clause_lit_count[c] = 1;
      dd_clause_lit[c] = new deepdist::lit[2];
      tem_v = lit_abs(lit);
      tem_sense = (lit < 0) ? 1 : 0;  // Negated
      dd_clause_lit[c][0].var_num = tem_v;
      dd_clause_lit[c][0].sense = tem_sense;
      dd_clause_lit[c][0].clause_num = c;
      dd_clause_lit[c][1].var_num = 0;
      dd_clause_lit[c][1].sense = false;
      dd_clause_lit[c][1].clause_num = -1;
      dd_clause_weight[c] = weight;
      ++c;
    }
  }

  dd_nclauses = c;
  delete[] redunt_test;

  logger_.Log(VerbosityLevel::VERBOSE, "build DeepDist instance start!");
  logger_.Log(VerbosityLevel::VVERBOSE, "dd_nvars = {}", dd_nvars);
  logger_.Log(VerbosityLevel::VVERBOSE, "dd_nclauses = {}", dd_nclauses);
  logger_.Log(VerbosityLevel::VVERBOSE, "dd_topclauseweight = {}",
              dd_topclauseweight);
  logger_.Log(VerbosityLevel::VVERBOSE, "dd_problem_weighted = {}",
              dd_solver.problem_weighted);
  logger_.Log(VerbosityLevel::VVERBOSE, "dd_unsat_assumps_soft_weight = {}",
              unsat_assumps_soft_weight);

  dd_solver.build_instance(dd_nvars, dd_nclauses, dd_topclauseweight,
                           dd_clause_lit, dd_clause_lit_count,
                           dd_clause_weight);

  // free the temporary arrays (clause_lit pointers are now owned by dd_solver)
  delete[] dd_clause_lit;
  delete[] dd_clause_lit_count;
  delete[] dd_clause_weight;

  logger_.Log(VerbosityLevel::VERBOSE, "build DeepDist instance done!");
  logger_.Log("changing to DeepDist solver!!!");
  dd_solver.settings();

  vector<int> init_solu(dd_nvars + 1);
  for (int i = 1; i <= dd_nvars; ++i) {
    if (latest_solution_[i] == TLitValue::FALSE)
      init_solu[i] = 0;
    else
      init_solu[i] = 1;
  }

  // Seed local_opt_soln and best_soln for decimation
  for (int i = 1; i <= dd_nvars; ++i) {
    dd_solver.local_opt_soln[i] = init_solu[i];
    dd_solver.best_soln[i] = init_solu[i];
  }

  dd_solver.opt_unsat_weight = (long long)latest_maxsat_value_;
  deepdist::dd_start_timing();

  const auto ddTimeLimit = dd_solver.DEEPDIST_TIME_LIMIT;
  logger_.Log(VerbosityLevel::VERBOSE, "ddTimeLimit = {}", ddTimeLimit);

  int time_limit_for_ls = deepdist::dd_get_runtime() + ddTimeLimit;
  bool better_soln_found = false;

  // Run DeepDist with decimation-based multi-try local search
  deepdist::Decimation deci(dd_solver.var_lit, dd_solver.var_lit_count,
                            dd_solver.clause_lit, dd_solver.org_clause_weight,
                            dd_solver.top_clause_weight);
  deci.make_space(dd_solver.num_clauses, dd_solver.num_vars);

  unsigned long long total_step = 0;
  bool problem_solved = false;

  for (int tries = 1; tries < dd_solver.max_tries; ++tries) {
    deci.init(dd_solver.local_opt_soln, dd_solver.best_soln,
              dd_solver.unit_clause, dd_solver.unit_clause_count,
              dd_solver.clause_lit_count);

    if (1 == dd_solver.problem_weighted)
      deci.unit_prosess();
    else
      deci.hard_unit_prosess();

    dd_solver.init(deci.fix);

    long long local_opt = __LONG_LONG_MAX__;
    unsigned int current_max_flips = dd_solver.max_non_improve_flip;

    for (unsigned int step = 1; step < current_max_flips; ++step) {
      if (dd_solver.hard_unsat_nb == 0) {
        dd_solver.local_soln_feasible = 1;
        if (local_opt > dd_solver.soft_unsat_weight) {
          local_opt = dd_solver.soft_unsat_weight;
          current_max_flips = step + dd_solver.max_non_improve_flip;
        }
        long long candidate =
            dd_solver.soft_unsat_weight + (long long)unsat_assumps_soft_weight;
        if (candidate < dd_solver.opt_unsat_weight) {
          dd_solver.best_soln_feasible = 1;
          dd_solver.opt_unsat_weight = candidate;

          time_limit_for_ls = deepdist::dd_get_runtime() + ddTimeLimit;

          SaveSolutionAndValue();
          for (int v = 1; v <= dd_solver.num_vars; ++v) {
            dd_solver.best_soln[v] = dd_solver.cur_soln[v];
            dd_solver.local_opt_soln[v] = dd_solver.cur_soln[v];
          }

          better_soln_found = true;
          PrintLatestMaxSATValue();

          if (ShouldExitAfterSolutionFound() || latest_maxsat_value_ == 0) {
            problem_solved = true;
            break;
          }
        }
      }

      int flipvar = dd_solver.pick_var();
      if (flipvar == 0) {
        problem_solved = true;
        break;
      }
      dd_solver.flip(flipvar);
      dd_solver.time_stamp[flipvar] = step;
      total_step++;

      if (total_step % 1000 == 0) {
        if (deepdist::dd_get_runtime() > time_limit_for_ls) {
          logger_.Log(VerbosityLevel::VERBOSE, "DeepDist: time {}",
                      deepdist::dd_get_runtime());
          break;
        }
      }
    }

    if (problem_solved || deepdist::dd_get_runtime() > time_limit_for_ls ||
        time_limit_for_ls < 0) {
      break;
    }
  }

  if (better_soln_found) {
    if (solver_options_.solve_conservatively) {
      FixNoneTargetsPolaritiesConservative(wlits);
    }
  }
  deci.free_memory();
  dd_solver.free_memory();
  logger_.Log("DeepDist search done!");
  logger_.Log(VerbosityLevel::VVERBOSE, "total_step {} get_runtime {}",
              total_step, deepdist::dd_get_runtime());
}

template class Aperture::Solver<int32_t, uint64_t>;