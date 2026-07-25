#include "../Aperture.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
double Solver<TLit, TWeight>::GetLatestBlackBoxValue() const {
  return latest_blackbox_value_;
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::ResetBlackBox() {
  ResetBeforeSolving();
  latest_blackbox_value_ = std::numeric_limits<TWeight>::max();
}

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::SolveBlackBox(
    Lits<TLit> assumps, Lits<TLit> observables,
    function<TWeight(function<TLitValue(TLit)>, void*)> PbFunc,
    function<bool(Lits<TLit>, void*)> CallbackOnSolutionFound, void* user_ds) {
  if (should_dump_) logger_.DumpSolveBlackBox(assumps, observables);

  if (!ValidAssumptions(assumps) || !ValidLits(observables)) {
    latest_error_reason_ =
        "Invalid assumptions or observables: some literals exceed the maximum "
        "variable index.";
    return SolverStatus::ERROR;
  }

  auto ShouldExitAfterSolutionFound = [&](Lits<TLit>, void*) {
    bool exit_by_callback = false;
    if (CallbackOnSolutionFound != nullptr) {
      exit_by_callback = CallbackOnSolutionFound(observables, user_ds);
    }
    return exit_by_callback;
  };
  return Polosat(assumps, observables, PbFunc, ShouldExitAfterSolutionFound,
                 user_ds, false);
}

template <ValidLiteral TLit, ValidWeight TWeight>
void Solver<TLit, TWeight>::PrintLatestBlackBoxValueAndTime() const {
  logger_.LogTimeO(latest_blackbox_value_);
}

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::SolveInitialSat(
    Lits<TLit> assumps, Lits<TLit> observables,
    function<TWeight(function<TLitValue(TLit)>, void*)> PbFunc, void* user_ds) {
  reference_wrapper<SatSolver<TLit>> initial_solver = *solver_;
  unique_ptr<SatSolver<TLit>> initial_solver_ptr;
  if (solver_options_.use_initial_solver) {
    logger_.Log("Using {} as initial SAT solver.",
                SolverTypeToName(solver_options_.initial_solver_type));

    initial_solver_ptr =
        BuildSecondarySolver(solver_options_.initial_solver_type, observables,
                             solver_options_.solve_optimistically,
                             solver_options_.use_target_bumping);
    initial_solver = *initial_solver_ptr;
  }
  if (solver_options_.use_target_bumping) {
    FixTargetsPolaritiesOptimistic(
        observables);  // Fix for the main solver anyway
  }
  if (solver_options_.use_target_bumping) {
    BumpTargetScores(observables);  // Bump for the main solver anyway
  }
  SolverStatus status = initial_solver.get().Solve(assumps);
  if (status == SolverStatus::SAT) {
    BlackBoxSolutionFoundFrom(initial_solver.get(), observables, PbFunc,
                              user_ds);
  }
  return status;
}

template class Aperture::Solver<int32_t, uint64_t>;