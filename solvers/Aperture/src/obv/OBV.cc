#include "../ATypes.h"
#include "../Aperture.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::SolveOBV(
    Lits<TLit> assumps, Lits<TLit> targets,
    function<bool(Lits<TLit>, void*)> CallbackOnSolutionFound, void* user_ds) {
  if (should_dump_) logger_.DumpSolveOBV(assumps, targets);

  CallWhenLeavingScope reenable_dump([&]() { logger_.EnableDump(); });
  logger_.DisableDumpTemporarily();

  if (!ValidAssumptions(assumps) || !ValidLits(targets)) {
    latest_error_reason_ =
        "Invalid assumptions or targets: some literals exceed the maximum "
        "variable index.";
    return SolverStatus::ERROR;
  }

  ResetBeforeSolving();

  return ObvBS(assumps, targets, CallbackOnSolutionFound, user_ds);
}

template <ValidLiteral TLit, ValidWeight TWeight>
SolverStatus Solver<TLit, TWeight>::SolveInitialSat(Lits<TLit> assumps,
                                                    Lits<TLit> targets) {
  reference_wrapper<SatSolver<TLit>> initial_solver = *solver_;
  unique_ptr<SatSolver<TLit>> initial_solver_ptr;
  if (solver_options_.use_initial_solver) {
    logger_.Log("Using {} as initial SAT solver.",
                SolverTypeToName(solver_options_.initial_solver_type));

    initial_solver_ptr =
        BuildSecondarySolver(solver_options_.initial_solver_type, targets,
                             solver_options_.solve_optimistically,
                             solver_options_.use_target_bumping);
    initial_solver = *initial_solver_ptr;
  }
  if (solver_options_.use_target_bumping) {
    FixTargetsPolaritiesOptimistic(targets);  // Fix for the main solver anyway
  }
  if (solver_options_.use_target_bumping) {
    BumpTargetScores(targets);  // Bump for the main solver anyway
  }
  SolverStatus status = initial_solver.get().Solve(assumps);
  if (status == SolverStatus::SAT) {
    SaveLatestSolutionFromSolver(initial_solver.get());
  }
  return status;
}

template class Aperture::Solver<int32_t, uint64_t>;