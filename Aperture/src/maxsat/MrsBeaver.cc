#include <random>

#include "../Aperture.h"
#include "../constraints/Adder.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::MaxSATObvBS(
    Lits<TLit> assumps, WLits<TLit, TWeight> targets,
    function<bool()> ShouldExitAfterSolutionFound, bool ums) {
  vector<TLit> assumptions(assumps.begin(), assumps.end());
  vector<TLit> target_lits;
  target_lits.reserve(targets.size());
  for (const auto& [weight, lit] : targets) {
    target_lits.push_back(lit);
  }
  Lits<TLit> target_lits_view(target_lits);

  TWeight total_fixed_cost = 0;
  vector<TLitValue> current_model = latest_solution_;

  auto LitValueFromModel = [&](TLit lit) -> TLitValue {
    return (lit > 0) ? current_model[lit] : !current_model[-lit];
  };

  for (size_t i = 0; i < target_lits.size(); i++) {
    TLit lit = target_lits[i];
    assumptions.push_back(-lit);
    if (LitValueFromModel(lit) != TLitValue::FALSE) {
      SolverStatus status;
      if (solver_options_.disable_polosat) {
        status = SolveForMaxSAT(assumptions, targets);
      } else {
        status = Polosat(
            assumptions, target_lits_view.subspan(i + 1),
            [&](function<TLitValue(TLit)> LitValueFunc, void* user_ds) {
              return WeightedCostFrom(LitValueFunc, targets);
            },
            nullptr, nullptr, true);
      }

      if (status != SolverStatus::SAT) {
        assumptions.pop_back();
        assumptions.push_back(lit);
        total_fixed_cost += targets[i].first;
        if (total_fixed_cost >= latest_maxsat_value_) {
          break;  // Fixed too much
        }
      } else {  // SAT
        solver_->CopyModelTo(current_model);
        if (ums) {
          size_t k = i + 1;
          for (size_t j = k; j < target_lits.size(); j++) {
            if (LitValueFromModel(target_lits[j]) == TLitValue::FALSE) {
              if (k != j) {
                TLit temp = target_lits[k];
                target_lits[k] = target_lits[j];
                target_lits[j] = temp;
              }
              k++;
            }
          }
        }
      }
    }
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
MBExitReason Solver<TLit, TWeight>::MrsBeaver(
    Lits<TLit> assumps, WLits<TLit, TWeight> targets,
    const bool fix_model_value, function<bool()> ShouldExitAfterSolutionFound) {
  logger_.Log(
      "Starting MRS-Beaver with max iterations {} and obv conflict "
      "threshold {}.",
      solver_options_.mrs_beaver_max_iterations,
      solver_options_.mrs_beaver_obv_conflict_threshold);

  // Parameters preparation

  vector<TLit> assumptions(assumps.begin(), assumps.end());
  vector<pair<TWeight, TLit>> target_wlits;
  bool problem_weighted = false;
  target_wlits.reserve(targets.size());
  for (const auto& [weight, lit] : targets) {
    target_wlits.emplace_back(weight, lit);
    problem_weighted |= (weight != 1);
  }
  if (problem_weighted) {
    std::sort(target_wlits.begin(), target_wlits.end(),
              [](const pair<TWeight, TLit>& a, const pair<TWeight, TLit>& b) {
                return a.first > b.first;
              });
  }

  vector<TLit> target_lits;
  target_lits.reserve(target_wlits.size());
  for (const auto& [weight, lit] : target_wlits) {
    target_lits.push_back(lit);
  }

  // Checking if should exit early due to size estimation

  TWeight current_best_value = latest_maxsat_value_ + 1;
  bool prev_turn_off_due_to_size_answer = false;
  auto TurnOffDueToSize = [&]() {
    if (prev_turn_off_due_to_size_answer) return true;
    if (latest_maxsat_value_ < current_best_value) {
      current_best_value = latest_maxsat_value_;
    } else {
      return prev_turn_off_due_to_size_answer;
    }
    int64_t bound = static_cast<int64_t>(latest_maxsat_value_) - 1;
    const int32_t clauses_threshold =
        solver_options_.mrs_beaver_size_switch_to_complete;
    if (clauses_threshold == 0) return false;
    prev_turn_off_due_to_size_answer =
        problem_weighted ? Totalizer<TLit, TWeight>::IsLeqGenTotExceedsThr(
                               target_wlits, bound, clauses_threshold)
                         : Totalizer<TLit, TWeight>::IsLeqTotExceedsThr(
                               target_lits, bound, clauses_threshold);
    if (prev_turn_off_due_to_size_answer) {
      logger_.Log(VerbosityLevel::VERBOSE, "MRS-Beaver stopping due to size.");
    }
    return prev_turn_off_due_to_size_answer;
  };

  // Checking if should exit early due to lack of improvement

  uint32_t non_improving_iterations = 0;
  auto TurnOffDueToNonImprovement = [&]() {
    if (non_improving_iterations >=
        solver_options_.mrs_beaver_max_non_improving_iterations) {
      logger_.Log(VerbosityLevel::VERBOSE,
                  "MRS-Beaver stopping due to lack of "
                  "improvement after {} consecutive iterations.",
                  non_improving_iterations);
      return true;
    }
    return false;
  };

  // Callback for Polosat and ObvBS

  auto ShouldStopAfterSolutionFound = [&]() {
    return ShouldExitAfterSolutionFound() || TurnOffDueToSize();
  };

  // MrsBeaver's main loop

  mt19937 rng(solver_options_.mrs_beaver_seed);
  uint64_t orginal_conflict_threshold = solver_options_.conflict_threshold;
  CallWhenLeavingScope revert_conf_thr_when_leaving_scope([&]() {
    solver_options_.conflict_threshold = orginal_conflict_threshold;
  });

  solver_options_.conflict_threshold =
      solver_options_.mrs_beaver_obv_conflict_threshold;
  Polosat(
      assumptions, target_lits,
      [&](function<TLitValue(TLit)> LitValueFunc, void* user_ds) {
        return WeightedCostFrom(LitValueFunc, target_wlits);
      },
      [&](Lits<TLit>, void*) { return ShouldStopAfterSolutionFound(); },
      nullptr, true);

  TWeight latest_best_cost = latest_maxsat_value_;
  for (uint64_t iteration = 0;
       iteration < solver_options_.mrs_beaver_max_iterations &&
       !TurnOffDueToSize() && !TurnOffDueToNonImprovement();
       iteration++) {
    logger_.Log(VerbosityLevel::VERBOSE, "MRS-Beaver iteration {}",
                iteration + 1);

    MaxSATObvBS(assumptions, target_wlits, ShouldStopAfterSolutionFound,
                (iteration % 4 == 0 || iteration % 4 == 1) &&
                    !problem_weighted);  // UMS

    if (latest_maxsat_value_ < latest_best_cost) {
      if (ShouldExitAfterSolutionFound()) break;
      latest_best_cost = latest_maxsat_value_;
      non_improving_iterations = 0;
    } else {
      non_improving_iterations++;
    }

    auto ApplyToEachWeightBlock = [&](auto&& Func) {
      auto start = target_wlits.begin();
      auto it_end = target_wlits.end();
      while (start != it_end) {
        auto end = start + 1;
        while (end != it_end && end->first == start->first) end++;
        if (end > start + 1) Func(start, end);
        start = end;
      }
    };

    auto ReverseBlock = [&](auto start, auto end) { reverse(start, end); };

    auto WeightedShuffle = [&]() {
      vector<TWeight> cumulative_weights;
      cumulative_weights.reserve(target_wlits.size());
      TWeight sum = 0;
      for (const auto& [weight, lit] : target_wlits) {
        sum += weight;
        cumulative_weights.push_back(sum);
      }

      for (size_t i = 0; i < target_wlits.size(); i++) {
        TWeight base = (i > 0 ? cumulative_weights[i - 1] : 0);
        TWeight total_remaining = cumulative_weights.back() - base;
        if (total_remaining == 0) break;
        // Pick a random weight in the remaining range
        uniform_real_distribution<double> dist(
            0.0, static_cast<double>(total_remaining));
        TWeight target_weight = base + static_cast<TWeight>(dist(rng));
        // Find which target corresponds to that weight
        auto it = lower_bound(cumulative_weights.begin() + i,
                              cumulative_weights.end(), target_weight);
        size_t chosen = it - cumulative_weights.begin();
        chosen = min(chosen, target_wlits.size() - 1);

        if (chosen != i) {
          // Swap it
          TWeight diff = target_wlits[chosen].first - target_wlits[i].first;
          swap(target_wlits[i], target_wlits[chosen]);
          // Update cumulative weights for the remaining range
          for (size_t j = i; j <= chosen; j++) {
            cumulative_weights[j] += diff;
          }
        }
      }
    };

    auto WeightedReverse = [&]() {
      ApplyToEachWeightBlock(ReverseBlock);

      auto IsIsolated = [&](size_t idx) {
        TWeight w = target_wlits[idx].first;
        if (idx > 0 && target_wlits[idx - 1].first == w) return false;
        if (idx + 1 < target_wlits.size() && target_wlits[idx + 1].first == w)
          return false;
        return true;
      };

      for (size_t i = 0; i + 1 < target_wlits.size(); i++) {
        if (IsIsolated(i) && IsIsolated(i + 1)) {
          swap(target_wlits[i], target_wlits[i + 1]);
          i++;  // Skip the next element since we just swapped it into place
        }
      }
    };

    if (iteration % 4 == 0 && iteration > 0) {
      if (problem_weighted) {
        WeightedShuffle();
      } else {
        shuffle(target_wlits.begin(), target_wlits.end(), rng);
      }
    } else {
      if (problem_weighted) {
        WeightedReverse();
      } else {
        reverse(target_wlits.begin(), target_wlits.end());
      }
    }
  }

  return prev_turn_off_due_to_size_answer ? MBExitReason::SIZE
                                          : MBExitReason::ITERATIONS;
}

template class Aperture::Solver<int32_t, uint64_t>;