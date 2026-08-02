#pragma once

#include <span>
#include <vector>

#include "../ATypes.h"

namespace Aperture {
template <ValidLiteral TLit = int32_t>
class SatSolver {
 public:
  // Adds a clause to the solver.
  virtual bool AddClause(Lits<TLit> lits) = 0;
  // Returns the model found by the last successful solving process.
  virtual std::vector<TLitValue> GetModel() const = 0;
  // Copies the model found by the last successful solving process into the
  virtual void CopyModelTo(std::vector<TLitValue>& model) const = 0;
  // Solves the current formula under the given assumptions. Assumptions are
  // literals that will be considered true during the solving process. Returns
  // the status of the solver after the call.
  virtual SolverStatus Solve(
      Lits<TLit> assumps,
      uint64_t conflict_threshold = std::numeric_limits<uint64_t>::max()) = 0;
  // Creates a new variable in the solver and returns its literal.
  virtual TLit NewVar() = 0;
  // Returns the maximum user variable index currently in use (the highest
  // variable index that was created via NewVar).
  virtual TLit MaxUserVar() const = 0;
  // Fixes the polarity of the given literal to TRUE during decision making of
  // the next solving process. That is, the solver will always try to assign the
  // variable of the given literal to TRUE if the literal is positive, and to
  // FALSE if the literal is negative. This setting is reset after each call to
  // Solve or SolveLimited. If target is true, it means that the literal is a
  // target literal. This information might be used by some solvers
  // (e.g. freeze it if elimination is used)
  virtual void FixPolarity(TLit lit, bool target = false) = 0;
  // Clears any polarity fixing for the given variable - ignores literal sign
  // (see FixPolarity).
  virtual void ClearPolarity(TLit lit) = 0;
  // Clears all polarity fixings in the solver.
  virtual void ClearAllPolarities() {
    for (TLit v = 1; v <= MaxUserVar(); ++v) {
      ClearPolarity(v);
    }
  }
  // Returns the number of implications made during the last solving process.
  virtual uint64_t GetNumImplications() const = 0;
  // Returns the literal value of a given literal in the given model
  // For example if lit = 5, it returns the value of literal 5
  // if lit = -5, it returns the value of literal -5.
  virtual TLitValue LitValue(TLit lit) const = 0;
  // Interrupts the current solving process.
  virtual void Interrupt() = 0;
  // Bumps the activity score score of the given literal by the given value.
  virtual void BumpScore(TLit lit, double val) = 0;
  virtual ~SatSolver() = default;
};
};  // namespace Aperture