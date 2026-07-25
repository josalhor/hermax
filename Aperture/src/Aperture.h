#pragma once

#include <atomic>
#include <functional>
#include <memory>
#include <optional>
#include <span>
#include <unordered_set>
#include <variant>
#include <vector>

#include "AOptions.h"
#include "ATypes.h"
#include "constraints/Totalizer.h"
#include "logging/Logger.h"
#include "solvers/SatSolver.h"

namespace Aperture {

template <ValidLiteral TLit = int32_t, ValidWeight TWeight = uint64_t>
class Solver {
 public:
  /* Solver and SAT Solving */

  // Constructor, takes ownership of a SatSolver instance
  Solver(std::unique_ptr<SatSolver<TLit>> solver,
         const SolverOptions& options = SolverOptions());
  // Constructor that creates a SatSolver instance of the given type
  Solver(SolverType solver_type,
         const std::unordered_map<std::string, std::string>& sat_solver_params =
             {},
         const SolverOptions& options = SolverOptions());
  // Adds a clause to the solver
  bool AddClause(Lits<TLit> clause);
  // Adds a clause to the solver
  // from initializer list, i.e. AddClause({ lit1, lit2, ... })
  bool AddClause(std::initializer_list<TLit> clause) {
    std::vector<TLit> clause_vec(clause);
    return AddClause(clause_vec);
  }
  // Moves and adds multiple clauses to the solver
  // Note - this will only work on a freshly created solver
  bool InitClauses(std::vector<TLit>&& clauses,
                   std::vector<size_t>&& clause_offsets);
  // Solves the current set of clauses with optional assumptions
  SolverStatus Solve(Lits<TLit> assumps = {});
  // Returns the latest solution/model from the solver
  std::vector<TLitValue> GetLatestSolution() const;
  // Creates a new variable in the solver
  TLit NewVar();
  // Returns the maximum variable currently in the solver (i.e. the highest
  // variable that was created via NewVar)
  TLit MaxVar() const;
  // Returns the variable value of a given variable in the latest solution
  // i.e. the value of |lit|. For example if lit = 5 or lit = -5, it returns
  // the value of variable 5
  TLitValue VarValue(TLit lit) const;
  // Returns the literal value of a given literal in the latest solution
  // For example if lit = 5, it returns the value of literal 5
  // if lit = -5, it returns the value of literal -5
  TLitValue LitValue(TLit lit) const;
  // Gets the current verbosity level (0 = silent, higher = more verbose)
  VerbosityLevel GetVerbosityLevel() const;
  // Sets the verbosity level (0 = silent, higher = more verbose)
  void SetVerbosityLevel(VerbosityLevel level);
  // Enables or disables colored output in the terminal
  void SetEnableOutputColoring(bool enable);
  // Returns the reason for the last error that occurred in the solver, or an
  // empty string if no error has occurred or the reason is unknown
  std::string GetLatestErrorReason() const;
  // Sets the parameter `param_name` with the given value.
  void SetParam(const std::string& param_name, double value);
  // Interrupts the current solving process
  void Interrupt();

  // Cardinality and PB Constrains

  // Returns the output variables of a totalizer encoding for the given
  // literals. RHS simplification can be optionally provided to limit the size
  // of the output to rhs_simplification + 1 variables, potentially
  // simplifying the encoding when only an upper bound on the cardinality is
  // needed.
  std::vector<TLit> GetTotalizer(
      Lits<TLit> lits, TLit selector,
      std::optional<uint64_t> rhs_simplification = std::nullopt);

  // Returns the output variables of a generalized totalizer encoding for the
  // given weighted literals. RHS simplification can be optionally provided to
  // limit the weight of the last output variable to rhs_simplification + 1,
  // potentially simplifying the encoding when only an upper bound on the
  // total pseudo-Boolean value is needed.
  std::vector<std::pair<TWeight, TLit>> GetGenTotalizer(
      WLits<TLit, TWeight> wlits, TLit selector,
      std::optional<uint64_t> rhs_simplification = std::nullopt);

  // Cardinality Constraints

  // Adds a cardinality constraint of the form Σ_i lits[i] < rhs
  bool AddConstraintLessThan(Lits<TLit> lits, uint64_t rhs,
                             std::optional<TLit> selector = std::nullopt) {
    return AddCardinalityConstraint(lits, Predicate::LT, rhs, selector);
  }
  // Adds a cardinality constraint of the form Σ_i lits[i] <= rhs
  bool AddConstraintLessThanEqual(Lits<TLit> lits, uint64_t rhs,
                                  std::optional<TLit> selector = std::nullopt) {
    return AddCardinalityConstraint(lits, Predicate::LEQ, rhs, selector);
  }
  // Adds a cardinality constraint of the form Σ_i lits[i] == rhs
  bool AddConstraintEqual(Lits<TLit> lits, uint64_t rhs,
                          std::optional<TLit> selector = std::nullopt) {
    return AddCardinalityConstraint(lits, Predicate::EQ, rhs, selector);
  }
  // Adds a cardinality constraint of the form Σ_i lits[i] >= rhs
  bool AddConstraintGreaterThanEqual(
      Lits<TLit> lits, uint64_t rhs,
      std::optional<TLit> selector = std::nullopt) {
    return AddCardinalityConstraint(lits, Predicate::GEQ, rhs, selector);
  }
  // Adds a cardinality constraint of the form Σ_i lits[i] > rhs
  bool AddConstraintGreaterThan(Lits<TLit> lits, uint64_t rhs,
                                std::optional<TLit> selector = std::nullopt) {
    return AddCardinalityConstraint(lits, Predicate::GT, rhs, selector);
  }
  // Adds a cardinality constraint according to the given predicate:
  // Σ_i lits[i] < rhs if pred is LT
  // Σ_i lits[i] <= rhs if pred is LEQ
  // Σ_i lits[i] == rhs if pred is EQ
  // Σ_i lits[i] >= rhs if pred is GEQ
  // Σ_i lits[i] > rhs if pred is GT
  bool AddCardinalityConstraint(Lits<TLit> lits, Predicate pred, uint64_t rhs,
                                std::optional<TLit> selector = std::nullopt);

  // Pseudo-Boolean Constraints

  // Adds a pseudo-Boolean constraint of the form
  // Σ_i wlits[i].weight * wlits[i].lit < rhs
  bool AddConstraintLessThan(WLits<TLit, TWeight> wlits, uint64_t rhs,
                             std::optional<TLit> selector = std::nullopt) {
    return AddPBConstraint(wlits, Predicate::LT, rhs, selector);
  }
  // Adds a pseudo-Boolean constraint of the form
  // Σ_i wlits[i].weight * wlits[i].lit <= rhs
  bool AddConstraintLessThanEqual(WLits<TLit, TWeight> wlits, uint64_t rhs,
                                  std::optional<TLit> selector = std::nullopt) {
    return AddPBConstraint(wlits, Predicate::LEQ, rhs, selector);
  }

  // Adds a pseudo-Boolean constraint according to the given predicate:
  // Σ_i wlits[i].weight * wlits[i].lit < rhs if pred is LT
  // Σ_i wlits[i].weight * wlits[i].lit <= rhs if pred is LEQ
  // Note: only supports < and <= currently.
  bool AddPBConstraint(WLits<TLit, TWeight> wlits, Predicate pred, uint64_t rhs,
                       std::optional<TLit> selector = std::nullopt);

  /* SAT-based Optimization Solving */

  // Solving MaxSAT

  // Returns the latest MaxSAT value found in the last MaxSAT solving call
  TWeight GetLatestMaxSATValue() const;
  // Returns true the latest MaxSAT solution found is proven optimal, false
  // otherwise
  bool IsLatestMaxSATOptimal() const;
  // Returns true if the latest MaxSAT solution was able to fix the model
  // value (per user request), false otherwise
  bool IsLatestMaxSATFixedModelValue() const;

  // Performs unwieghted MaxSAT solving with optional callback on new
  // solutions. The literals usually represent soft clauses with unit weights
  // (relaxation literals) - but are not restricted to that. The
  // CallbackOnSolutionFound function should return true to continue solving,
  // false to stop.
  SolverStatus SolveMaxSAT(
      Lits<TLit> assumps, Lits<TLit> lits, bool fix_model_value,
      std::function<bool(Lits<TLit>, void*)> CallbackOnSolutionFound = nullptr,
      void* user_ds = nullptr);
  // Performs weighted MaxSAT solving with optional callback on new solutions
  // The literals usually represent soft clauses with associated weights
  // (relaxation literals) - but are not restricted to that
  // The CallbackOnSolutionFound function should return true to continue
  // solving, false to stop.
  SolverStatus SolveWeightedMaxSAT(
      Lits<TLit> assumps, WLits<TLit, TWeight> wlits, bool fix_model_value,
      std::function<bool(WLits<TLit, TWeight>, void*)> CallbackOnSolutionFound =
          nullptr,
      void* user_ds = nullptr);

  // Solving BlackBox

  // Returns the latest black-box function value found in the last black-box
  // optimization solving call
  double GetLatestBlackBoxValue() const;

  // Performs BlackBox optimization solving. That is, it tries to minimize the
  // value returned by the provided BlackBox function PbFunc. PbFunc should be
  // monotone w.r.t. the observables provided, i.e. assigning an observable
  // FALSE will strictly decrease the value returned by it. The
  // CallbackOnSolutionFound function should return true to continue solving
  // after an improving solution is found, false to stop.
  SolverStatus SolveBlackBox(
      Lits<TLit> assumps, Lits<TLit> observables,
      std::function<TWeight(std::function<TLitValue(TLit)>, void*)> PbFunc,
      std::function<bool(Lits<TLit>, void*)> CallbackOnSolutionFound = nullptr,
      void* user_ds = nullptr);

  // Solving OBV

  SolverStatus SolveOBV(
      Lits<TLit> assumps, Lits<TLit> targets,
      std::function<bool(Lits<TLit>, void*)> CallbackOnSolutionFound = nullptr,
      void* user_ds = nullptr);

  /* Output Functions */

  // Prints the latest solution to standard output in 'o <value>' format
  // Also prints  the latest solution and time in higher verbosity levels -
  // see PrintLatestMaxSATValueAndTime()
  void PrintLatestMaxSATValue() const;
  // Prints the latest MaxSAT value and time since last StartTiming() call in
  // 'timeo <time_in_seconds> <value>' format
  void PrintLatestMaxSATValueAndTime() const;
  // Prints the latest black-box function value in 'o <value>' format
  void PrintLatestBlackBoxValue() const;
  // Prints the latest BlackBox value and time since last
  // StartTiming() call in 'timeo <time_in_seconds> <value>' format
  void PrintLatestBlackBoxValueAndTime() const;

 protected:
  /* Solver and SAT Solving */

  Logger& logger_ = Logger::Instance();

  std::unique_ptr<SatSolver<TLit>> solver_;

  // For initial solver caching in case it equals the main solvers type
  std::optional<SolverType> main_solver_type_;

  using ParamType = std::variant<bool*, uint64_t*, int*, double*, SolverType*,
                                 LocalSearchSolverType*>;
  SolverOptions solver_options_;
  std::unordered_map<std::string, ParamType> params_map_;

  std::vector<TLit> clauses_;
  std::vector<size_t> clause_offsets_;
  std::vector<TLitValue> latest_solution_;
  bool should_dump_ = logger_.ShouldDump();

  std::string latest_error_reason_;

  // Cardinality and PB Constrains

  Totalizer<TLit, TWeight> totalizer_;

  /* SAT-based Optimization Solving */

  TWeight latest_maxsat_value_ = std::numeric_limits<TWeight>::max();
  bool latest_maxsat_fixed_model_value_ = false;
  bool latest_maxsat_optimal_ = false;
  TWeight latest_blackbox_value_ = std::numeric_limits<TWeight>::max();

  /* Solver and SAT Solving */

  void ResetBeforeSolving();

  // Saves the latest solution from a given SAT solver
  void SaveLatestSolutionFromSolver(const SatSolver<TLit>& solver);
  // Saves the latest solution from the underlying SAT solver
  void SaveLatestSolutionFromSolver() {
    SaveLatestSolutionFromSolver(*solver_);
  }
  // Returns true if all assumptions are valid (variables exist in the solver)
  bool ValidAssumptions(Lits<TLit> assumps) const;
  // Returns true if all literals are valid (variables exist in the solver)
  bool ValidLits(Lits<TLit> lits) const;
  // Returns true if all weighted literals are valid (variables exist in the
  bool ValidWLits(WLits<TLit, TWeight> wlits) const;
  // Solves the current set of clauses under the given assumptions with the
  // currently set conflict threshold
  SolverStatus SolveLimited(Lits<TLit> assumps);
  // Returns the value of a given literal in the latest solution of the given
  // solver
  TLitValue LitValue(TLit lit, const SatSolver<TLit>& solver) const;
  // Returns the number of clauses currently in the solver
  size_t GetNumClauses() const;
  void InitParamsMap();

  /* SAT-based Optimization Solving */

  std::unique_ptr<SatSolver<TLit>> BuildSecondarySolver(
      SolverType solver_type, Lits<TLit> lits,
      bool fix_target_polarities = false, bool bump_target_scores = false);
  std::unique_ptr<SatSolver<TLit>> BuildSecondarySolver(
      SolverType solver_type, WLits<TLit, TWeight> wlits,
      bool fix_target_polarities = false, bool bump_target_scores = false);

  TWeight UnweightedCostIn(const SatSolver<TLit>& solver,
                           Lits<TLit> lits) const;
  TWeight UnweightedCost(Lits<TLit> lits) const;
  TWeight UnweightedCostFrom(std::function<TLitValue(TLit)> LitValueFunc,
                             Lits<TLit> lits) const;
  TWeight WeightedCostIn(const SatSolver<TLit>& solver,
                         WLits<TLit, TWeight> wlits) const;
  TWeight WeightedCost(WLits<TLit, TWeight> wlits) const;
  TWeight WeightedCostFrom(std::function<TLitValue(TLit)> LitValueFunc,
                           WLits<TLit, TWeight> wlits) const;

  void FixTargetsPolaritiesOptimisticFor(SatSolver<TLit>& solver,
                                         Lits<TLit> targets);
  void FixTargetsPolaritiesOptimisticFor(SatSolver<TLit>& solver,
                                         WLits<TLit, TWeight> targets);
  void FixTargetsPolaritiesOptimistic(Lits<TLit> targets);
  void FixTargetsPolaritiesOptimistic(WLits<TLit, TWeight> targets);
  void FixNoneTargetsPolaritiesConservative(Lits<TLit> targets);
  void FixNoneTargetsPolaritiesConservative(WLits<TLit, TWeight> targets);

  void SaveAndPrintLatestMaxSATValue(WLits<TLit, TWeight> wlits);
  void ResetMaxSAT();
  void MaxSATSolutionFoundFrom(const SatSolver<TLit>& solver,
                               WLits<TLit, TWeight> wlits);
  void MaxSATSolutionFound(WLits<TLit, TWeight> wlits);
  void MaxSATSolutionFoundFrom(const SatSolver<TLit>& solver, Lits<TLit> lits,
                               TWeight value);
  void MaxSATSolutionFound(Lits<TLit> lits, TWeight value);
  void MaxSATSolutionFoundFrom(const SatSolver<TLit>& solver,
                               WLits<TLit, TWeight> wlits, TWeight value);
  void MaxSATSolutionFound(WLits<TLit, TWeight> wlits, TWeight value);

  void BumpTargetScoresFor(SatSolver<TLit>& solver, Lits<TLit> targets);
  void BumpTargetScores(Lits<TLit> targets);
  void BumpTargetScoresFor(SatSolver<TLit>& solver,
                           WLits<TLit, TWeight> targets);
  void BumpTargetScores(WLits<TLit, TWeight> targets);

  SolverStatus SolveInitialSat(Lits<TLit> assumps, WLits<TLit, TWeight> wlits);
  SolverStatus SolveForMaxSAT(Lits<TLit> assumps, WLits<TLit, TWeight> wlits);

  // Concrete MaxSAT Algorithms

  void LocalSearchMaxSAT(Lits<TLit> assumps, WLits<TLit, TWeight> wlits,
                         std::function<bool()> ShouldExitAfterSolutionFound);
  void NuWLS(Lits<TLit> assumps, WLits<TLit, TWeight> wlits,
             std::function<bool()> ShouldExitAfterSolutionFound);
  void DeepDist(Lits<TLit> assumps, WLits<TLit, TWeight> wlits,
                std::function<bool()> ShouldExitAfterSolutionFound);
  void NuWeighting(Lits<TLit> assumps, WLits<TLit, TWeight> wlits,
                   std::function<bool()> ShouldExitAfterSolutionFound);
  void MaxSATObvBS(Lits<TLit> assumps, WLits<TLit, TWeight> targets,
                   std::function<bool()> ShouldExitAfterSolutionFound,
                   bool ums = false);
  MBExitReason MrsBeaver(Lits<TLit> assumps, WLits<TLit, TWeight> targets,
                         const bool fix_model_value,
                         std::function<bool()> ShouldExitAfterSolutionFound);
  void LSU(Lits<TLit> assumps, WLits<TLit, TWeight> targets,
           EncoderType encoder_type, const bool fix_model_value,
           std::function<bool()> ShouldExitAfterSolutionFound);

  // BlackBox

  SolverStatus SolveInitialSat(
      Lits<TLit> assumps, Lits<TLit> observables,
      std::function<TWeight(std::function<TLitValue(TLit)>, void*)> PbFunc,
      void* user_ds = nullptr);
  SolverStatus Polosat(
      Lits<TLit> assumps, Lits<TLit> observables,
      std::function<TWeight(std::function<TLitValue(TLit)>, void*)> PbFunc,
      std::function<bool(Lits<TLit>, void*)> CallbackOnSolutionFound = nullptr,
      void* user_ds = nullptr, const bool maxsat_call = false);
  void ResetBlackBox();
  void SaveAndPrintLatestBlackBoxValue(TWeight value);
  void BlackBoxSolutionFoundFrom(
      const SatSolver<TLit>& solver, Lits<TLit> observables,
      std::function<TWeight(std::function<TLitValue(TLit)>, void*)> PbFunc,
      void* user_ds);
  void BlackBoxSolutionFound(
      Lits<TLit> observables,
      std::function<TWeight(std::function<TLitValue(TLit)>, void*)> PbFunc,
      void* user_ds);

  // OBV

  SolverStatus SolveInitialSat(Lits<TLit> assumps, Lits<TLit> targets);
  SolverStatus ObvBS(
      Lits<TLit> assumps, Lits<TLit> targets,
      std::function<bool(Lits<TLit>, void*)> CallbackOnSolutionFound = nullptr,
      void* user_ds = nullptr);
};
};  // namespace Aperture