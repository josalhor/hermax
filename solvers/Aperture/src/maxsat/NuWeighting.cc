#include "NuWeighting.h"

#include <signal.h>

#include "../Aperture.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::NuWeighting(
    Lits<TLit> assumps, WLits<TLit, TWeight> wlits,
    function<bool()> ShouldExitAfterSolutionFound) {
  unordered_set<TLit> assump_lits(assumps.begin(), assumps.end());
  // if (maxsat_formula->using_nuweighting == false &&
  // maxsat_formula->nTotalLitCount() < 350000000)
  {
    nuweighting::NUWEIGHTING nuweighting_solver;
    nuweighting_solver.problem_weighted = 0;

    unsigned long long nuweighting_topclauseweight = 0;
    unsigned long long unsat_assumps_soft_weight = 0;

    unordered_map<TLit, TWeight> target_lit_to_weights;
    for (const auto& [weight, lit] : wlits) {
      target_lit_to_weights[lit] += weight;
      nuweighting_topclauseweight += weight;
      if (weight != 1) nuweighting_solver.problem_weighted = 1;
    }
    nuweighting_topclauseweight += 1;

    nuweighting::clauselit** nuweighting_clause_lit;
    int* nuweighting_clause_lit_count;
    int nuweighting_nvars = MaxVar();
    int nuweighting_nclauses =
        GetNumClauses() +
        (solver_options_.wcnf_mode ? 0 : static_cast<int>(wlits.size()));
    unsigned long long* nuweighting_clause_weight;

    const int problem_weighted = nuweighting_solver.problem_weighted;

    // nuweighting_num_hclauses: the number of hard clauses
    nuweighting_clause_lit =
        new nuweighting::clauselit*[nuweighting_nclauses + 10];
    nuweighting_clause_lit_count = new int[nuweighting_nclauses + 10];
    nuweighting_clause_weight =
        new unsigned long long[nuweighting_nclauses + 10];

    int* redunt_test = new int[nuweighting_nvars + 10];
    memset(redunt_test, 0, sizeof(int) * (nuweighting_nvars + 10));

    int tem_v, tem_sense, tem_lit_count;
    bool clause_reduent;
    // c counts the number of clauses (will be identical to
    // maxsat_formula->nuweighting_nclauses, if no redundant clauses are
    // identified)
    int c = 0;
    // maxsat_formula->nHard(): the number of hard clauses
    // The loop goes over every hard clause. It copies the clauses to
    // NUWEIGHTING's data structures, while skipping tautologies and removing
    // identical literals. There is a very similar loop for soft clauses coming
    // up next
    bool soft_clause = false;
    TWeight clause_weight = 0;
    vector<pair<size_t, TLit>> clause_relaxed_by;  // For ACNF mode

    auto SaveSolutionAndValue = [&]() {
      SigScopeBlocker block(SIGTERM);

      latest_maxsat_value_ = nuweighting_solver.opt_unsat_weight;

      for (int v = 1; v <= nuweighting_solver.num_vars; ++v) {
        if (nuweighting_solver.cur_soln[v] == 0)
          latest_solution_[v] = TLitValue::FALSE;
        else
          latest_solution_[v] = TLitValue::TRUE;
      }

      for (const auto& [clause_idx, relaxed_by] : clause_relaxed_by) {
        // Clause UNSAT -> Relaxation literal must be SAT
        if (nuweighting_solver.sat_count[clause_idx] == 0) {
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
        nuweighting_clause_lit_count[c] = static_cast<int>(clause.size());
        nuweighting_clause_lit[c] =
            new nuweighting::clauselit[nuweighting_clause_lit_count[c] + 1];
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
          if (tem_v <= 0 || tem_v > nuweighting_nvars) {
            clause_reduent = true;
          }
          if (redunt_test[tem_v] == 0) {
            redunt_test[tem_v] = tem_sense - 2;
            nuweighting_clause_lit[c][tem_lit_count].var_num = tem_v;
            nuweighting_clause_lit[c][tem_lit_count].sense = tem_sense;
            ++tem_lit_count;
          } else if (redunt_test[tem_v] == tem_sense - 2) {
            continue;
          } else {
            clause_reduent = true;
          }
        }
        // reset redunt_test only for literals we actually set
        for (int k = 0; k < tem_lit_count; ++k) {
          redunt_test[nuweighting_clause_lit[c][k].var_num] = 0;
        }

        if (!clause_reduent && tem_lit_count > 0) {
          nuweighting_clause_weight[c] =
              soft_clause ? clause_weight : nuweighting_topclauseweight;
          nuweighting_clause_lit_count[c] =
              tem_lit_count;  // actual size after skipping soft lits
          nuweighting_clause_lit[c][tem_lit_count].var_num = 0;
          nuweighting_clause_lit[c][tem_lit_count].sense = false;
          ++c;
        } else {
          // nothing kept for this clause
          if (tem_lit_count == 0 && soft_clause) {
            unsat_assumps_soft_weight += clause_weight;
          }
          delete[] nuweighting_clause_lit[c];
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
        nuweighting_clause_lit_count[c] = static_cast<int>(clause.size());
        nuweighting_clause_lit[c] =
            new nuweighting::clauselit[nuweighting_clause_lit_count[c] + 1];
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
          if (tem_v <= 0 || tem_v > nuweighting_nvars) {
            clause_reduent = true;
          }
          if (redunt_test[tem_v] == 0) {
            redunt_test[tem_v] = tem_sense - 2;
            nuweighting_clause_lit[c][tem_lit_count].var_num = tem_v;
            nuweighting_clause_lit[c][tem_lit_count].sense = tem_sense;
            ++tem_lit_count;
          } else if (redunt_test[tem_v] == tem_sense - 2) {
            continue;
          } else {
            clause_reduent = true;
          }
        }

        // reset redunt_test only for literals we actually set
        for (int k = 0; k < tem_lit_count; ++k) {
          redunt_test[nuweighting_clause_lit[c][k].var_num] = 0;
        }

        if (!clause_reduent && tem_lit_count > 0) {
          nuweighting_clause_weight[c] =
              soft_clause ? clause_weight : nuweighting_topclauseweight;
          nuweighting_clause_lit_count[c] =
              tem_lit_count;  // actual size after skipping soft lits
          nuweighting_clause_lit[c][tem_lit_count].var_num = 0;
          nuweighting_clause_lit[c][tem_lit_count].sense = false;
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
          delete[] nuweighting_clause_lit[c];
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

        nuweighting_clause_lit_count[c] = 1;
        nuweighting_clause_lit[c] = new nuweighting::clauselit[2];
        tem_v = lit_abs(lit);
        tem_sense = (lit < 0) ? 1 : 0;  // Negated
        nuweighting_clause_lit[c][0].var_num = tem_v;
        nuweighting_clause_lit[c][0].sense = tem_sense;
        nuweighting_clause_lit[c][1].var_num = 0;
        nuweighting_clause_lit[c][1].sense = false;
        nuweighting_clause_weight[c] = weight;
        ++c;
      }
    }

    nuweighting_nclauses = c;
    delete[] redunt_test;

    logger_.Log(VerbosityLevel::VERBOSE, "build NuWeighting instance start!");
    logger_.Log(VerbosityLevel::VVERBOSE, "nuweighting_nvars = {}",
                nuweighting_nvars);
    logger_.Log(VerbosityLevel::VVERBOSE, "nuweighting_nclauses = {}",
                nuweighting_nclauses);
    logger_.Log(VerbosityLevel::VVERBOSE, "nuweighting_topclauseweight = {}",
                nuweighting_topclauseweight);
    logger_.Log(VerbosityLevel::VVERBOSE, "problem_weighted = {}",
                problem_weighted);
    logger_.Log(VerbosityLevel::VVERBOSE, "unsat_assumps_soft_weight = {}",
                unsat_assumps_soft_weight);

    nuweighting_solver.build_instance(
        nuweighting_nvars, nuweighting_nclauses, nuweighting_topclauseweight,
        nuweighting_clause_lit, nuweighting_clause_lit_count,
        nuweighting_clause_weight);

    logger_.Log(VerbosityLevel::VERBOSE, "build NuWeighting instance done!");
    logger_.Log("changing to NuWeighting solver!!!");
    nuweighting_solver.settings();

    vector<int> init_solu(nuweighting_nvars + 1);
    for (int i = 1; i <= nuweighting_nvars; ++i) {
      if (latest_solution_[i] == TLitValue::FALSE)
        init_solu[i] = 0;
      else
        init_solu[i] = 1;
    }

    nuweighting_solver.init(init_solu);
    nuweighting_solver.opt_unsat_weight = latest_maxsat_value_;
    nuweighting::start_timing();

    const auto nuweightingTimeLimit = nuweighting_solver.NUWEIGHTING_TIME_LIMIT;
    logger_.Log(VerbosityLevel::VERBOSE, "nuweightingTimeLimit = {}",
                nuweightingTimeLimit);

    int time_limit_for_ls = nuweightingTimeLimit;
    bool better_soln_found = false;
    unsigned long long step = 0;
    unsigned long long full_unsat_weight = 0;
    long long time_steps = 0;
    // if (nuweighting_solver.if_using_neighbor)
    {
      if (problem_weighted == 0) {
        for (step = 1; step < nuweighting_solver.max_flips; ++step) {
          time_steps += 2;
          if (nuweighting_solver.hard_unsat_nb == 0) {
            full_unsat_weight = nuweighting_solver.soft_unsat_weight +
                                unsat_assumps_soft_weight;
            time_steps += 2;
            nuweighting_solver.local_soln_feasible = 1;
            if (full_unsat_weight < nuweighting_solver.opt_unsat_weight) {
              time_steps += 4;
              nuweighting_solver.max_flips =
                  step + nuweighting_solver.max_non_improve_flip;
              time_limit_for_ls = nuweighting::get_runtime() +
                                  nuweighting_solver.NUWEIGHTING_TIME_LIMIT;

              nuweighting_solver.best_soln_feasible = 1;
              nuweighting_solver.opt_unsat_weight = full_unsat_weight;

              SaveSolutionAndValue();

              better_soln_found = true;
              PrintLatestMaxSATValue();

              if (ShouldExitAfterSolutionFound() || latest_maxsat_value_ == 0) {
                break;
              }
            }
          }

          int flipvar = nuweighting_solver.pick_var(time_steps);
          if (flipvar == -1) {
            break;
          }
          if (nuweighting_solver.if_using_neighbor) {
            nuweighting_solver.flip2(flipvar, time_steps);
          } else {
            nuweighting_solver.flip(flipvar, time_steps);
          }
          nuweighting_solver.time_stamp[flipvar] = step;
          time_steps++;
          if (step % 1000 == 0) {
            if (time_steps > nuweighting_solver.cut_round)
            // if (nuweighting::get_runtime() > time_limit_for_ls)
            {
              break;
            }
          }
        }
      } else {
        for (step = 1; step < nuweighting_solver.max_flips; ++step) {
          if (nuweighting_solver.hard_unsat_nb == 0) {
            full_unsat_weight = nuweighting_solver.soft_unsat_weight +
                                unsat_assumps_soft_weight;
            time_steps++;
            if (full_unsat_weight < nuweighting_solver.opt_unsat_weight) {
              time_steps += 5;
              nuweighting_solver.best_soln_feasible = 1;
              nuweighting_solver.local_soln_feasible = 1;
              nuweighting_solver.max_flips =
                  step + nuweighting_solver.max_non_improve_flip;

              time_limit_for_ls = nuweighting::get_runtime() +
                                  nuweighting_solver.NUWEIGHTING_TIME_LIMIT;

              nuweighting_solver.opt_unsat_weight = full_unsat_weight;

              SaveSolutionAndValue();

              better_soln_found = true;
              PrintLatestMaxSATValue();

              if (ShouldExitAfterSolutionFound() || latest_maxsat_value_ == 0) {
                break;
              }
            }
          }

          int flipvar = nuweighting_solver.pick_var(time_steps);
          if (flipvar == -1) break;
          nuweighting_solver.flip(flipvar, time_steps);
          nuweighting_solver.time_stamp[flipvar] = step;
          time_steps++;
          if (step % 1000 == 0) {
            if (time_steps > nuweighting_solver.cut_round) {
              logger_.Log(VerbosityLevel::VVERBOSE, "{}",
                          nuweighting::get_runtime());
              break;
            }
          }
        }
      }
    }
    if (better_soln_found) {
      if (solver_options_.solve_conservatively) {
        FixNoneTargetsPolaritiesConservative(wlits);
      }
    }
    nuweighting_solver.free_memory();
    logger_.Log("nuweighting search done!");
    logger_.Log(VerbosityLevel::VVERBOSE,
                "step {} get_runtime {} time_limit_for_ls {}", step,
                nuweighting::get_runtime(), time_limit_for_ls);
  }
}

template class Aperture::Solver<int32_t, uint64_t>;