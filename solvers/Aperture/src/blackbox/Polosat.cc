#include "../Aperture.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::Polosat(
    Lits<TLit> assumps, Lits<TLit> observables,
    function<TWeight(function<TLitValue(TLit)>, void*)> PbFunc,
    function<bool(Lits<TLit>, void*)> CallbackOnSolutionFound, void* user_ds,
    const bool maxsat_call) {
  auto ShouldExitAfterSolutionFound = [&]() {
    bool exit_by_callback = false;
    if (CallbackOnSolutionFound != nullptr) {
      exit_by_callback = CallbackOnSolutionFound(observables, user_ds);
    }
    return (maxsat_call ? latest_maxsat_value_ == 0
                        : latest_blackbox_value_ == 0) ||
           exit_by_callback;
  };

  CallWhenLeavingScope clear_polarities_when_leaving_scope([&]() {
    if (!maxsat_call) solver_->ClearAllPolarities();
  });

  if (!maxsat_call) {
    ResetBlackBox();

    SolverStatus status =
        SolveInitialSat(assumps, observables, PbFunc, user_ds);
    if (status != SolverStatus::SAT) {
      return status;
    }
    if (ShouldExitAfterSolutionFound()) {
      return SolverStatus::SAT;
    }
  }

  vector<TLit> assumptions(assumps.begin(), assumps.end());
  vector<TLit> bad_lits;
  bad_lits.reserve(observables.size());
  bool good_epoch = true;
  uint64_t improving_models = 1;
  const uint64_t initial_num_implications = solver_->GetNumImplications();
  const auto polosat_start_time = Clock::now();
  TWeight best_value =
      maxsat_call ? latest_maxsat_value_ : latest_blackbox_value_;
  bool was_sat_at_least_once = !maxsat_call;  // In blackbox we must be SAT here
  vector<TLitValue> current_model = latest_solution_;

  auto ShouldStopDueToPropsPerModelThreshold = [&]() {
    return solver_options_.use_polosat_props_per_model_threshold &&
           maxsat_call && improving_models > 0 &&
           (double)(solver_->GetNumImplications() - initial_num_implications) /
                   improving_models >
               solver_options_.max_props_per_model;
  };

  auto ShouldStopDueToModelsPerSecThreshold = [&]() {
    return solver_options_.use_polosat_model_per_sec_threshold && maxsat_call &&
           improving_models > 0 &&
           (double)improving_models / chrono::duration_cast<chrono::seconds>(
                                          Clock::now() - polosat_start_time)
                                          .count() <
               solver_options_.min_models_per_sec;
  };

  auto LitValueFunc = [&](TLit lit) -> TLitValue {
    return (lit > 0) ? current_model[lit] : !current_model[-lit];
  };

  auto ClearNonBadLits = [&](vector<TLit>& bad_lits) {
    bad_lits.erase(
        remove_if(bad_lits.begin(), bad_lits.end(),
                  [&](TLit& l) { return LitValueFunc(l) != TLitValue::TRUE; }),
        bad_lits.end());
  };

  for (int epoch = 0; epoch < solver_options_.polosat_max_epochs &&
                      good_epoch && !ShouldStopDueToPropsPerModelThreshold() &&
                      !ShouldStopDueToModelsPerSecThreshold() &&
                      !ShouldExitAfterSolutionFound();
       epoch++) {
    good_epoch = false;

    bad_lits.clear();
    for (TLit lit : observables) {
      TLitValue val = LitValue(lit);
      assert(val == TLitValue::TRUE || val == TLitValue::FALSE);
      if (val == TLitValue::TRUE) {
        bad_lits.push_back(lit);
      }
    }

    size_t obs_index = observables.size() - 1;
    vector<TLit> original_assumptions;

    while (!bad_lits.empty() && !ShouldStopDueToPropsPerModelThreshold() &&
           !ShouldStopDueToModelsPerSecThreshold()) {
      TLit lit = bad_lits.back();
      bad_lits.pop_back();

      SolverStatus status;

      if (maxsat_call) {
        if (solver_options_.polosat_weighted_obv_strategy) {
          while (observables[obs_index] != lit) {
            TLit obs_lit = observables[obs_index];
            assumptions.push_back(
                LitValue(obs_lit) == TLitValue::TRUE ? obs_lit : -obs_lit);
            --obs_index;
          }

          assumptions.push_back(-lit);
          status = SolveLimited(assumptions);
          assumptions.pop_back();

          if (status == SolverStatus::SAT) {
            solver_->CopyModelTo(current_model);
          } else {
            original_assumptions.clear();
            original_assumptions = assumptions;
            assumptions.resize(assumps.size());

            assumptions.push_back(-lit);
            status = SolveLimited(assumptions);
            assumptions = original_assumptions;

            if (status == SolverStatus::SAT) {
              solver_->CopyModelTo(current_model);
            }
          }
        } else {
          assumptions.push_back(-lit);
          status = SolveLimited(assumptions);
          assumptions.pop_back();

          if (status == SolverStatus::SAT) {
            solver_->CopyModelTo(current_model);
          }

          if (status != SolverStatus::SAT ||
              PbFunc(LitValueFunc, user_ds) >= best_value) {
            original_assumptions.clear();
            original_assumptions = assumptions;
            while (observables[obs_index] != lit) {
              TLit obs_lit = observables[obs_index];
              assumptions.push_back(
                  LitValue(obs_lit) == TLitValue::TRUE ? obs_lit : -obs_lit);
              --obs_index;
            }

            assumptions.push_back(-lit);
            auto res = SolveLimited(assumptions);
            assumptions = original_assumptions;
            if (res == SolverStatus::SAT) {
              solver_->CopyModelTo(current_model);
            }
          }
        }
      } else {
        assumptions.push_back(-lit);
        status = SolveLimited(assumptions);
        assumptions.pop_back();

        if (status == SolverStatus::SAT) {
          solver_->CopyModelTo(current_model);
        }
      }

      if (status == SolverStatus::SAT) {
        was_sat_at_least_once = true;
        TWeight current_value = PbFunc(LitValueFunc, user_ds);
        if (current_value < best_value) {
          best_value = current_value;
          improving_models++;
          if (maxsat_call) {
            MaxSATSolutionFound(observables, current_value);
          } else {
            BlackBoxSolutionFound(observables, PbFunc, user_ds);
          }
          good_epoch = true;
          if (ShouldExitAfterSolutionFound()) {
            return SolverStatus::SAT;
          }
          ClearNonBadLits(bad_lits);
        } else {
          if (solver_options_.polosat_update_bits_on_each_sat_model) {
            ClearNonBadLits(bad_lits);
          }
        }
      }
    }
  }

  if (ShouldStopDueToPropsPerModelThreshold()) {
    logger_.Log("Stopping polosat due to props/model threshold.");
    solver_options_.disable_polosat = true;
  }

  if (ShouldStopDueToModelsPerSecThreshold()) {
    logger_.Log("Stopping polosat due to models/sec threshold.");
    solver_options_.disable_polosat = true;
  }

  return was_sat_at_least_once ? SolverStatus::SAT : SolverStatus::UNSAT;
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::SaveAndPrintLatestBlackBoxValue(TWeight value) {
  latest_blackbox_value_ = min(latest_blackbox_value_, value);
  PrintLatestBlackBoxValue();
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::BlackBoxSolutionFoundFrom(
    const SatSolver<TLit>& solver, Lits<TLit> observables,
    function<TWeight(function<TLitValue(TLit)>, void*)> PbFunc, void* user_ds) {
  SaveLatestSolutionFromSolver(solver);
  auto value = PbFunc(
      [&](TLit lit) -> TLitValue { return LitValue(lit, solver); }, user_ds);
  SaveAndPrintLatestBlackBoxValue(value);
  if (solver_options_.solve_conservatively) {
    FixNoneTargetsPolaritiesConservative(observables);
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::BlackBoxSolutionFound(
    Lits<TLit> observables,
    function<TWeight(function<TLitValue(TLit)>, void*)> PbFunc, void* user_ds) {
  BlackBoxSolutionFoundFrom(*solver_, observables, PbFunc, user_ds);
}

template class Aperture::Solver<int32_t, uint64_t>;