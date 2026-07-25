#include "../Aperture.h"
#include "../solvers/SolverFactory.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
TWeight Solver<TLit, TWeight>::GetLatestMaxSATValue() const {
  return latest_maxsat_value_;
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::ResetMaxSAT() {
  ResetBeforeSolving();
  latest_maxsat_value_ = numeric_limits<TWeight>::max();
  latest_maxsat_optimal_ = false;
  latest_maxsat_fixed_model_value_ = false;
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Solver<TLit, TWeight>::IsLatestMaxSATOptimal() const {
  return latest_maxsat_optimal_;
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Solver<TLit, TWeight>::IsLatestMaxSATFixedModelValue() const {
  return latest_maxsat_fixed_model_value_;
}

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::SolveMaxSAT(
    Lits<TLit> assumps, Lits<TLit> lits, bool fix_model_value,
    function<bool(Lits<TLit>, void*)> CallbackOnSolutionFound, void* user_ds) {
  if (should_dump_) logger_.DumpSolveMaxSAT(assumps, lits);

  vector<pair<TWeight, TLit>> wlits;
  wlits.reserve(lits.size());
  for (TLit l : lits) {
    wlits.emplace_back(1, l);
  }
  function<bool(WLits<TLit, TWeight>, void*)> WeightedCallback = nullptr;
  if (CallbackOnSolutionFound != nullptr) {
    WeightedCallback = [&](WLits<TLit, TWeight> wlits_span, void* ds) -> bool {
      return CallbackOnSolutionFound(lits, user_ds);
    };
  }

  // For current state where unweighted call just calls weighted call
  logger_.DisableDumpTemporarily();

  return SolveWeightedMaxSAT(assumps, wlits, fix_model_value, WeightedCallback,
                             user_ds);
}

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::SolveWeightedMaxSAT(
    Lits<TLit> assumps, WLits<TLit, TWeight> wlits, bool fix_model_value,
    function<bool(WLits<TLit, TWeight>, void*)> CallbackOnSolutionFound,
    void* user_ds) {
  if (should_dump_) logger_.DumpSolveWeightedMaxSAT(assumps, wlits);

  CallWhenLeavingScope reenable_dump([&]() { logger_.EnableDump(); });
  logger_.DisableDumpTemporarily();

  if (!ValidAssumptions(assumps) || !ValidWLits(wlits)) {
    latest_error_reason_ =
        "Invalid assumptions or weighted literals: some literals exceed the "
        "maximum variable index.";
    return SolverStatus::ERROR;
  }

  auto ShouldExitAfterSolutionFound = [&]() {
    bool exit_by_callback = false;
    if (CallbackOnSolutionFound != nullptr) {
      exit_by_callback = CallbackOnSolutionFound(wlits, user_ds);
    }
    return exit_by_callback || latest_maxsat_value_ == 0;
  };

  auto SetOptimalityDueToZeroCost = [&]() {
    latest_maxsat_optimal_ = true;
    if (fix_model_value) {
      for (const auto& [weight, lit] : wlits) AddClause({-lit});
      latest_maxsat_fixed_model_value_ = true;
    }
  };

  auto MrsBeaverExitToEncoderType = [&](MBExitReason reason) {
    switch (reason) {
      case MBExitReason::SIZE:
        return EncoderType::TOTALIZER;
      case MBExitReason::ITERATIONS:
      default:
        return EncoderType::ADDER;
    }
  };

  ResetMaxSAT();

  CallWhenLeavingScope clear_polarities_when_leaving_scope(
      [&]() { solver_->ClearAllPolarities(); });

  SolverStatus status = SolveInitialSat(assumps, wlits);
  if (status != SolverStatus::SAT) {
    return status;
  }
  if (ShouldExitAfterSolutionFound() || wlits.empty()) {
    if (latest_maxsat_value_ == 0) {
      SetOptimalityDueToZeroCost();
    }
    return SolverStatus::SAT;
  }

  if (solver_options_.use_local_search) {
    LocalSearchMaxSAT(assumps, wlits, ShouldExitAfterSolutionFound);
    if (ShouldExitAfterSolutionFound()) {
      if (latest_maxsat_value_ == 0) {
        SetOptimalityDueToZeroCost();
      }
      return SolverStatus::SAT;
    }
  }

  if (solver_options_.use_sat_based_optimization) {
    MBExitReason mrs_beaver_exit_reason = MrsBeaver(
        assumps, wlits, fix_model_value, ShouldExitAfterSolutionFound);
    if (ShouldExitAfterSolutionFound()) {
      if (latest_maxsat_value_ == 0) {
        SetOptimalityDueToZeroCost();
      }
      return SolverStatus::SAT;
    }
    EncoderType encoder_type =
        MrsBeaverExitToEncoderType(mrs_beaver_exit_reason);
    LSU(assumps, wlits, encoder_type, fix_model_value,
        ShouldExitAfterSolutionFound);
  }

  return SolverStatus::SAT;
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::PrintLatestMaxSATValue() const {
  logger_.LogO(latest_maxsat_value_);
  PrintLatestMaxSATValueAndTime();
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::PrintLatestMaxSATValueAndTime() const {
  logger_.LogTimeO(latest_maxsat_value_);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::PrintLatestBlackBoxValue() const {
  logger_.LogO(latest_blackbox_value_);
  PrintLatestBlackBoxValueAndTime();
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::SaveAndPrintLatestMaxSATValue(
    WLits<TLit, TWeight> wlits) {
  auto current_cost = WeightedCost(wlits);
  latest_maxsat_value_ = min(latest_maxsat_value_, current_cost);
  PrintLatestMaxSATValue();
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::MaxSATSolutionFoundFrom(
    const SatSolver<TLit>& solver, WLits<TLit, TWeight> wlits) {
  SaveLatestSolutionFromSolver(solver);
  SaveAndPrintLatestMaxSATValue(wlits);
  if (solver_options_.solve_conservatively) {
    FixNoneTargetsPolaritiesConservative(wlits);
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::MaxSATSolutionFound(WLits<TLit, TWeight> wlits) {
  MaxSATSolutionFoundFrom(*solver_, wlits);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::MaxSATSolutionFoundFrom(
    const SatSolver<TLit>& solver, Lits<TLit> lits, TWeight value) {
  SaveLatestSolutionFromSolver(solver);
  latest_maxsat_value_ = value;
  PrintLatestMaxSATValue();
  if (solver_options_.solve_conservatively) {
    FixNoneTargetsPolaritiesConservative(lits);
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::MaxSATSolutionFound(Lits<TLit> lits,
                                                TWeight value) {
  MaxSATSolutionFoundFrom(*solver_, lits, value);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::MaxSATSolutionFoundFrom(
    const SatSolver<TLit>& solver, WLits<TLit, TWeight> wlits, TWeight value) {
  SaveLatestSolutionFromSolver(solver);
  latest_maxsat_value_ = value;
  PrintLatestMaxSATValue();
  if (solver_options_.solve_conservatively) {
    FixNoneTargetsPolaritiesConservative(wlits);
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::MaxSATSolutionFound(WLits<TLit, TWeight> wlits,
                                                TWeight value) {
  MaxSATSolutionFoundFrom(*solver_, wlits, value);
}

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::SolveInitialSat(
    Lits<TLit> assumps, WLits<TLit, TWeight> wlits) {
  solver_->ClearAllPolarities();
  if (solver_options_.solve_optimistically) {
    FixTargetsPolaritiesOptimistic(wlits);  // Fix for the main solver anyway
  }
  if (solver_options_.use_target_bumping) {
    BumpTargetScores(wlits);  // Bump for the main solver anyway
  }

  reference_wrapper<SatSolver<TLit>> initial_solver = *solver_;
  unique_ptr<SatSolver<TLit>> initial_solver_ptr;
  if (solver_options_.use_initial_solver) {
    logger_.Log("Using {} as initial SAT solver.",
                SolverTypeToName(solver_options_.initial_solver_type));

    initial_solver_ptr =
        BuildSecondarySolver(solver_options_.initial_solver_type, wlits,
                             solver_options_.solve_optimistically,
                             solver_options_.use_target_bumping);
    initial_solver = *initial_solver_ptr;
  }

  SolverStatus status = initial_solver.get().Solve(assumps);
  if (status == SolverStatus::SAT) {
    MaxSATSolutionFoundFrom(initial_solver.get(), wlits);
  }

  return status;
}

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::SolveForMaxSAT(Lits<TLit> assumps,
                                                   WLits<TLit, TWeight> wlits) {
  SolverStatus status = SolveLimited(assumps);
  if (status != SolverStatus::SAT) {
    return status;
  }
  TWeight value = WeightedCostIn(*solver_, wlits);
  if (value < latest_maxsat_value_) {
    MaxSATSolutionFound(wlits, value);
  }
  return SolverStatus::SAT;
}

template class Aperture::Solver<int32_t, uint64_t>;