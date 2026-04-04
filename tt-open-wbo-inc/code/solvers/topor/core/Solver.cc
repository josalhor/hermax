#include "Solver.h"
#include "../utils/Options.h"
#include "../../../Torc.h"
#include <algorithm>
#include <iostream>

using namespace ToporWrapper;
using namespace std;
using namespace Topor;

Solver::Solver()
{
	for (auto [p,n] : Torc::Instance()->toporParams)
	{
		topor.SetParam(p,n);
		//cout << "TOPOR PARAM " << p << " <-- " << n << "\n"; 
	}	
}

std::vector<TLit> Solver::T(const vec<Lit>& ps)
{
	vector<TLit> toporLits(ps.size());
	for (int i = 0; i < ps.size(); ++i)
	{
		toporLits[i] = T(ps[i]);
	}
	return toporLits;
}			
		
bool Solver::addClause(const vec<Lit>& ps) 
{ 
	auto tCls = T(ps);
	
	topor.AddClause(tCls);
	
	return !topor.IsError(); 
}

bool Solver::addClause(Lit p) 
{ 
	array<TLit, 1> toporCls = {T(p)};
	topor.AddClause(toporCls);	
	return !topor.IsError(); 
}

bool Solver::addClause(Lit p, Lit q)
{
	array<TLit, 2> toporCls = {T(p), T(q)};
	topor.AddClause(toporCls);	
	return !topor.IsError(); 
}

bool Solver::addClause(Lit p, Lit q, Lit r)
{
	array<TLit, 3> toporCls = {T(p), T(q), T(r)};
	topor.AddClause(toporCls);	
	return !topor.IsError(); 
}


lbool Solver::solveLimited(const vec<Lit>& assumps) 
{ 
	if (topor.IsError())
	{
		cout << "Topor ERROR before solving: " << topor.GetStatusExplanation() << endl << flush;
		exit(50);
	}
	
	auto tAssumps = T(assumps);
	
	const uint64_t confBudget = confBudgets[0] >= 0 && confBudgets[1] >= 0 ? (uint64_t)std::min(confBudgets[0], confBudgets[1]) : 
		confBudgets[0] < 0 && confBudgets[1] < 0 ? numeric_limits<uint64_t>::max() : confBudgets[0] < 0 ? (uint64_t)confBudgets[1] : (uint64_t)confBudgets[0];
	
	if (Torc::Instance()->GetPolOptimistic() && !polarityOptimisticSet)
	{
		for (int v = 0; v < nVars(); ++v)
		{
			if (v >= Torc::Instance()->TargetIsVarTarget().size())
			{
				break;
			}
			
			if (Torc::Instance()->TargetIsVarTarget()[v])
			{
				topor.FixPolarity(-T(v));
				maxVarFixedPolarity = std::max(maxVarFixedPolarity, v);
			}
		} 
		polarityOptimisticSet = true;
	}
	 
	if (Torc::Instance()->GetPolConservative())
	{
		for (int v = 0; v < _user_phase_saving.size(); ++v)
		{
			if (!Torc::Instance()->GetPolOptimistic() || v >= Torc::Instance()->TargetIsVarTarget().size() || !Torc::Instance()->TargetIsVarTarget()[v])
			{
				assert(_user_phase_saving[v] == l_True || _user_phase_saving[v] == l_False);
				topor.FixPolarity(_user_phase_saving[v] == l_True ? T(v) : -T(v));
				maxVarFixedPolarity = std::max(maxVarFixedPolarity, v);
			}		
		}
		
		for (int v = _user_phase_saving.size(); v <= maxVarFixedPolarity; ++v)
		{
			if (!Torc::Instance()->GetPolOptimistic() || v >= Torc::Instance()->TargetIsVarTarget().size() || !Torc::Instance()->TargetIsVarTarget()[v])
			{
				topor.ClearUserPolarityInfo(T(v));
			}
		}	
	}
	
	TToporReturnVal trv = topor.Solve(tAssumps, make_pair((numeric_limits<double>::max)(), true), confBudget);
	
	if (topor.IsError())
	{
		cout << "Topor ERROR after solving: " << topor.GetStatusExplanation() << endl << flush;
		exit(50);
	}

	latestStat = topor.GetStatStrShort(true);
	propagations = topor.GetPropagations();
	if (trv == Topor::TToporReturnVal::RET_SAT)
	{
		model.growTo(nVars());
		for (int v = 0; v < nVars(); ++v)
		{
			const TToporLitVal tVal = topor.GetLitValue(T(v));
			model[v] = G(tVal);
		}
		
		return l_True;		
	}
	
	if (trv == Topor::TToporReturnVal::RET_UNSAT)
	{
		return l_False;
	}	
	
	return l_Undef;
}
			
bool Solver::solve(const vec<Lit>& assumps) 
{ 
	budgetOff();
	return solveLimited(assumps) == l_True;
}
