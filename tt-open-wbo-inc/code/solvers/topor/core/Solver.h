#pragma once

#include "../mtl/Vec.h"
#include "../topor/Topor.hpp"
#include "SolverTypes.h"
#include <limits>
#include <string>

using namespace ToporWrapper;

namespace ToporWrapper
{	
	using TLit = int32_t;
	using TUInd = CLSIND;//uint32_t;
	constexpr bool Compress = COMPRESS;//false;
	
	class Solver
	{
		public:		
		
			Solver();
			inline Var newVar() { return varsNum++; }
			bool addClause (const vec<Lit>& ps);
			bool addClause (Lit p);
			bool addClause (Lit p, Lit q);
			bool addClause (Lit p, Lit q, Lit r);
    
			inline void setConfBudget(int confBudget) { confBudgets[0] = confBudget; }
			inline void setConfBudget2(int confBudget) { confBudgets[1] = confBudget; }
			
			inline void budgetOffConflict() { confBudgets[0] = -1; }
			inline void budgetOffConflict2() { confBudgets[1] = -1; }
			inline void budgetOff() { budgetOffConflict(); budgetOffConflict2(); }
			inline void varBumpActivity(Var v, double inc = 1.0) { topor.BoostScore(T(v), inc); }
			
			lbool solveLimited (const vec<Lit>& assumps);
			bool solve(const vec<Lit>& assumps);			
						
			// The current number of variables
			inline int nVars() const { return varsNum; }    
			// FALSE means solver is in a conflicting state   
			inline bool okay() const { return !topor.IsError(); } 
			inline lbool value(Var x) const   { return G(topor.GetLitValue(T(x))); }
			inline lbool value(Lit p) const   { return G(topor.GetLitValue(T(p))); }
			
			// Glucose parameters, accessed by the solver. We declare them, but ignored in the code
			double random_var_freq = 0;
			unsigned lbLBDFrozenClause = 30;
			int	confl_to_chrono = 4000;
			int	chrono = -1;
			
			// ************************************
			// Communicate to Topor before each Solve
			// ************************************
			vec<lbool> _user_phase_saving;
			std::array<int, 2> confBudgets = {-1, -1};
			
			// ************************************
			// Retrieve from Topor after each Solve
			// ************************************
			uint64_t propagations = 0;			
			vec<lbool> model;
			std::string latestStat = "";
			inline std::string GetLatestStatStr() { return latestStat; }
			
			// ************************************
			// Not needed for anytime MaxSAT solving
			// ************************************			
			vec<Lit> conflict;											
		protected:
			Topor::CTopor<TLit,TUInd,Compress> topor;
			int varsNum = 0;			
			int maxVarFixedPolarity = -1;	
			bool polarityOptimisticSet = false;
			
			inline TLit T(Lit l) const 
			{ 
				const int lInt = toInt(l);
				const TLit vTopor = T(lInt >> 1);
				const bool isNeg = lInt & 1;
				return isNeg ? -vTopor : vTopor;
			}
			
			inline TLit T(int v) const 
			{ 
				return v + 1;
			}
						
			std::vector<TLit> T(const vec<Lit>& ps);
			inline lbool G(Topor::TToporLitVal tVal) const { return tVal == Topor::TToporLitVal::VAL_SATISFIED ? l_True : tVal == Topor::TToporLitVal::VAL_UNASSIGNED ? l_Undef : l_False; }
	};
}
