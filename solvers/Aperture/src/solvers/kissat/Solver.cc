#include "Solver.h"

extern "C" {
#include "external/solvers/AE_kissat2025_MAB/src/kissat.h"
}

using namespace Aperture;
using namespace std;

template <ValidLiteral TLit>
KissatSatSolver<TLit>::KissatSatSolver(
    const unordered_map<string, string>& params)
    : kissat_(kissat_init()), max_var_(0) {
  kissat_set_option(kissat_, "quiet", 1);
}

template <ValidLiteral TLit>
KissatSatSolver<TLit>::~KissatSatSolver() {
  if (kissat_) {
    kissat_release(kissat_);
    kissat_ = nullptr;
  }
}

template <ValidLiteral TLit>
bool KissatSatSolver<TLit>::AddClause(Lits<TLit> clause) {
  for (TLit lit : clause) {
    kissat_add(kissat_, lit);
  }
  kissat_add(kissat_, 0);
  return true;
}

template <ValidLiteral TLit>
vector<TLitValue> KissatSatSolver<TLit>::GetModel() const {
  vector<TLitValue> model;
  model.resize(max_var_ + 1);
  model[0] = TLitValue::TRUE;
  for (TLit v = 1; v <= max_var_; ++v) {
    int val = kissat_value(kissat_, v);
    if (val > 0) {
      model[v] = TLitValue::TRUE;
    } else {
      model[v] = TLitValue::FALSE;
    }
  }
  return model;
}

template <ValidLiteral TLit>
void KissatSatSolver<TLit>::CopyModelTo(vector<TLitValue>& model) const {
  model.resize(max_var_ + 1);
  model[0] = TLitValue::TRUE;
  for (TLit v = 1; v <= max_var_; ++v) {
    int val = kissat_value(kissat_, v);
    if (val > 0) {
      model[v] = TLitValue::TRUE;
    } else {
      model[v] = TLitValue::FALSE;
    }
  }
}

template <ValidLiteral TLit>
SolverStatus KissatSatSolver<TLit>::Solve(Lits<TLit> assumps,
                                          uint64_t conflict_threshold) {
  for (TLit lit : assumps) {
    kissat_add(kissat_, lit);
    kissat_add(kissat_, 0);
  }
  kissat_set_conflict_limit(kissat_, conflict_threshold);
  int res = kissat_solve(kissat_);
  kissat_set_conflict_limit(kissat_, -1);
  if (res == 10) {
    return SolverStatus::SAT;
  } else if (res == 20) {
    return SolverStatus::UNSAT;
  } else {
    return SolverStatus::UNKNOWN;
  }
}

template <ValidLiteral TLit>
TLit KissatSatSolver<TLit>::NewVar() {
  return ++max_var_;
}

template <ValidLiteral TLit>
TLit KissatSatSolver<TLit>::MaxUserVar() const {
  return max_var_;
}

template <ValidLiteral TLit>
void KissatSatSolver<TLit>::FixPolarity(TLit lit, bool target) {
  if (target) {
    kissat_freeze_variable(kissat_, lit);
  }
  kissat_set_polarity(kissat_, lit);
}

template <ValidLiteral TLit>
void KissatSatSolver<TLit>::ClearPolarity(TLit lit) {
  kissat_melt_variable(kissat_, lit);
  kissat_clear_polarity(kissat_, lit);
}

template <ValidLiteral TLit>
TLitValue KissatSatSolver<TLit>::LitValue(TLit lit) const {
  int val = kissat_value(kissat_, lit_abs<TLit>(lit));
  if (lit < 0) {
    if (val > 0) {
      return TLitValue::FALSE;
    } else if (val < 0) {
      return TLitValue::TRUE;
    }
  } else {
    if (val > 0) {
      return TLitValue::TRUE;
    } else if (val < 0) {
      return TLitValue::FALSE;
    }
  }
  return TLitValue::DONT_CARE;
}

template <ValidLiteral TLit>
void KissatSatSolver<TLit>::Interrupt() {
  kissat_terminate(kissat_);
};

template <ValidLiteral TLit>
void KissatSatSolver<TLit>::BumpScore(TLit lit, double val) {}

template class Aperture::KissatSatSolver<int32_t>;