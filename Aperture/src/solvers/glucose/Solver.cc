#include "Solver.h"

using namespace Aperture;
using namespace ApertureGlucose;
using namespace std;

template <ValidLiteral TLit>
GlucoseSatSolver<TLit>::GlucoseSatSolver(
    const std::unordered_map<std::string, std::string>& params)
    : max_var_(0) {
  glucose_.verbosity = 0;
  if (params.find("chrono") != params.end()) {
    glucose_.chrono = std::stoi(params.at("chrono"));
  }
  if (params.find("confl_to_chrono") != params.end()) {
    glucose_.confl_to_chrono = std::stoi(params.at("confl_to_chrono"));
  }
}

template <ValidLiteral TLit>
bool GlucoseSatSolver<TLit>::AddClause(Lits<TLit> clause) {
  vec<Lit> glucose_clause;
  for (TLit l : clause) {
    glucose_clause.push(ToGlucoseLit(l));
  }
  glucose_.addClause(glucose_clause);
  return glucose_.okay();
}

template <ValidLiteral TLit>
SolverStatus GlucoseSatSolver<TLit>::Solve(Lits<TLit> assumps,
                                           uint64_t conflict_threshold) {
  vec<Lit> glucose_assumps;
  for (TLit l : assumps) {
    glucose_assumps.push(ToGlucoseLit(l));
  }

  if ((int64_t)conflict_threshold > 0) {
    glucose_.setConfBudget(conflict_threshold);
  }
  lbool res = glucose_.solveLimited(glucose_assumps);
  glucose_.budgetOff();

  if (res == l_True) {
    return SolverStatus::SAT;
  } else if (res == l_False) {
    return SolverStatus::UNSAT;
  } else {
    return SolverStatus::UNKNOWN;
  }
}

template <ValidLiteral TLit>
vector<TLitValue> GlucoseSatSolver<TLit>::GetModel() const {
  vector<TLitValue> model;
  model.resize(max_var_ + 1);
  model[0] = TLitValue::TRUE;
  for (TLit var = 1; var <= max_var_; ++var) {
    lbool val = glucose_.model[var - 1];
    if (val == l_True) {
      model[var] = TLitValue::TRUE;
    } else if (val == l_False) {
      model[var] = TLitValue::FALSE;
    } else {
      model[var] = TLitValue::DONT_CARE;
    }
  }
  return model;
}

template <ValidLiteral TLit>
void GlucoseSatSolver<TLit>::CopyModelTo(vector<TLitValue>& model) const {
  model.clear();
  model.resize(max_var_ + 1);
  model[0] = TLitValue::TRUE;
  for (TLit var = 1; var <= max_var_; ++var) {
    lbool val = glucose_.model[var - 1];
    if (val == l_True) {
      model[var] = TLitValue::TRUE;
    } else if (val == l_False) {
      model[var] = TLitValue::FALSE;
    } else {
      model[var] = TLitValue::DONT_CARE;
    }
  }
}

template <ValidLiteral TLit>
TLit GlucoseSatSolver<TLit>::NewVar() {
  glucose_.newVar();
  return ++max_var_;
}

template <ValidLiteral TLit>
void GlucoseSatSolver<TLit>::FixPolarity(TLit lit, bool target) {
  glucose_.setFixedPolarity(ToGlucoseVar(lit), lit > 0);
}

template <ValidLiteral TLit>
void GlucoseSatSolver<TLit>::ClearPolarity(TLit lit) {
  glucose_.clearFixedPolarity(ToGlucoseVar(lit));
}

template <ValidLiteral TLit>
uint64_t GlucoseSatSolver<TLit>::GetNumImplications() const {
  return glucose_.propagations;
}

template <ValidLiteral TLit>
Var GlucoseSatSolver<TLit>::ToGlucoseVar(TLit lit) const {
  return lit_abs<TLit>(lit) - 1;
}

template <ValidLiteral TLit>
Lit GlucoseSatSolver<TLit>::ToGlucoseLit(TLit lit) const {
  Var var = ToGlucoseVar(lit);
  return mkLit(var, lit < 0);
}

template <ValidLiteral TLit>
TLitValue GlucoseSatSolver<TLit>::LitValue(TLit lit) const {
  Var var = ToGlucoseVar(lit);
  lbool val = glucose_.model[var];
  if (lit < 0) {
    if (val == l_True) {
      return TLitValue::FALSE;
    } else if (val == l_False) {
      return TLitValue::TRUE;
    }
  } else {
    if (val == l_True) {
      return TLitValue::TRUE;
    } else if (val == l_False) {
      return TLitValue::FALSE;
    }
  }
  return TLitValue::DONT_CARE;
}

template <ValidLiteral TLit>
void GlucoseSatSolver<TLit>::Interrupt() {
  glucose_.interrupt();
}

template <ValidLiteral TLit>
void GlucoseSatSolver<TLit>::BumpScore(TLit lit, double val) {
  Var var = ToGlucoseVar(lit);
  glucose_.varBumpActivity(var, val);
}

template class Aperture::GlucoseSatSolver<int32_t>;