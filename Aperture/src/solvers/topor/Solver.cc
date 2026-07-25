#include "Solver.h"

using namespace Aperture;
using namespace ApertureTopor;
using namespace std;

template <ValidLiteral TLit>
ToporSatSolver<TLit>::ToporSatSolver(
    const unordered_map<string, string>& params)
    : max_var_(0) {
  if (params.find("mode") != params.end()) {
    topor_.SetParam("/mode/value", stoi(params.at("mode")));
  }
}

template <ValidLiteral TLit>
bool ToporSatSolver<TLit>::AddClause(Lits<TLit> clause) {
  vector<TLit> clause_vec(clause.begin(), clause.end());
  topor_.AddClause(clause_vec);
  return !topor_.IsError();
}

template <ValidLiteral TLit>
SolverStatus ToporSatSolver<TLit>::Solve(Lits<TLit> assumps,
                                         uint64_t conflict_threshold) {
  vector<TLit> assumps_vec(assumps.begin(), assumps.end());
  TToporReturnVal res = topor_.Solve(
      assumps_vec, make_pair((numeric_limits<double>::max)(), true),
      conflict_threshold);
  switch (res) {
    case TToporReturnVal::RET_SAT:
      latest_model_.resize(max_var_ + 1);
      latest_model_[0] = TLitValue::TRUE;
      for (TLit var = 1; var <= max_var_; ++var) {
        latest_model_[var] =
            (topor_.GetLitValue(var) == TToporLitVal::VAL_SATISFIED)
                ? TLitValue::TRUE
                : TLitValue::FALSE;
      }
      return SolverStatus::SAT;
    case TToporReturnVal::RET_UNSAT:
      return SolverStatus::UNSAT;
    case TToporReturnVal::RET_EXOTIC_ERROR:
    case TToporReturnVal::RET_PARAM_ERROR:
    case TToporReturnVal::RET_INDEX_TOO_NARROW:
    case TToporReturnVal::RET_ASSUMPTION_REQUIRED_ERROR:
      return SolverStatus::ERROR;
    default:
      return SolverStatus::UNKNOWN;
  }
}

template <ValidLiteral TLit>
vector<TLitValue> ToporSatSolver<TLit>::GetModel() const {
  return latest_model_;
}

template <ValidLiteral TLit>
void ToporSatSolver<TLit>::CopyModelTo(vector<TLitValue>& model) const {
  model.resize(max_var_ + 1);
  std::copy(latest_model_.begin(), latest_model_.end(), model.begin());
}

template <ValidLiteral TLit>
TLit ToporSatSolver<TLit>::NewVar() {
  return ++max_var_;
}

template <ValidLiteral TLit>
void ToporSatSolver<TLit>::FixPolarity(TLit lit, bool target) {
  topor_.FixPolarity(lit, false);
}

template <ValidLiteral TLit>
void ToporSatSolver<TLit>::ClearPolarity(TLit lit) {
  topor_.ClearUserPolarityInfo(lit);
}

template <ValidLiteral TLit>
uint64_t ToporSatSolver<TLit>::GetNumImplications() const {
  return topor_.GetPropagations();
}

template <ValidLiteral TLit>
TLitValue ToporSatSolver<TLit>::LitValue(TLit lit) const {
  return (lit > 0) ? latest_model_[lit] : !latest_model_[-lit];
}

template <ValidLiteral TLit>
void ToporSatSolver<TLit>::Interrupt() {
  topor_.InterruptNow();
}

template <ValidLiteral TLit>
void ToporSatSolver<TLit>::BumpScore(TLit lit, double val) {
  topor_.BoostScore(lit_abs<TLit>(lit), val);
}

template class Aperture::ToporSatSolver<int32_t>;