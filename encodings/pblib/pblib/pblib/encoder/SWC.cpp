#include "SWC.h"

using namespace PBLib;
using namespace std;


void SWC_Encoder::encode(const SimplePBConstraint& pbconstraint, ClauseDatabase& formula, AuxVarManager& auxvars)
{
  if (config->print_used_encodings)
    cout << "c encode with SWC" << endl;

  encode_intern(pbconstraint, formula, auxvars);
}

void SWC_Encoder::encode(const shared_ptr< IncSimplePBConstraint >& pbconstraint, ClauseDatabase& formula, AuxVarManager& auxvars)
{
  if (config->print_used_encodings)
    cout << "c encode incremental with SWC" << endl;

  isInc = true;
  encode_intern(*pbconstraint, formula, auxvars, true);
  isInc = false;

  pbconstraint->setIncrementalData(make_shared<SWCIncData>(outlits));

  outlits.clear();
}


void SWC_Encoder::encode_intern(const SimplePBConstraint& pbconstraint, ClauseDatabase& formula, AuxVarManager& auxvars, bool encodeComplete)
{
  outlits.clear();
  if (pbconstraint.getComparator() == BOTH || isInc)
    encodeComplete = true;

  int n = pbconstraint.getN();
  int64_t k = pbconstraint.getLeq();

  vector<WeightedLit> const & lits = pbconstraint.getWeightedLiterals();

  // A prefix cannot reach a threshold larger than the sum of its weights.
  // Store only reachable thresholds; an absent entry represents false.
  vector<vector<int> > s(n+1);
  int64_t prefix = 0;
  for (int i = 1; i <= n; ++i)
  {
    prefix = min(k, prefix + lits[i-1].weight);
    s[i].resize(prefix + 1, 0);
    for (int64_t j = 1; j <= prefix; ++j)
      s[i][j] = auxvars.getVariable();
  }
  const auto cell = [&s](int i, int64_t j) -> int {
    return j > 0 && j < static_cast<int64_t>(s[i].size()) ? s[i][j] : 0;
  };



  for (int i = 2; i <= n; ++i) for (int j = 1; j < s[i-1].size(); ++j)
    formula.addClause(-s[i-1][j],s[i][j]);

  for (int i = 1; i <= n; ++i) for (int j = 1; j <= lits[i-1].weight; ++j)
    formula.addClause(-lits[i-1].lit, s[i][j]);

  for (int i = 2; i <= n; ++i) for (int j = 1; j < s[i-1].size() && j <= (k-lits[i-1].weight); ++j)
    formula.addClause(-s[i-1][j],-lits[i-1].lit, s[i][j+lits[i-1].weight]);


  if (encodeComplete)
  {
    for (int i = 2; i <= (int)n; ++i) for (int j = 1; j < s[i].size(); ++j)
    {
        int previous = cell(i-1, j);
        if (previous) formula.addClause(-s[i][j], lits[i-1].lit, previous);
        else formula.addClause(-s[i][j], lits[i-1].lit);
    }

    for (int i = 2; i <= (int)n; ++i)  for (int j = lits[i-1].weight + 1; j < s[i].size(); ++j)
    {
        int previous = cell(i-1, j);
        int reduced = cell(i-1, j-lits[i-1].weight);
        if (previous && reduced) formula.addClause(-s[i][j], previous, reduced);
        else if (previous || reduced) formula.addClause(-s[i][j], previous ? previous : reduced);
        else formula.addClause(-s[i][j]);
    }

    for (int j = 1; j <= lits[0].weight; ++j)
	formula.addClause(-s[1][j], lits[0].lit);
  }

  if (isInc)
  {
    outlits.clear();
    for (int i = 1; i <= k; ++i)
    {
      outlits.push_back(s[n][i]);
    }
  }

  formula.addConditionals(pbconstraint.getConditionals());

  for (int i = 2; i <= n; ++i)
  {
    int threshold = cell(i-1, k+1-lits[i-1].weight);
    if (threshold) formula.addClause(-threshold, -lits[i-1].lit);
  }

  if (pbconstraint.getComparator() == BOTH)
  {
    assert(pbconstraint.getGeq() <= k);
    for (int j = 1; j <= pbconstraint.getGeq(); ++j)
      formula.addClause(s[n][j]);
  }

  for (int i = 0; i < pbconstraint.getConditionals().size(); ++i)
    formula.getConditionals().pop_back();
}





void SWC_Encoder::SWCIncData::encodeNewGeq(int64_t newGeq, ClauseDatabase& formula, AuxVarManager&, vector< int32_t > conditionals)
{
  formula.addConditionals(conditionals);

  if (newGeq > 0)
    formula.addClause(outlits[newGeq - 1]); // setting newGeq to true forcing the sum to be at least equal newGeq

  for (int i = 0; i < conditionals.size(); ++i)
    formula.getConditionals().pop_back();
}

void SWC_Encoder::SWCIncData::encodeNewLeq(int64_t newLeq, ClauseDatabase& formula, AuxVarManager&, vector< int32_t > conditionals)
{
  formula.addConditionals(conditionals);

  assert(newLeq < outlits.size());

  formula.addClause(-outlits[newLeq]); // setting newLeq + 1 to false forcing the sum to be less equal newLeq

  for (int i = 0; i < conditionals.size(); ++i)
    formula.getConditionals().pop_back();
}


SWC_Encoder::SWCIncData::SWCIncData(vector< int32_t >& outlits) : outlits(outlits)
{

}


int64_t SWC_Encoder::encodingValue(const SimplePBConstraint& pbconstraint)
{
  int n = pbconstraint.getN();
  int64_t k = pbconstraint.getLeq();

  return valueFunction(n*k*(pbconstraint.getComparator() == BOTH ? 4 : 2), n*k);
}

int64_t SWC_Encoder::encodingValue(const shared_ptr< IncSimplePBConstraint >& pbconstraint)
{
  int n = pbconstraint->getN();
  int64_t k = pbconstraint->getLeq();

  return valueFunction(n*k*4, n*k);
}


SWC_Encoder::SWC_Encoder(PBConfig config): Encoder(config)
{

}
