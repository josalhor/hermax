#include "Solver.h"

#include <stdexcept>

using namespace Aperture;
using namespace ApertureCaDiCaL;
using namespace std;

template <ValidLiteral TLit>
bool CadicalSatSolver<TLit>::AddClause(Lits<TLit> lits) {
  for (TLit lit : lits) {
    cadical_.add(lit);
  }
  cadical_.add(0);
  return !cadical_.inconsistent();
}

template <ValidLiteral TLit>
SolverStatus CadicalSatSolver<TLit>::Solve(Lits<TLit> assumps,
                                           uint64_t conflict_threshold) {
  for (TLit lit : assumps) {
    cadical_.assume(lit);
  }
  cadical_.limit("conflicts", conflict_threshold);
  int res = cadical_.solve();
  cadical_.limit("conflicts", -1);
  switch (res) {
    case 10:
      latest_model_.resize(max_var_ + 1);
      latest_model_[0] = TLitValue::TRUE;
      for (TLit var = 1; var <= max_var_; ++var) {
        int val = cadical_.val(var);
        if (val > 0) {
          latest_model_[var] = TLitValue::TRUE;
        } else if (val < 0) {
          latest_model_[var] = TLitValue::FALSE;
        } else {
          latest_model_[var] = TLitValue::DONT_CARE;
        }
      }
      return SolverStatus::SAT;
    case 20:
      return SolverStatus::UNSAT;
    default:
      return SolverStatus::UNKNOWN;
  }
}

template <ValidLiteral TLit>
vector<TLitValue> CadicalSatSolver<TLit>::GetModel() const {
  return latest_model_;
}

template <ValidLiteral TLit>
void CadicalSatSolver<TLit>::CopyModelTo(vector<TLitValue>& model) const {
  model.resize(max_var_ + 1);
  std::copy(latest_model_.begin(), latest_model_.end(), model.begin());
}

template <ValidLiteral TLit>
TLit CadicalSatSolver<TLit>::NewVar() {
  return ++max_var_;
}

template <ValidLiteral TLit>
void CadicalSatSolver<TLit>::FixPolarity(TLit lit, bool target) {
  if (target && !cadical_.frozen(lit_abs<TLit>(lit))) {
    cadical_.freeze(lit_abs<TLit>(lit));
  }
  cadical_.phase(lit);
}

template <ValidLiteral TLit>
void CadicalSatSolver<TLit>::ClearPolarity(TLit lit) {
  cadical_.unphase(lit);
  if (cadical_.frozen(lit_abs<TLit>(lit))) {
    cadical_.melt(lit_abs<TLit>(lit));
  }
}

template <ValidLiteral TLit>
uint64_t CadicalSatSolver<TLit>::GetNumImplications() const {
  return cadical_.get_statistic_value("propagations");
}

template <ValidLiteral TLit>
TLitValue CadicalSatSolver<TLit>::LitValue(TLit lit) const {
  return (lit > 0) ? latest_model_[lit] : !latest_model_[-lit];
}

template <ValidLiteral TLit>
void CadicalSatSolver<TLit>::Interrupt() {
  cadical_.terminate();
}

template <ValidLiteral TLit>
void CadicalSatSolver<TLit>::BumpScore(TLit lit, double val) {}

template class Aperture::CadicalSatSolver<int32_t>;