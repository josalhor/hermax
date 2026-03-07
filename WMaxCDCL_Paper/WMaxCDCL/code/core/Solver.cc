/***************************************************************************************[Solver.cc]
 MiniSat -- Copyright (c) 2003-2006, Niklas Een, Niklas Sorensson
 Copyright (c) 2007-2010, Niklas Sorensson
 
Chanseok Oh's MiniSat Patch Series -- Copyright (c) 2015, Chanseok Oh

Maple_LCM, Based on MapleCOMSPS_DRUP --Copyright (c) 2017, Mao Luo, Chu-Min LI, Fan Xiao: implementing a learnt clause minimisation approach
 Reference: M. Luo, C.-M. Li, F. Xiao, F. Manya, and Z. L. , “An effective learnt clause minimization approach for cdcl sat solvers,” in IJCAI-2017, 2017, pp.703-711.
 
Maple_CM, Based on Maple_LCM --Copyright (c) 2018, Chu-Min LI, Mao Luo, Fan Xiao: implementing a clause minimisation approach.


Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
 including without limitation the rights to use, copy, modify, merge, publish, distribute,
 sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:
 
The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.
 
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT
OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
**************************************************************************************************/

// Based on newMaxMaple_CM+distACT1W5lastPointAllLRB+

// Based on MaxCDCL3+coreRedctnBis+lookhead+clsRedtn+

// Based on MaxCDCL4+lastConfl+auxiHeap+adaptRL+

// Based on MaxCDCL5+softLits+binS+keepsuc+clsRdn-+-, exploiting conflicting soft literals
// when two soft literals l1 and l2 are conflicting, i.e., they cannot be satisfied at the same time
// without violating a hard clause, then they can be combined into one soft clause.
// See Li & Quan AAAI2010 for different encodings of MaxClique into patial MaxSAT

// Based on newMaxCDCL8+lkUB+lastConfl-+initConfls, treat specially the soft lits involved
//in disjoint inconsistent sets

// Based on newMaxCDCL11+sUB2times+harden4, create new variables to shorten clauses when hardening

// Based on MaxCDCL12bis+act+gc20, detect initial conflicts (different but noy necessarily
// disjoint) and create initial clauses to represent them

// Based on MaxCDCL15UB+saveDynVars-+shortenCls+coretier2+hard+lim4

// Based on newMaxCDCL16+ub+reset+partitnMin2

// Based on MaxCDCL20+lb3

// Based on MaxCDCL21-localrdtn+hardenbis

// Based on newMaxCDCL22+core5+s+purharden3+allUIP+LRBlastL

// Based on newMaxCDCL23+minLBD+core5+hardenEnable2

// Based on MaxCDCL27+quasiConfl

// Based on MaxCDCL30-dist+cardinality+hardC

// Based on newMaxCDCL31bis++dynvarDec+alt+isetCls

// Based on newMaxCDCL32+isetscls-+cls--+hconfl3+allAct

// Based on newMaxCDCL33+unitIset2+nk10k+flyRdtn

// Based on MaxCDCL35+impGbaselineBis++--isetcls+mto+

// Based on new5MaxCDCL37+uip2+isetclsbis+inv+coef2

// Based on MaxCDCL1.0+quasi-+prepro+bin2++fl+vsids01+binRes+

//Based on WMaxCDCL1.7-maxhs-satlike-reuseDyn-fromScratch-noRename+eq

#define _CRT_SECURE_NO_DEPRECATE

#ifdef _MSC_VER
//#include <io.h>
//#include <process.h>
#else
#include <unistd.h>
#endif

#ifdef _MSC_VER
#include <windows.h>
#include <thread>

#define _MSC_VER_Sleep
#endif


#include <math.h>
#include <signal.h>

#include "mtl/Sort.h"
#include "core/Solver.h"
#include "utils/System.h"

using namespace Minisat;

#ifdef BIN_DRUP
int Solver::buf_len = 0;
unsigned char Solver::drup_buf[2 * 1024 * 1024];
unsigned char* Solver::buf_ptr = drup_buf;
#endif

//=================================================================================================
// Options:


static const char* _cat = "CORE";

static DoubleOption  opt_step_size         (_cat, "step-size",   "Initial step size",                             0.40,     DoubleRange(0, false, 1, false));
static DoubleOption  opt_step_size_dec     (_cat, "step-size-dec","Step size decrement",                          0.000001, DoubleRange(0, false, 1, false));
static DoubleOption  opt_min_step_size     (_cat, "min-step-size","Minimal step size",                            0.06,     DoubleRange(0, false, 1, false));
static DoubleOption  opt_var_decay         (_cat, "var-decay",   "The variable activity decay factor",            0.80,     DoubleRange(0, false, 1, false));
static DoubleOption  opt_clause_decay      (_cat, "cla-decay",   "The clause activity decay factor",              0.999,    DoubleRange(0, false, 1, false));
static DoubleOption  opt_random_var_freq   (_cat, "rnd-freq",    "The frequency with which the decision heuristic tries to choose a random variable", 0, DoubleRange(0, true, 1, true));
static DoubleOption  opt_random_seed       (_cat, "rnd-seed",    "Used by the random variable selection",         91648253, DoubleRange(0, false, HUGE_VAL, false));
static IntOption     opt_ccmin_mode        (_cat, "ccmin-mode",  "Controls conflict clause minimization (0=none, 1=basic, 2=deep)", 2, IntRange(0, 2));
static IntOption     opt_phase_saving      (_cat, "phase-saving", "Controls the level of phase saving (0=none, 1=limited, 2=full)", 2, IntRange(0, 2));
static BoolOption    opt_rnd_init_act      (_cat, "rnd-init",    "Randomize the initial activity", false);
static IntOption     opt_restart_first     (_cat, "rfirst",      "The base restart interval", 100, IntRange(1, INT32_MAX));
static DoubleOption  opt_restart_inc       (_cat, "rinc",        "Restart interval increase factor", 2, DoubleRange(1, false, HUGE_VAL, false));
static DoubleOption  opt_garbage_frac      (_cat, "gc-frac",     "The fraction of wasted memory allowed before a garbage collection is triggered",  0.20, DoubleRange(0, false, HUGE_VAL, false));


//=================================================================================================
// Constructor/Destructor:


Solver::Solver() :

// Parameters (user settable):
//
        drup_file        (NULL)
        , verbosity        (0)
        , step_size        (opt_step_size)
        , step_size_dec    (opt_step_size_dec)
        , min_step_size    (opt_min_step_size)
        , timer            (5000)
        , var_decay        (opt_var_decay)
        , clause_decay     (opt_clause_decay)
        , random_var_freq  (opt_random_var_freq)
        , random_seed      (opt_random_seed)
        , VSIDS            (false)
        , ccmin_mode       (opt_ccmin_mode)
        , phase_saving     (opt_phase_saving)
        , rnd_pol          (false)
        , rnd_init_act     (opt_rnd_init_act)
        , garbage_frac     (opt_garbage_frac)
        , restart_first    (opt_restart_first)
        , restart_inc      (opt_restart_inc)

        // Parameters (the rest):
        //
        , learntsize_factor((double)1/(double)3), learntsize_inc(1.1)

        // Parameters (experimental):
        //
        , learntsize_adjust_start_confl (100)
        , learntsize_adjust_inc         (1.5)

        // Statistics: (formerly in 'SolverStats')
        //
        , solves(0), starts(0), decisions(0), rnd_decisions(0), propagations(0), conflicts(0), conflicts_VSIDS(0)
        , dec_vars(0), clauses_literals(0), learnts_literals(0), max_literals(0), tot_literals(0)

        , ok                 (true)
        , cla_inc            (1)
        , var_inc            (1)
        , watches_bin        (WatcherDeleted(ca))
        , watches            (WatcherDeleted(ca))
        , qhead              (0)
        , simpDB_assigns     (-1)
        , simpDB_props       (0)
        , order_heap_CHB     (VarOrderLt(activity_CHB))
        , order_heap_VSIDS   (VarOrderLt(activity_VSIDS))
		, order_heap_distance(VarOrderLt(activity_distance))
        , progress_estimate  (0)
        , remove_satisfied   (false)

        , core_lbd_cut       (5)
        , global_lbd_sum     (0)
        , lbd_queue          (50)
        , next_T2_reduce     (10000)
        , next_L_reduce      (15000)

        , counter            (0)

        // Resource constraints:
        //
        , conflict_budget    (-1)
        , propagation_budget (-1)
        , asynch_interrupt   (false)

        // simplfiy
        , nbSimplifyAll(0)
        , s_propagations(0)

        // simplifyAll adjust occasion
        , curSimplify(1)
        , nbconfbeforesimplify(1000)
        , incSimplify(1000)


        , var_iLevel_inc     (1)
		, my_var_decay       (0.6)
        , DISTANCE           (true)

        , softConflicts (0)
        , softConflictFlag (false)
        //, softWatches        (softWatcherDeleted(ca))
        , solutionCost (0)
        , totalWeight (0)
        , nbClauseReduce (0)


		, countedWeight(0)
		, countedWeightRecord(0)
		, satisfiedWeightRecord(0)
		, totalCost(0)
		, satCost(0)

		, orderHeapAuxi(VarOrderGt(activityLB))

        , tier2_lbd_cut (7)
        , coreLimit (50000)
        , coreInactiveLimit (100000)
        , tier2Limit (7000)
        , tier2InactiveLimit (30000)


        , quasiSoftConflicts (0)
        , fixedByQuasiConfl (0)

        , hardenHeap(VarOrderWeightDec(weights))

		, CCPBadded(false)
		, GACPBadded(false)

        , nSoftLits(0)

		, nbFlyReduced (0)
        , pureSoftConfl (0)
        , nbFixedByLH  (0)

		, la_conflicts(0)
		, la_softConflicts(0)
        , laConflictCost(0)

        ,UB(INT64_MAX)
        ,nonInferenceCost(0)
        ,updateCost(0)

	, occurIn             (ClauseDeleted(ca))
	, SEED (5)
	, SEED_FLAG (5)
        , rootConflCost (0)

	, feasibleNbEq(0), nbEqUse(0)
	, prevEquivLitsNb (0)
	, myDerivedCost (0)

{
  vec<Lit> dummy(1,lit_Undef);
  bwdsub_tmpunit = ca.alloc(dummy);
}


Solver::~Solver()
{
}

// simplify All
//
CRef Solver::simplePropagate() {
    // if (falseLits.size() + rootNbIsets >= UB) { // no need to propagate if a soft conflict occurs
    //   softConflictFlag=true;
    //   return CRef_Undef;
    // }
    CRef    confl = CRef_Undef;
    int     num_props = 0;
    watches.cleanAll();
    watches_bin.cleanAll();
    while (qhead < trail.size()) {
        Lit            p = trail[qhead++];     // 'p' is enqueued fact to propagate.
        vec<Watcher>&  ws = watches[p];
        Watcher        *i, *j, *end;
        num_props++;
        // First, Propagate binary clauses
        vec<Watcher>&  wbin = watches_bin[p];

        for (int k = 0; k<wbin.size(); k++) {
            Lit imp = wbin[k].blocker;
            if (value(imp) == l_False) {
                binConfl[0] = ~p; binConfl[1]=imp;
                return CRef_Bin;
            }
            if (value(imp) == l_Undef) {
                simpleUncheckEnqueue(imp, wbin[k].cref);
                // if (falseLits.size() + rootNbIsets >= UB) {
                //   softConflictFlag = true;
                //   return confl;
                // }
            }
        }
        for (i = j = (Watcher*)ws, end = i + ws.size(); i != end;) {
            // Try to avoid inspecting the clause:
            Lit blocker = i->blocker;
            if (value(blocker) == l_True) {
                *j++ = *i++; continue;
            }
            // Make sure the false literal is data[1]:
            CRef     cr = i->cref;
            Clause&  c = ca[cr];
            Lit      false_lit = ~p;
            if (c[0] == false_lit)
                c[0] = c[1], c[1] = false_lit;
            assert(c[1] == false_lit);
            // If 0th watch is true, then clause is already satisfied.
            // However, 0th watch is not the blocker, make it blocker using a new watcher w
            // why not simply do i->blocker=first in this case?
            Lit     first = c[0];
            //  Watcher w     = Watcher(cr, first);
            if (first != blocker && value(first) == l_True){
                i->blocker = first;
                *j++ = *i++; continue;
            }
            assert(c.lastPoint() >=2);
            if (c.lastPoint() > c.size())
                c.setLastPoint(2);
            for (int k = c.lastPoint(); k < c.size(); k++) {
                if (value(c[k]) == l_Undef) {
                    // watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
                    // the blocker is first in the watcher. However,
                    // the blocker in the corresponding watcher in ~first is not c[1]
                    Watcher w = Watcher(cr, first); i++;
                    c[1] = c[k]; c[k] = false_lit;
                    watches[~c[1]].push(w);
                    c.setLastPoint(k+1);
                    goto NextClause;
                }
                else if (value(c[k]) == l_True) {
                    i->blocker = c[k];  *j++ = *i++;
                    c.setLastPoint(k);
                    goto NextClause;
                }
            }
            for (int k = 2; k < c.lastPoint(); k++) {
                if (value(c[k]) ==  l_Undef) {
                    // watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
                    // the blocker is first in the watcher. However,
                    // the blocker in the corresponding watcher in ~first is not c[1]
                    Watcher w = Watcher(cr, first); i++;
                    c[1] = c[k]; c[k] = false_lit;
                    watches[~c[1]].push(w);
                    c.setLastPoint(k+1);
                    goto NextClause;
                }
                else if (value(c[k]) == l_True) {
                    i->blocker = c[k];  *j++ = *i++;
                    c.setLastPoint(k);
                    goto NextClause;
                }
            }
            // Did not find watch -- clause is unit under assignment:
            i->blocker = first;
            *j++ = *i++;
            if (value(first) == l_False) {
                confl = cr;
                qhead = trail.size();
                // Copy the remaining watches:
                while (i < end)
                    *j++ = *i++;
            }
            else {
                simpleUncheckEnqueue(first, cr);
                // if (falseLits.size()+ rootNbIsets >= UB) {
                //   qhead = trail.size();
                //   // Copy the remaining watches:
                //   while (i < end)
                // 	*j++ = *i++;
                //   softConflictFlag = true;
                // }
            }
            NextClause:;
        }
        ws.shrink(i - j);
        // if (confl == CRef_Undef)
        // 	if (shortenSoftClauses(p))
        // 	  break;
    }
    s_propagations += num_props;

    if (confl == CRef_Undef && countedWeight + rootConflCost >= UB)
        softConflictFlag = true;

    return confl;
}


CRef Solver::simplePropagateForAMO(vec<Lit> & trueLits) {
	// if (falseLits.size() + rootNbIsets >= UB) { // no need to propagate if a soft conflict occurs
	//   softConflictFlag=true;
	//   return CRef_Undef;
	// }
	CRef    confl = CRef_Undef;
	int     num_props = 0;
	watches.cleanAll();
	watches_bin.cleanAll();
	while (qhead < trail.size()) {
		Lit            p = trail[qhead++];     // 'p' is enqueued fact to propagate.
		vec<Watcher>&  ws = watches[p];
		Watcher        *i, *j, *end;
		num_props++;
		// First, Propagate binary clauses
		vec<Watcher>&  wbin = watches_bin[p];

		for (int k = 0; k<wbin.size(); k++) {
			Lit imp = wbin[k].blocker;
			if (value(imp) == l_False) {
				binConfl[0] = ~p; binConfl[1]=imp;
				return CRef_Bin;
			}
			if (value(imp) == l_Undef) {
				simpleUncheckEnqueue(imp, wbin[k].cref);
				if(auxiLit(imp))
					trueLits.push(imp);
				// if (falseLits.size() + rootNbIsets >= UB) {
				//   softConflictFlag = true;
				//   return confl;
				// }
			}
		}
		for (i = j = (Watcher*)ws, end = i + ws.size(); i != end;) {
			// Try to avoid inspecting the clause:
			Lit blocker = i->blocker;
			if (value(blocker) == l_True) {
				*j++ = *i++; continue;
			}
			// Make sure the false literal is data[1]:
			CRef     cr = i->cref;
			Clause&  c = ca[cr];
			Lit      false_lit = ~p;
			if (c[0] == false_lit)
				c[0] = c[1], c[1] = false_lit;
			assert(c[1] == false_lit);
			// If 0th watch is true, then clause is already satisfied.
			// However, 0th watch is not the blocker, make it blocker using a new watcher w
			// why not simply do i->blocker=first in this case?
			Lit     first = c[0];
			//  Watcher w     = Watcher(cr, first);
			if (first != blocker && value(first) == l_True){
				i->blocker = first;
				*j++ = *i++; continue;
			}
			assert(c.lastPoint() >=2);
			if (c.lastPoint() > c.size())
				c.setLastPoint(2);
			for (int k = c.lastPoint(); k < c.size(); k++) {
				if (value(c[k]) == l_Undef) {
					// watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
					// the blocker is first in the watcher. However,
					// the blocker in the corresponding watcher in ~first is not c[1]
					Watcher w = Watcher(cr, first); i++;
					c[1] = c[k]; c[k] = false_lit;
					watches[~c[1]].push(w);
					c.setLastPoint(k+1);
					goto NextClause;
				}
				else if (value(c[k]) == l_True) {
					i->blocker = c[k];  *j++ = *i++;
					c.setLastPoint(k);
					goto NextClause;
				}
			}
			for (int k = 2; k < c.lastPoint(); k++) {
				if (value(c[k]) ==  l_Undef) {
					// watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
					// the blocker is first in the watcher. However,
					// the blocker in the corresponding watcher in ~first is not c[1]
					Watcher w = Watcher(cr, first); i++;
					c[1] = c[k]; c[k] = false_lit;
					watches[~c[1]].push(w);
					c.setLastPoint(k+1);
					goto NextClause;
				}
				else if (value(c[k]) == l_True) {
					i->blocker = c[k];  *j++ = *i++;
					c.setLastPoint(k);
					goto NextClause;
				}
			}
			// Did not find watch -- clause is unit under assignment:
			i->blocker = first;
			*j++ = *i++;
			if (value(first) == l_False) {
				confl = cr;
				qhead = trail.size();
				// Copy the remaining watches:
				while (i < end)
					*j++ = *i++;
			}
			else {
				simpleUncheckEnqueue(first, cr);
				if(auxiLit(first))
					trueLits.push(first);
				// if (falseLits.size()+ rootNbIsets >= UB) {
				//   qhead = trail.size();
				//   // Copy the remaining watches:
				//   while (i < end)
				// 	*j++ = *i++;
				//   softConflictFlag = true;
				// }
			}
			NextClause:;
		}
		ws.shrink(i - j);
		// if (confl == CRef_Undef)
		// 	if (shortenSoftClauses(p))
		// 	  break;
	}
	s_propagations += num_props;

	if (confl == CRef_Undef && countedWeight + rootConflCost >= UB)
		softConflictFlag = true;

	return confl;
}


//the soft lits in the locked isets falsified by the main UP must not counted two times:
// in falseLits.size() and in isets
//So, they are counted in falseLits.size() but not in isets by using rootNbIsets--. But they are used to
//decrease the lock of the isets by calling decrmentIsetLock(iset)
//TODO to implement
/*void Solver::updateIsetLock(int savedFalseLits) {

  for(int i=savedFalseLits; i<falseLits.size(); i++) {
    Lit p=falseLits[i];
    if (inConflicts[var(p)] != NON) {
      int iset = getLockedVarIsetForLK(var(p));
      if (getIsetLock(iset) > 0) {
	decrmentIsetLock(iset);
	rootNbIsets--;
      }
    }
  }
}
*/


void Solver::simpleUncheckEnqueue(Lit p, CRef from){
 assert(value(p) == l_Undef);
  Var v = var(p);
  assigns[v] = lbool(!sign(p)); // this makes a lbool object whose value is sign(p)
  // vardata[x] = mkVarData(from, decisionLevel());
  vardata[v].reason = from;
  vardata[v].level = decisionLevel() + 1;
  trail.push_(p);

  if (auxiVar(v) && value(softLits[v]) == l_False) {// a soft clause is falsified
    //if (unLockedSoftVarForLK(v)) {
      assert(softLits[v] == ~p);
      falseLits.push(softLits[v]);
      assert(weights[v]>=0);
      countedWeight+=weights[v];
    //}
    /*else {
      int iset = getLockedVarIsetForLK(v);
      decrmentIsetLock(iset);
      unLockedVars.push(v);
    }*/
  }
}

void Solver::setTrailRecord()
{
    trailRecord = trail.size();
    falseLitsRecord=falseLits.size();
    satisfiedWeightRecord=satisfiedWeight;
    countedWeightRecord=countedWeight;
}

void Solver::cancelUntilTrailRecord()
{
    for (int c = trail.size() - 1; c >= trailRecord; c--)
    {
        Var x = var(trail[c]);
        assigns[x] = l_Undef;
        nbActiveVars[toInt(trail[c])] = trailRecord;
    }
    qhead = trailRecord;
    trail.shrink(trail.size() - trailRecord);
    falseLits.shrink(falseLits.size() - falseLitsRecord);
    countedWeight=countedWeightRecord;
	satisfiedWeight=satisfiedWeightRecord;
}

void Solver::cancelUntilTrailRecordUnsee()
{
    for (int c = trail.size() - 1; c >= trailRecord; c--)
    {
        Var x = var(trail[c]);
        assigns[x] = l_Undef;
        seen[x]=0;
    }
    qhead = trailRecord;
    trail.shrink(trail.size() - trailRecord);
    falseLits.shrink(falseLits.size() - falseLitsRecord);
    countedWeight=countedWeightRecord;
    satisfiedWeight=satisfiedWeightRecord;

}

void Solver::cancelUntilTrailRecordFillHeap()
{
    for(int i=trailRecord; i< trail.size(); i++) {
        Var v=var(trail[i]);
        assigns[v] = l_Undef;
        if (auxiVar(v)) {
			activityLB[v] = (1-stepSizeLB)*activityLB[v];
            insertAuxiVarOrder(v);
            orderHeapAuxi.decrease(v);
        }
    }
    qhead = trailRecord;
    trail.shrink(trail.size() - trailRecord);
    falseLits.shrink(falseLits.size() - falseLitsRecord);
    countedWeight=countedWeightRecord;
    satisfiedWeight=satisfiedWeightRecord;
}



/*
void Solver::litsEnqueue(int cutP, Clause& c)
{
    for (int i = cutP; i < c.size(); i++)
    {
        simpleUncheckEnqueue(~c[i]);
    }
}
*/

bool Solver::removed(CRef cr) {
    return ca[cr].mark() == 1;
}

void Solver::simplereduceClause(CRef cr, int pathC) {
    nbFlyReduced++;
    Clause& c=ca[cr];
    assert(value(c[0]) == l_True);
    if (feasible || c.learnt()) {
        detachClause(cr, true);
        int max_i = 2;
        // Find the first literal assigned at the next-highest level:
        for (int i = 3; i < c.size(); i++)
            if (level(var(c[i])) >= level(var(c[max_i])))
                max_i = i;
        // here c must contain at least 3 literals assigned at level(var(c[1])): c[0], c[1] and c[max_i],
        // otherwise pathC==1, where c[0] is satisfied
        assert(level(var(c[1])) == level(var(c[max_i])));
        // put this literal at index 0:
        c[0] = c[max_i];

        for(int i=max_i+1; i<c.size(); i++)
            c[i-1] = c[i];
        c.shrink(1);
        attachClause(cr);
    }
}

void Solver::simpleAnalyze(CRef confl, vec<Lit>& out_learnt, bool True_confl)
{
    int pathC = 0;
    Lit p; // = lit_Undef;
    int index = trail.size() - 1;

    if (confl == CRef_Bin) {
        assert(level(var(binConfl[0])) > 0);
        assert(level(var(binConfl[1])) > 0);
        seen[var(binConfl[0])] = 1; seen[var(binConfl[1])] = 1;  pathC = 2;
    }
    else {
        Clause& c = ca[confl]; // c can be binary clause
        if (True_confl && c.size() == 2 && value(c[0]) == l_False) {
            assert(value(c[1]) == l_True);
            Lit tmp = c[0];
            c[0] = c[1], c[1] = tmp;
        }
        for(int i= (True_confl ? 1: 0); i<c.size(); i++)
            if (level(var(c[i])) > 0) {
                seen[var(c[i])] = 1; 	pathC++;
            }
    }
    while(pathC > 0) {
        // Select next clause to look at:
        while (!seen[var(trail[index--])]);
        p = trail[index + 1];
        confl = reason(var(p));
        seen[var(p)] = 0;
        pathC--;
        if (confl != CRef_Undef) {
            // reason_clause.push(confl);
            Clause& c = ca[confl];
            // Special case for binary clauses
            // The first one has to be SAT
            if (c.size() == 2 && value(c[0]) == l_False) {
                assert(value(c[1]) == l_True);
                Lit tmp = c[0];
                c[0] = c[1], c[1] = tmp;
            }
            int nbSeen=0, nbNotSeen = 0;
            int resolventSize=pathC + out_learnt.size();
            // if True_confl==true, then choose p begin with the 1th index of c;
            for (int j = 1; j < c.size(); j++){
                Lit q = c[j]; Var v=var(q);
                if (level(v) > 0) {
                    if (seen[v])
                        nbSeen++;
                    else {
                        nbNotSeen++;
                        seen[v] = 1;
                        pathC++;
                    }
                }
            }
            assert(resolventSize == pathC + out_learnt.size() - nbNotSeen);
            if (pathC > 1 && p!=lit_Undef && nbSeen >= resolventSize)
                simplereduceClause(confl, pathC);
            //printf("b\n");
        }
        else if (confl == CRef_Undef){
            out_learnt.push(~p); seen[var(p)] = 1;
        }
    }
    for(int i=0; i<out_learnt.size(); i++)
        seen[var(out_learnt[i])] = 0;
}


void Solver::simpleAnalyzeSoftConflict(vec<Lit>& out_learnt) {
    int pathC = 0;
    Lit p;
    CRef confl;
    int index   = trail.size() - 1;

    for(int a=falseLitsRecord; a<falseLits.size(); a++) {
        Var v=var(falseLits[a]);
        if (!seen[v] && level(v) > 0) {
            seen[v] = 1; 	pathC++;
            /*if (inConflicts[v] != NON) {
	  int iset=getLockedVarIsetForLK(v);
	  vec<int>& myInconfls = isets[iset];
	  for(int i=0; i<myInconfls.size(); i++) {
	    vec<Lit>& lits = localCores[myInconfls[i]].lits;
	    for(int j=0; j<lits.size(); j++) {
	      if (value(lits[j]) == l_False && !seen[var(lits[j])] && level(var(lits[j])) > 0) {
		seen[var(lits[j])] = 1; pathC++;
	      }
	    }
	  }
	}*/
        }
    }

    // if (pathC < UB)
    //   printf("pathC %d, falseLits: %d, isets %d, UB %llu\n",
    // 	     pathC, falseLits.size(), rootNbIsets, UB);

    while (pathC > 0) {
        while (!seen[var(trail[index--])]);
        // if the reason cr from the 0-level assigned var, we must break avoid move forth further;
        // but attention that maybe seen[x]=1 and never be clear. However makes no matter;
        if (trailRecord > index + 1) break;
        p     = trail[index+1];
        confl = reason(var(p));
        seen[var(p)] = 0;
        pathC--;
        // if (pathC + out_learnt.size() == 0 && confl != CRef_Undef)
        // 	printf("b\n");
        if (confl == CRef_Undef)
            out_learnt.push(~p);
        else {
            // reason_clause.push(confl);
            Clause& c = ca[confl];
            // Special case for binary clauses: the first one has to be SAT
            if (c.size() == 2 && value(c[0]) == l_False) {
                assert(value(c[1]) == l_True);
                Lit tmp = c[0];
                c[0] = c[1], c[1] = tmp;
            }
            for (int j = 1; j < c.size(); j++){
                Var v = var(c[j]);
                if (!seen[v] && level(v) > 0){
                    seen[v] = 1;
                    pathC++;
                }
            }
        }
    }
}

bool Solver::simplifyLearnt(Clause& c, CRef cr, vec<Lit>& lits) {

    trailRecord = trail.size();// record the start pointer
    //sort(&c[0], c.size(), VarOrderLevelLt(vardata));
    falseLitsRecord = falseLits.size(); //unLockedVarsRecord = unLockedVars.size();
    countedWeightRecord=countedWeight;
	satisfiedWeightRecord=satisfiedWeight;

    bool True_confl = false, sat=false, false_lit=false;
    int i, j;
    CRef confl;
    for (int i = 0; i < c.size(); i++){
        if (value(c[i]) == l_True){
            sat = true;
            break;
        }
        else if (value(c[i]) == l_False){
            false_lit = true;
        }
    }
    if (sat){
        removeClause(cr);
        return false;
    }
    else{
        // detachClause(cr, true);

        if (false_lit){
            int li, lj;
            for (li = lj = 0; li < c.size(); li++){
                if (value(c[li]) != l_False){
                    c[lj++] = c[li];
                }
                else assert(li>1);
            }
            if (lj==2) {
                assert(li>2);
                detachClause(cr, true);
                c.shrink(li - lj);
                attachClause(cr);
            }
            else {
                assert(lj>2);
                c.shrink(li - lj);
            }
        }
        original_length_record += c.size();

        assert(c.size() > 1);

        Lit implied;
        lits.clear();
        for(i=0; i<c.size(); i++) lits.push(c[i]);
        assert(lits.size() == c.size());
        for (i = 0, j = 0; i < lits.size(); i++){
            if (value(lits[i]) == l_Undef){
                simpleUncheckEnqueue(~lits[i]);
                lits[j++] = lits[i];
                confl = simplePropagate();
                if (confl != CRef_Undef || softConflictFlag){
                    break;
                }
            }
            else{
                if (value(lits[i]) == l_True){
                    //printf("///@@@ uncheckedEnqueue:index = %d. l_True\n", i);
                    lits[j++] = lits[i];
                    True_confl = true; implied=lits[i];
                    confl = reason(var(lits[i]));
                    assert(confl  != CRef_Undef);
                    break;
                }
            }
        }
        if (j<lits.size()) {
            lits.shrink(lits.size() - j);
        }
        assert(lits.size() > 0 && lits.size() == j);

        if (confl != CRef_Undef || True_confl == true || softConflictFlag) {
            simp_learnt_clause.clear();
            //  simp_reason_clause.clear();
            if (softConflictFlag) {
                simpleAnalyzeSoftConflict(simp_learnt_clause);
                softConflictFlag = false;
            }
            else {
                if (True_confl == true){
                    simp_learnt_clause.push(implied);
                }
                simpleAnalyze(confl, simp_learnt_clause, True_confl);
            }
            assert(simp_learnt_clause.size() <= lits.size());
            cancelUntilTrailRecord();
            if (simp_learnt_clause.size() < lits.size()){
                for (i = 0; i < simp_learnt_clause.size(); i++){
                    lits[i] = simp_learnt_clause[i];
                }
                lits.shrink(lits.size() - i);
            }
            assert(simp_learnt_clause.size() == lits.size());
        }
        else
            cancelUntilTrailRecord();

        simplified_length_record += lits.size();
        return true;
    }
}
bool Solver::simplifyLearnt_core() {

    //int learnts_core_size_before = learnts_core.size();
    unsigned int nblevels;
    vec<Lit> lits;

    int nbSimplified = 0, nbSimplifing = 0, nbShortened=0, ci, cj;

    for (ci = 0, cj = 0; ci < learnts_core.size(); ci++){
        CRef cr = learnts_core[ci];
        Clause& c = ca[cr];

        if (removed(cr)) continue;
        else if ((c.simplified() && !WithNewUB)
                 || (c.learnt() && (c.touched() + coreInactiveLimit < conflicts || c.activity() == 0))){
            learnts_core[cj++] = learnts_core[ci];
            ////
            nbSimplified++;
        }
        else{
            ////
            nbSimplifing++;
            if (drup_file){
                add_oc.clear();
                for (int i = 0; i < c.size(); i++) add_oc.push(c[i]); }
            if (simplifyLearnt(c, cr, lits)) {

                if(drup_file && add_oc.size()!=lits.size()){
#ifdef BIN_DRUP
                    binDRUP('a', lits , drup_file);
//                    binDRUP('d', add_oc, drup_file);
#else
                    for (int i = 0; i < lits.size(); i++)
                        fprintf(drup_file, "%i ", (var(lits[i]) + 1) * (-2 * sign(lits[i]) + 1));
                    fprintf(drup_file, "0\n");

//                      fprintf(drup_file, "d ");
//                     for (int i = 0; i < add_oc.size(); i++)
//                         fprintf(drup_file, "%i ", (var(add_oc[i]) + 1) * (-2 * sign(add_oc[i]) + 1));
//                     fprintf(drup_file, "0\n");
#endif
                }
                if (lits.size() == 0)
                    return false;
                if (lits.size() == 1){
                    //int savedFalseLits=falseLits.size();
                    // when unit clause occur, enqueue and propagate
                    uncheckedEnqueue(lits[0]);
                    if (propagate() != CRef_Undef  || softConflictFlag==true){
                        // ok = false;
                        return false;
                    }
                    // delete the clause memory in logic
                    detachClause(cr, true);
                    c.mark(1);
                    ca.free(cr);
                    //updateIsetLock(savedFalseLits);
                }
                else {
                    if (c.size() > lits.size()) {
                        nbShortened++;
                        detachClause(cr, true);
                        for(int i=0; i<lits.size(); i++)
                            c[i]=lits[i];
                        c.shrink(c.size()-lits.size());
                        c.calcAbstraction();
                        attachClause(cr);

                        nblevels = computeLBD(c);
                        if (nblevels < c.lbd()){
                            //printf("lbd-before: %d, lbd-after: %d\n", c.lbd(), nblevels);
                            c.set_lbd(nblevels);
                        }
                    }
                    if (c.learnt())
                        learnts_core[cj++] = learnts_core[ci];
                    c.setSimplified(2);
                }
            }
        }
    }
    learnts_core.shrink(ci - cj);

    // printf("c nbLearnts_core %d / %d, nbSimplified: %d, nbSimplifing: %d, of which nbShortened: %d\n",
    //        learnts_core_size_before, learnts_core.size(), nbSimplified, nbSimplifing, nbShortened);

    return true;
}

struct reduceTIER2_lt {
    ClauseAllocator& ca;
    reduceTIER2_lt(ClauseAllocator& ca_) : ca(ca_) {}
    bool operator () (CRef x, CRef y) {

        if (ca[x].touched() < ca[y].touched()) return true;
        if (ca[x].touched() > ca[y].touched()) return false;

        if(ca[x].lbd() > ca[y].lbd()) return true;
        if(ca[x].lbd() < ca[y].lbd()) return false;

        // Finally we can use old activity or size, we choose the last one

        return ca[x].size() > ca[y].size();
    }
};

bool Solver::simplifyLearnt_tier2() {
    //int learnts_tier2_size_before = learnts_tier2.size();
    unsigned int nblevels;
    vec<Lit> lits;

    int nbSimplified = 0, nbSimplifing = 0, nbShortened=0, ci, cj;
    int limit;
    if (learnts_tier2.size() <= tier2Limit/2)
        limit = 0;
    else {
        sort(learnts_tier2, reduceTIER2_lt(ca));
        limit = learnts_tier2.size() - (tier2Limit/2);
    }

    for (ci = 0, cj = 0; ci < learnts_tier2.size(); ci++){
        CRef cr = learnts_tier2[ci];
        Clause& c = ca[cr];

        if (removed(cr)) continue;
        else if ((c.simplified() && !WithNewUB) || c.activity() == 0){
            learnts_tier2[cj++] = learnts_tier2[ci];
            ////
            nbSimplified++;
        }
        else{
            ////
            nbSimplifing++;
            if (drup_file){
                add_oc.clear();
                for (int i = 0; i < c.size(); i++) add_oc.push(c[i]); }
            if (simplifyLearnt(c, cr, lits)) {

                if(drup_file && add_oc.size()!=lits.size()){
#ifdef BIN_DRUP
                    binDRUP('a', lits , drup_file);
//                    binDRUP('d', add_oc, drup_file);
#else
                    for (int i = 0; i < lits.size(); i++)
                        fprintf(drup_file, "%i ", (var(lits[i]) + 1) * (-2 * sign(lits[i]) + 1));
                    fprintf(drup_file, "0\n");

//                      fprintf(drup_file, "d ");
//                     for (int i = 0; i < add_oc.size(); i++)
//                         fprintf(drup_file, "%i ", (var(add_oc[i]) + 1) * (-2 * sign(add_oc[i]) + 1));
//                     fprintf(drup_file, "0\n");
#endif
                }
                if (lits.size() == 0)
                    return false;
                if (lits.size() == 1){
                    //                   int savedFalseLits=falseLits.size();
                    // when unit clause occur, enqueue and propagate
                    uncheckedEnqueue(lits[0]);
                    if (propagate() != CRef_Undef  || softConflictFlag==true){
                        // ok = false;
                        return false;
                    }
                    // delete the clause memory in logic
                    detachClause(cr, true);
                    c.mark(1);
                    ca.free(cr);
                    //updateIsetLock(savedFalseLits);
                }
                else {
                    if (c.size() > lits.size()) {
                        nbShortened++;
                        detachClause(cr, true);
                        for(int i=0; i<lits.size(); i++)
                            c[i]=lits[i];
                        c.shrink(c.size()-lits.size());
                        attachClause(cr);
                        c.calcAbstraction();

                        nblevels = computeLBD(c);
                        if (nblevels < c.lbd()){
                            //printf("lbd-before: %d, lbd-after: %d\n", c.lbd(), nblevels);
                            c.set_lbd(nblevels);
                        }
                    }

                    if (c.learnt())
                        if (c.lbd() <= core_lbd_cut){
                            //	c.set_lbd(c.size());
                            learnts_core.push(cr);
                            c.mark(CORE);
                        }
                        else
                            learnts_tier2[cj++] = learnts_tier2[ci];
                    c.setSimplified(2);
                }
            }
        }
    }
    learnts_tier2.shrink(ci - cj);

    //    printf("c nbLearnts_tier2 %d / %d, nbSimplified: %d, nbSimplifing: %d, of which nbShortened: %d\n",
    //           learnts_tier2_size_before, learnts_tier2.size(), nbSimplified, nbSimplifing, nbShortened);

    return true;
}

void Solver::cancelUntilTrailRecord1() {
  counter++;
  for (int c = trail.size() - 1; c >= trailRecord; c--) {
    Lit l=trail[c];
      assigns[var(l)] = l_Undef;
      nbActiveVars[toInt(l)] = trailRecord;
      seen2[toInt(l)] = counter;
    }
  qhead = trailRecord;
  trail.shrink(trail.size() - trailRecord);
  falseLits.shrink(falseLits.size() - falseLitsRecord);
  countedWeight = countedWeightRecord;
  satisfiedWeight = satisfiedWeightRecord;
}

Lit Solver::getRpr(Lit p) {
  while (rpr[toInt(p)] != lit_Undef)
    p = rpr[toInt(p)];
  assert(rpr[toInt(p)] == lit_Undef);
  return p;
}

void Solver::cancelUntilTrailRecord2(Lit p, int& nbeq, int& nbSoftEq) {
  impliedLits.clear();
  p=getRpr(p);
  for (int c = trail.size() - 1; c >= trailRecord; c--) {
    Lit l=trail[c];
    assigns[var(l)] = l_Undef;
    nbActiveVars[toInt(l)] = trailRecord;
    if (seen2[toInt(l)] == counter)
      impliedLits.push(l);
    else if (seen2[toInt(~l)] == counter && !dynVar(var(l)) && !dynVar(var(p))) {
      // p implies ~l and ~p implies l
      Lit q=getRpr(~l);
      if (p != q) {
	assert(rpr[toInt(p)] == lit_Undef && rpr[toInt(q)] == lit_Undef);
	assert(rpr[toInt(~p)] == lit_Undef && rpr[toInt(~q)] == lit_Undef);
	if (auxiVar(var(p)) && auxiVar(var(q))) {
	  if (weights[var(q)] > weights[var(p)]) {
	    Lit r=p; p=q; q=r;
	  }
	}
	else if (auxiVar(var(q))) {
	   Lit r=p; p=q; q=r;
	}
	rpr[toInt(q)] = p;
	rpr[toInt(~q)] = ~p;
	nbeq++; equivLits.push(q);
	if (auxiVar(var(p)) && auxiVar(var(q)))
	  nbSoftEq++;
	  //printf("sf\n");
      }
    }
  }
  qhead = trailRecord;
  trail.shrink(trail.size() - trailRecord);
  falseLits.shrink(falseLits.size() - falseLitsRecord);
  countedWeight = countedWeightRecord;
  satisfiedWeight = satisfiedWeightRecord;
}

// void Solver::cancelUntilTrailRecord2() {
//   impliedLits.clear();
//   for (int c = trail.size() - 1; c >= trailRecord; c--) {
//     Lit l=trail[c];
//     assigns[var(l)] = l_Undef;
//     nbActiveVars[toInt(l)] = trailRecord;
//     if (seen2[toInt(l)] == counter)
//       impliedLits.push(l);
//   }
//   qhead = trailRecord;
//   trail.shrink(trail.size() - trailRecord);
//   falseLits.shrink(falseLits.size() - falseLitsRecord);
//   countedWeight = countedWeightRecord;
//   satisfiedWeight = satisfiedWeightRecord;
// }

// Lit Solver::get1UIP(CRef confl) {
//     int pathC = 0;
//     Lit p     = lit_Undef;
//     int index   = trail.size() - 1;
    
//     do{
//         assert(confl != CRef_Undef); // (otherwise should be UIP)
//         Clause& c = ca[confl];

//         // For binary clauses, we don't rearrange literals in propagate(), so check and make sure the first is an implied lit.
//         if (p != lit_Undef && c.size() == 2 && value(c[0]) == l_False){
//             assert(value(c[1]) == l_True);
//             Lit tmp = c[0];
//             c[0] = c[1], c[1] = tmp; }

// 	int nbSeen=0, resolventSize=pathC;
//         for (int j = (p == lit_Undef) ? 0 : 1; j < c.size(); j++){
//             Lit q = c[j];

//             // if (!seen[var(q)] && trailIndex(var(q)) >= trailRecord){
// 	    //   seen[var(q)] = 1;
// 	    //   pathC++;
//             // }

// 	    if (trailIndex(var(q)) >= trailRecord) {
// 	      if (seen[var(q)])
// 		nbSeen++;
// 	      else {
// 		seen[var(q)] = 1;
// 		pathC++;
// 	      }
// 	    }
//         }
// 	if (p != lit_Undef && pathC > 1 && nbSeen >= resolventSize) {
// 	  simplereduceClause(confl);
// 	  nbFlyReducedFL++;
// 	}
	
// 	while (!seen[var(trail[index--])]);
// 	p  = trail[index+1];
//         confl = reason(var(p));
//         seen[var(p)] = 0;
//         pathC--;
	
//     }while (pathC > 0);
//     return p;
// }

#define maxNbTestedVars 10000

bool Solver::failedLiteralDetection() {
  int nbFailedLits=0, initTrail = trail.size(), maxNoFail=0, nbTested=0, nbI=0, skipped=0, nbeq=0, myNbSoftEq=0;
    CRef confl;
    bool res = true;
    falseLitsRecord = falseLits.size(); trailRecord = trail.size();
    countedWeightRecord=countedWeight;
	satisfiedWeightRecord=satisfiedWeight;

    // for (int i=0; i<maxNbTestedVars; i++) {
    //for(Var v=0; v<staticNbVars; v++) {
    while (1) {
        if (maxNoFail > maxNbTestedVars/10)
            break;
        Lit p=pickBranchLit();
        if (p==lit_Undef)
            break;
        // if (value(v) != l_Undef)
        //   continue;
        // Lit p=mkLit(v);
	if (nbActiveVars[toInt(p)] == trailRecord && nbActiveVars[toInt(~p)] == trailRecord) {
	  skipped++; maxNoFail++;
	  testedVars.push(var(p));
	}
	else {
	  nbTested++;
	  simpleUncheckEnqueue(p);
	  confl = simplePropagate();
	  if (confl != CRef_Undef || softConflictFlag) {
            maxNoFail = 0;
            cancelUntilTrailRecord(); softConflictFlag=false;
	    //            int savedFalseLits=falseLits.size();
            uncheckedEnqueue(~p);
            assert(decisionLevel() == 0);
            if (propagate() != CRef_Undef  || softConflictFlag) {
	      res = false;
	      break;
            }
            //updateIsetLock(savedFalseLits);
            trailRecord = trail.size();  falseLitsRecord = falseLits.size();
            countedWeightRecord = countedWeight;
	    satisfiedWeightRecord = satisfiedWeight;
	    nbFailedLits++;
	  }
	  else {
            cancelUntilTrailRecord1();
            simpleUncheckEnqueue(~p);
            confl = simplePropagate();
            if (confl != CRef_Undef || softConflictFlag) {
	      maxNoFail = 0;
	      cancelUntilTrailRecord(); softConflictFlag=false;
	      //               int savedFalseLits=falseLits.size();
	      uncheckedEnqueue(p);
	      if (propagate() != CRef_Undef  || softConflictFlag) {
		res = false;
		break;
	      }
	      //updateIsetLock(savedFalseLits);
	      trailRecord = trail.size();  falseLitsRecord = falseLits.size();
	      countedWeightRecord = countedWeight;
	      satisfiedWeightRecord = satisfiedWeight;
	      nbFailedLits++;
            }
            else {
	      cancelUntilTrailRecord2(p, nbeq, myNbSoftEq);
	      if (impliedLits.size() > 0) {
		nbI += impliedLits.size(); maxNoFail = 0;
		for(int i=0; i<impliedLits.size(); i++) 
		  uncheckedEnqueue(impliedLits[i]);
		if (propagate() != CRef_Undef || softConflictFlag) {
		  res = false;
		  break;
		}
		trailRecord = trail.size(); falseLitsRecord = falseLits.size();
		countedWeightRecord = countedWeight;
		satisfiedWeightRecord = satisfiedWeight;
	      }
	      else
		maxNoFail++;
	      if (value(p) == l_Undef)
		testedVars.push(var(p));
            }
	  }
	}
    }
    for(int i=0; i<testedVars.size() ; i++)
      if (value(testedVars[i]) == l_Undef)
	insertVarOrder(testedVars[i]);
    testedVars.clear();
    printf("c nbFailedLits %d, nbI %d, fixedVarsByFL %d, totalFixedVars %d, nbTested %d, skipped %d, nbeq %d, nbSoftEq %d\n",
           nbFailedLits, nbI, trail.size()-initTrail, trail.size(), nbTested, skipped, nbeq, myNbSoftEq);

    //  if (feasible)
    feasibleNbEq += nbeq; nbSoftEq += myNbSoftEq;
    
    return res;
}

// bool Solver::failedLiteralDetection() {
//   int nbFailedLits=0, initTrail = trail.size(), maxNoFail=0, nbTested=0, nbI=0, skipped=0;
//     CRef confl;
//     bool res = true;
//     falseLitsRecord = falseLits.size(); trailRecord = trail.size();
//     countedWeightRecord=countedWeight;
// 	satisfiedWeightRecord=satisfiedWeight;

//     // for (int i=0; i<maxNbTestedVars; i++) {
//     //for(Var v=0; v<staticNbVars; v++) {
//     while (1) {
//         if (maxNoFail > maxNbTestedVars/10)
//             break;
//         Lit p=pickBranchLit();
//         if (p==lit_Undef)
//             break;
//         // if (value(v) != l_Undef)
//         //   continue;
//         // Lit p=mkLit(v);
// 	if (nbActiveVars[toInt(p)] == trailRecord && nbActiveVars[toInt(~p)] == trailRecord) {
// 	  skipped++; maxNoFail++;
// 	  testedVars.push(var(p));
// 	}
// 	else {
// 	  nbTested++;
// 	  simpleUncheckEnqueue(p);
// 	  confl = simplePropagate();
// 	  if (confl != CRef_Undef || softConflictFlag) {
//             maxNoFail = 0;
//             cancelUntilTrailRecord(); softConflictFlag=false;
// 	    //            int savedFalseLits=falseLits.size();
//             uncheckedEnqueue(~p);
//             assert(decisionLevel() == 0);
//             if (propagate() != CRef_Undef  || softConflictFlag) {
// 	      res = false;
// 	      break;
//             }
//             //updateIsetLock(savedFalseLits);
//             trailRecord = trail.size();  falseLitsRecord = falseLits.size();
//             countedWeightRecord = countedWeight;
// 	    satisfiedWeightRecord = satisfiedWeight;
// 	    nbFailedLits++;
// 	  }
// 	  else {
//             cancelUntilTrailRecord1();
//             simpleUncheckEnqueue(~p);
//             confl = simplePropagate();
//             if (confl != CRef_Undef || softConflictFlag) {
// 	      maxNoFail = 0;
// 	      cancelUntilTrailRecord(); softConflictFlag=false;
// 	      //               int savedFalseLits=falseLits.size();
// 	      uncheckedEnqueue(p);
// 	      if (propagate() != CRef_Undef  || softConflictFlag) {
// 		res = false;
// 		break;
// 	      }
// 	      //updateIsetLock(savedFalseLits);
// 	      trailRecord = trail.size();  falseLitsRecord = falseLits.size();
// 	      countedWeightRecord = countedWeight;
// 	      satisfiedWeightRecord = satisfiedWeight;
// 	      nbFailedLits++;
//             }
//             else {
// 	      cancelUntilTrailRecord2();
// 	      if (impliedLits.size() > 0) {
// 		nbI += impliedLits.size(); maxNoFail = 0;
// 		for(int i=0; i<impliedLits.size(); i++) 
// 		  uncheckedEnqueue(impliedLits[i]);
// 		if (propagate() != CRef_Undef || softConflictFlag) {
// 		  res = false;
// 		  break;
// 		}
// 		trailRecord = trail.size(); falseLitsRecord = falseLits.size();
// 		countedWeightRecord = countedWeight;
// 		satisfiedWeightRecord = satisfiedWeight;
// 	      }
// 	      else
// 		maxNoFail++;
// 	      if (value(p) == l_Undef)
// 		testedVars.push(var(p));
//             }
// 	  }
// 	}
//     }
//     for(int i=0; i<testedVars.size() ; i++)
//       if (value(testedVars[i]) == l_Undef)
// 	insertVarOrder(testedVars[i]);
//     testedVars.clear();
//     printf("c nbFailedLits %d, nbI %d, fixedVarsByFL %d, totalFixedVars %d, nbTested %d, skipped %d\n",
//            nbFailedLits, nbI, trail.size()-initTrail, trail.size(), nbTested, skipped);
//     return res;
// }

bool Solver::eliminateEqLit(CRef cr, Var v, Var targetV) {
  Clause& c=ca[cr];
  assert(c.size() > 1);
  assert(decisionLevel() == 0);
  detachClause(cr, true);
  //p1 is the rpr lit of c[i] such that var(c[i])==v; p2 is c[i], rpr of a lit of v
  Lit p1=lit_Undef, p2=lit_Undef; 
  for(int i=0; i<c.size(); i++) {
    if (var(c[i]) == v) {
      p1=getRpr(c[i]);
      if (p2 == lit_Undef) {
	//c[i] such that var(c[i]) is encountered first, replace it with its rpr
	c[i] = p1; 
      }
      else if (p1 == p2) {
	// the rpr of c[i] was already encountered, discard it
	c[i] = c.last();
	c.shrink(1); nbEqUse++;
	break;
      }
      else if (p1 == ~p2) {
	c.mark(1); ca.free(cr); nbEqUse++;
	return true;
      }
    }
    else if (var(c[i]) == targetV) {
      p2 = c[i];
      if (p1 == p2) {
	c[i] = c.last();
	c.shrink(1); nbEqUse++; break;
      }
      else if (p1 == ~p2) {
	c.mark(1); ca.free(cr); nbEqUse++;
	return true;
      }
    }
  }
  if (c.size() == 1) {
    printf("c unit clause produced by equLit substitution\n");
    uncheckedEnqueue(c[0]);
    if (propagate() != CRef_Undef  || softConflictFlag==true){
      // ok = false;
      return false;
    }
    c.mark(1);
    ca.free(cr);
  }
  else {
    attachClause(cr);
    c.calcAbstraction();
    if (p2 == lit_Undef) //cr was not in the list of targetV
      occurIn[targetV].push(cr);
  }
  return true;
}

bool Solver::extendEquivLitValue(int debut) {
  bool toRepeat;
  do {
    toRepeat=false;
    for(int i=equivLits.size()-1; i>=debut; i--) {
      Lit p=equivLits[i];
      Lit targetP = rpr[toInt(p)];
      if (value(p) == l_Undef && value(targetP) != l_Undef) {
  	toRepeat=true;
  	//	printf("c eqLit not both assigned (original not assigned) %d %d\n", toInt(p), toInt(targetP));
  	if (value(targetP) == l_True)
  	  uncheckedEnqueue(p);
  	else uncheckedEnqueue(~p);
	assert(value(p) ==  value(targetP));
      }
      else if (value(p) != l_Undef && value(targetP) == l_Undef) {
      	toRepeat=true;
	assigns[var(p)] = l_Undef;
      	// //	printf("c eqLits not both assigned (target not assigned) %d %d\n", toInt(p), toInt(targetP));
      	// if (value(p) == l_True)
      	//   uncheckedEnqueue(targetP);
      	// else uncheckedEnqueue(~targetP);
      }
      //  assert(value(p) ==  value(targetP));
    }
  } while (toRepeat);

  do {
    toRepeat=false;
    for(int i=equivLits.size()-1; i>=debut; i--) {
      Lit p=equivLits[i];
      Lit targetP = rpr[toInt(p)];
      if (value(p) == l_Undef && value(targetP) == l_Undef) {
      	printf("c eqLit both unassigned %d(%d) %d(%d, %d, %d) at %d with %d vars at %llu confls****\n",
	       toInt(p), decision[var(p)],
	       toInt(targetP), decision[var(targetP)],
	       toInt(getRpr(targetP)), decision[var(getRpr(targetP))], i, staticNbVars,
	       conflicts);
      	if (auxiVar(var(targetP))) {
	  toRepeat=true;
      	  uncheckedEnqueue(softLits[var(targetP)]);
	}
      	// else 
      	//   uncheckedEnqueue(targetP);
      }
      else if (value(p) == l_Undef && value(targetP) != l_Undef) {
	toRepeat=true;
	//	printf("c eqLit not both assigned (original not assigned) %d %d\n", toInt(p), toInt(targetP));
	if (value(targetP) == l_True)
	  uncheckedEnqueue(p);
	else uncheckedEnqueue(~p);
      }
      else if (value(p) != l_Undef && value(targetP) == l_Undef) {
      	toRepeat=true;
	assigns[var(p)] = l_Undef;
      	// //	printf("c eqLits not both assigned (target not assigned) %d %d\n", toInt(p), toInt(targetP));
      	// if (value(p) == l_True)
      	//   uncheckedEnqueue(targetP);
      	// else uncheckedEnqueue(~targetP);
      }
      // else {
      // 	toRepeat=true;
      // 	assigns[var(p)] = l_Undef;
      // }
    }
  } while (toRepeat);

#ifndef NDEBUG
    for(int i=equivLits.size()-1; i>=debut; i--) {
      Lit p=equivLits[i];
      Lit targetP = rpr[toInt(p)];
      if (value(p) !=  value(targetP))
	printf("%d %d, %d %d, %d %d\n", i, equivLits.size(), toInt(p), toInt(value(p)), toInt(targetP), toInt(value(targetP)));
      assert(value(p) ==  value(targetP));
    }
#endif
    
  return true;
}

// bool Solver::extendEquivLitValue(int debut) {
//   bool toRepeat;
//   do {
//     toRepeat=false;
//     for(int i=equivLits.size()-1; i>=debut; i--) {
//       Lit p=equivLits[i];
//       Lit targetP = getRpr(p);
//       if (value(p) == l_Undef && value(targetP) != l_Undef) {
// 	toRepeat=true;
// 	printf("c eqLit not both assigned (original not assigned) %d %d\n", toInt(p), toInt(targetP));
// 	if (value(targetP) == l_True)
// 	  uncheckedEnqueue(p);
// 	else uncheckedEnqueue(~p);
//       }
//       else if (value(p) != l_Undef && value(targetP) == l_Undef) {
// 	toRepeat=true;
// 	printf("c eqLits not both assigned (target not assigned) %d %d\n", toInt(p), toInt(targetP));
// 	if (value(p) == l_True)
// 	  uncheckedEnqueue(targetP);
// 	else uncheckedEnqueue(~targetP);
//       }
//     }
//   } while (toRepeat);
//   return true;
// }

bool Solver::eliminateEqLits_(int& debut) {
  int nb=0, savedNbEqUse=nbEqUse, nbSofts=0;
  bool toRepeat, softLitRemoved=false;
  int64_t savedUB=UB;
  do {
    toRepeat=false;
    for(int i=debut; i<equivLits.size(); i++) {
      Lit p=equivLits[i];
      Lit targetP = getRpr(p);
      if (value(p) == l_Undef && value(targetP) != l_Undef) {
	toRepeat=true;
	printf("c eqLits not both assigned\n");
	if (value(targetP) == l_True)
	  uncheckedEnqueue(p);
	else uncheckedEnqueue(~p);
	if (propagate() != CRef_Undef  || softConflictFlag==true){
	  // ok = false;
	  return false;
	}
      }
      else if (value(p) != l_Undef && value(targetP) == l_Undef) {
	toRepeat=true;
	printf("c eqLits not both assigned\n");
	if (value(p) == l_True)
	  uncheckedEnqueue(targetP);
	else uncheckedEnqueue(~targetP);
	if (propagate() != CRef_Undef  || softConflictFlag==true){
	  // ok = false;
	  return false;
	}
      }
    }
  } while (toRepeat);
  
  for(int i=debut; i<equivLits.size(); i++) {
    Lit p=equivLits[i];
    Var v= var(p);
    if (value(v) == l_Undef) {
      Lit targetP = getRpr(p);
      Var targetV = var(targetP);
      if (auxiVar(v) && auxiVar(targetV)) {
	if (sign(p)^sign(softLits[v]) == sign(targetP)^sign(softLits[targetV])) {
	  weights[targetV] += weights[v];
	  weightsBckp[targetV] +=  weights[v];
	}
	else {
	  if (weights[targetV] < weights[v]) {
	    rpr[toInt(targetP)] = p;  rpr[toInt(~targetP)] = ~p;
	    rpr[toInt(p)] = lit_Undef;  rpr[toInt(~p)] = lit_Undef;

	    assert(equivLits[i] == p);
	    for(int j = i+1; j<equivLits.size(); j++)
	      equivLits[j-1] = equivLits[j];
	    equivLits[equivLits.size() - 1] = targetP;
	    
	    Lit tmpP=p; p=targetP; targetP=tmpP;
	    Var tmpV=v; v=targetV; targetV = tmpV;

	    i--;
	    continue;
	  }
	  int64_t w, emptyWeight;
	  w = weights[targetV] - weights[v]; emptyWeight =  weights[v];
	  weights[targetV] = w; weightsBckp[targetV] = w;
	  derivedCost += emptyWeight;
	  UB -= emptyWeight; infeasibleUB -= emptyWeight; totalCost -= emptyWeight;
	}
	weights[v] = 0;  weightsBckp[v] = 0; removeSoftLit(softLits[v]); nbSofts++;
	if (weightsBckp[targetV]==0) {
	  removeSoftLit(softLits[targetV]); nbSofts++;
	}
	softLitRemoved = true;
      }
      else if (auxiVar(v) && !auxiVar(targetV)) {
	rpr[toInt(targetP)] = p;  rpr[toInt(~targetP)] = ~p;
	rpr[toInt(p)] = lit_Undef;  rpr[toInt(~p)] = lit_Undef;

	assert(equivLits[i] == p);
	for(int j = i+1; j<equivLits.size(); j++)
	  equivLits[j-1] = equivLits[j];
	equivLits[equivLits.size() - 1] = targetP;
	
	Lit tmpP=p; p=targetP; targetP=tmpP;
	Var tmpV=v; v=targetV; targetV = tmpV;

	i--;
	continue;
      }
      assert(targetP == getRpr(p));
      assert(~targetP == getRpr(~p));
      assert(targetV == var(targetP));
      assert(v == var(p));
      
      vec<CRef>& cs=occurIn.lookup(v);
      assert(!auxiVar(v) || auxiVar(targetV));
      for(int j=0; j<cs.size(); j++) {
	CRef cr=cs[j];
	if (cleanClause(cr) && !eliminateEqLit(cr, v, targetV))
	  return false;
      }

      watches.cleanAll();
      watches_bin.cleanAll();
      
      assert(watches[mkLit(v)].size() == 0);
      assert(watches[~mkLit(v)].size() == 0);
      assert(watches_bin[mkLit(v)].size() == 0);
      assert(watches_bin[~mkLit(v)].size() == 0);

      if (activity_VSIDS[v] > activity_VSIDS[targetV]) {
	activity_VSIDS[targetV] = activity_VSIDS[v];
	if (order_heap_VSIDS.inHeap(targetV))
	  order_heap_VSIDS.decrease(targetV);
      }
      if (activity_CHB[v] > activity_CHB[targetV]) {
	activity_CHB[targetV] = activity_CHB[v];
	if (order_heap_CHB.inHeap(targetV))
	  order_heap_CHB.decrease(targetV);
      }
      //     setDecisionVar(v, false);
      if (decision[v]) {
	setDecisionVar(v, false);
	if (!decision[targetV]) {
	  setDecisionVar(targetV, true);
	  insertAuxiVarOrder(targetV);  insertVarOrder(targetV);
	}
      }
      nb+=cs.size();
    }
  }
  printf("c %d clauses modified by %d eqLits with %d eqUse, DecreasedUB %lld, rm soft %d\n",
	 nb, equivLits.size()-debut, nbEqUse-savedNbEqUse, savedUB-UB, nbSofts);
  debut = equivLits.size();
  if (softLitRemoved) {
    int i, j;
    for( i = 0,j=0; i < allSoftLits.size(); i++)
      if(auxiLit(allSoftLits[i]))
	allSoftLits[j++]=allSoftLits[i];
    
    allSoftLits.shrink(allSoftLits.size()-j);
    assert(allSoftLits.size()==nSoftLits);
  }
  return true;
}

bool Solver::eliminateEqLits() {
  static int prevNbSoftEq=0;
  bool PBCremoved=false;
  if (nbSoftEq > prevNbSoftEq) {
    if (PBC.size() > 0) {
      for (int ci=0; ci < PBC.size(); ci++)
	removeClause(PBC[ci]);
      PBC.clear();
      CCPBadded=false;
      collectDynVars();
      watches.cleanAll();
      watches_bin.cleanAll();
      checkGarbage();
      PBCremoved = true;
    }
    prevNbSoftEq = nbSoftEq;
  }
  int nv=PBCremoved ? staticNbVars : nVars();
  
  occurIn.init(nv);
  for(int i=0; i<nv; i++)
    occurIn[i].clear();
  
  collectClauses(clauses);
  collectClauses(learnts_core, CORE);
  collectClauses(learnts_tier2, TIER2);
  collectClauses(PBC, CORE);
  collectClauses(learnts_local, LOCAL);

  if (!eliminateEqLits_(prevEquivLitsNb))
    return false;

  if (PBCremoved) {
    addPBConstraints();
    if (lPropagate() != CRef_Undef || softConflictFlag)
      return false;
  }
  
  return true;
}

bool Solver::simplifyAll()
{
    ////
    simplified_length_record = original_length_record = 0;

    if (!ok || propagate() != CRef_Undef)
        return false; //ok = false;

    //// cleanLearnts(also can delete these code), here just for analyzing
    //if (local_learnts_dirty) cleanLearnts(learnts_local, LOCAL);
    //if (tier2_learnts_dirty) cleanLearnts(learnts_tier2, TIER2);
    //local_learnts_dirty = tier2_learnts_dirty = false;

    if (!failedLiteralDetection()) return false;

    if (!simplifyLearnt_core()) return false; //ok = false;
    if (!simplifyLearnt_tier2()) return false; //ok = false;
    // if (!simplifyLearnt_local()) return false; //ok = false;
    //if (!simplifyLearnt_x(learnts_local)) false //return ok = false;
    // if (!simplifyUsedOriginalClauses()) false; //return ok = false;

    // if (WithNewUB)
    //   collectDynVars();

    WithNewUB = false;

    checkGarbage();

    ////
    // printf("c size_reduce_ratio     : %4.2f%%\n",
    //        original_length_record == 0 ? 0 : (original_length_record - simplified_length_record) * 100 / (double)original_length_record)
    ;

    return true;
}


#define lbdLimitForOriCls 20

// bool Solver::simplifyUsedOriginalClauses() {

//     int usedClauses_size_before = usedClauses.size();
//     unsigned int nblevels;
//     vec<Lit> lits;
//     int nbSimplified = 0, nbSimplifing = 0, nbShortened=0, nb_remaining=0, nbRemovedLits=0, ci;
//     double avg;

//     for (ci = 0; ci < usedClauses.size(); ci++){
//         CRef cr = usedClauses[ci];
//         Clause& c = ca[cr];

//         if (!removed(cr)) {
//             nbSimplifing++;

//             if (drup_file){
//                 add_oc.clear();
//                 for (int i = 0; i < c.size(); i++) add_oc.push(c[i]); }

//             if (simplifyLearnt(c, cr, lits)) {

//                 if(drup_file && add_oc.size()!=lits.size()){
// #ifdef BIN_DRUP
//                     binDRUP('a', lits , drup_file);
//                     binDRUP('d', add_oc, drup_file);
// #else
//                     for (int i = 0; i < lits.size(); i++)
//                         fprintf(drup_file, "%i ", (var(lits[i]) + 1) * (-2 * sign(lits[i]) + 1));
//                     fprintf(drup_file, "0\n");

//                       fprintf(drup_file, "d ");
//                      for (int i = 0; i < add_oc.size(); i++)
//                          fprintf(drup_file, "%i ", (var(add_oc[i]) + 1) * (-2 * sign(add_oc[i]) + 1));
//                      fprintf(drup_file, "0\n");
// #endif
//                 }

//                 if (lits.size() == 1){
//                     // when unit clause occur, enqueue and propagate
//                     uncheckedEnqueue(lits[0]);
//                     if (propagate() != CRef_Undef || softConflictFlag==true){
// 		      //ok = false;
//                         return false;
//                     }
//                     // delete the clause memory in logic
// 		    detachClause(cr, true);
//                     c.mark(1);
//                     ca.free(cr);
//                 }
//                 else {

//                     if (c.size() > lits.size()) {
//                         nbShortened++; nbRemovedLits += c.size() - lits.size();
//                         nblevels = computeLBD(c);
//                         if (nblevels < c.lbd()){
//                             //printf("lbd-before: %d, lbd-after: %d\n", c.lbd(), nblevels);
//                             c.set_lbd(nblevels);
//                         }
//                     }
//                     detachClause(cr, true);
//                     for(int i=0; i<lits.size(); i++)
//                         c[i]=lits[i];
//                     c.shrink(c.size()-lits.size());
//                     attachClause(cr);

//                     nb_remaining++;
//                     c.setSimplified(3);
//                 }
//             }
//         }
// 	//      c.setUsed(0);
//     }
//     if (nbShortened==0) avg=0;
//     else avg=((double) nbRemovedLits)/nbShortened;
//     //    printf("c nb_usedClauses %d / %d, nbSimplified: %d, nbSimplifing: %d, of which nbShortened: %d with nb removed lits %3.2lf\n",
//     //           usedClauses_size_before, nbSimplified+nb_remaining, nbSimplified, nbSimplifing, nbShortened, avg);
//     usedClauses.clear();

//     return true;
// }

struct clauseSize_lt {
    ClauseAllocator& ca;
    clauseSize_lt(ClauseAllocator& ca_) : ca(ca_) {}
    bool operator () (CRef x, CRef y) const { return ca[x].size() < ca[y].size(); }
};

#define simpLimit 200000000
#define tolerance 100

bool Solver::simplifyOriginalClauses(vec<CRef>& clauseSet) {

    int last_shorten=0;
    vec<Lit> lits;
    uint64_t saved_s_up = s_propagations;

    int nbShortened=0, ci, cj, nbRemoved=0, nbShortening=0;

    sort(clauseSet, clauseSize_lt(ca));
    // printf("c total nb of literals: %llu\n", clauses_literals);
    // if (clauses.size()> simpLimit) {
    //   printf("c too many original clauses (> %d), no original clause minimization \n",
    // 	     simpLimit);
    //   return true;
    // }
#ifndef NDEBUG
    int nbOriginalClauses_before = clauseSet.size();
    double      begin_simp_time = cpuTime();
#endif
    for (ci = 0, cj = 0; ci < clauseSet.size(); ci++){
        CRef cr = clauseSet[ci];
        Clause& c = ca[cr];
        if (removed(cr)) continue;
        // if (ci - last_shorten > tolerance)
        //    clauses[cj++] = clauses[ci];
        // else


        if ((c.size() == 2 &&
             (nbActiveVars[toInt(~c[0])] >= trail.size() && nbActiveVars[toInt(~c[1])] >= trail.size())) ||
            (s_propagations-saved_s_up>simpLimit && ci-last_shorten>tolerance))
            clauseSet[cj++] = clauseSet[ci];
        else{
            if (drup_file){
                add_oc.clear();
                for (int i = 0; i < c.size(); i++) add_oc.push(c[i]); }

            if (simplifyLearnt(c, cr, lits)) {
                if(drup_file && add_oc.size()!=lits.size()){
#ifdef BIN_DRUP
                    binDRUP('a', lits , drup_file);
                    binDRUP('d', add_oc, drup_file);
#else
                    for (int i = 0; i < lits.size(); i++)
                        fprintf(drup_file, "%i ", (var(lits[i]) + 1) * (-2 * sign(lits[i]) + 1));
                    fprintf(drup_file, "0\n");

                      fprintf(drup_file, "d ");
                     for (int i = 0; i < add_oc.size(); i++)
                         fprintf(drup_file, "%i ", (var(add_oc[i]) + 1) * (-2 * sign(add_oc[i]) + 1));
                     fprintf(drup_file, "0\n");
#endif
                }


                nbShortening++;
                if (lits.size() == 1){
                    last_shorten = ci;
                    // when unit clause occur, enqueue and propagate
                    uncheckedEnqueue(lits[0]);
                    if (propagate() != CRef_Undef || softConflictFlag==true){
                        ok = false;
                        return false;
                    }
                    // delete the clause memory in logic
                    detachClause(cr, true);
                    c.mark(1);
                    ca.free(cr);

                }
                else {

                    if (c.size() > lits.size()) {
                        nbShortened++; nbRemoved += c.size() - lits.size(); last_shorten = ci;
                    }
                    detachClause(cr, true);
                    for(int i=0; i<lits.size(); i++)
                        c[i]=lits[i];
                    c.shrink(c.size()-lits.size());
                    attachClause(cr);
                    assert(c == ca[cr]);
                    clauseSet[cj++] = clauseSet[ci];
                    //  c.setSimplified(2);
                }
            }
        }
    }
    clauseSet.shrink(ci - cj);

    double avg;
    if (nbShortened>0)
        avg= ((double)nbRemoved)/nbShortened;
    else avg=0;
#ifndef NDEBUG
    printf("c nb Clauses before/after: %d / %d, nbShortening: %d, nbShortened: %d, avg nbLits removed: %4.2lf\n",
           nbOriginalClauses_before, clauseSet.size(), nbShortening, nbShortened, avg);
    printf("c Original clause minimization time: %5.2lfs, number UPs: %llu\n",
           cpuTime() - begin_simp_time, s_propagations-saved_s_up);
#endif
    return true;
}

//=================================================================================================
// Minor methods:


// Creates a new SAT variable in the solver. If 'decision' is cleared, variable will not be
// used as a decision variable (NOTE! This has effects on the meaning of a SATISFIABLE result).
//
Var Solver::newVar(bool sign, bool dvar)
{
    int v = nVars();
    watches_bin.init(mkLit(v, false));
    watches_bin.init(mkLit(v, true ));
    watches  .init(mkLit(v, false));
    watches  .init(mkLit(v, true ));
    assigns  .push(l_Undef);
    vardata  .push(mkVarData(CRef_Undef, 0));
    activity_CHB  .push(0);
    activity_VSIDS.push(rnd_init_act ? drand(random_seed) * 0.00001 : 0);

    picked.push(0);
    conflicted.push(0);
    almost_conflicted.push(0);
#ifdef ANTI_EXPLORATION
    canceled.push(0);
#endif

    seen     .push(0);
    seen2    .push(0);
    seen2    .push(0);
    polarity .push(sign);
    decision .push();
    trail    .capacity(v+1);

    activity_distance.push(0);
    var_iLevel.push(0); //PROBABLY LOCAL
    var_iLevel_tmp.push(0); //PROBABLY LOCAL
    pathCs.push(0);

    involved.push(0);

    imply.push(lit_Undef);
    imply.push(lit_Undef);

    // softWatches.init(mkLit(v, false));
    // softWatches.init(mkLit(v, true));

    //  lookaheadCNT.push(0);

    /*





    inConflict.push(NON);
    unlockReason.push(var_Undef);
    inConflicts.push(NON);
*/

    conflictLits.init(mkLit(v, false));
    conflictLits.init(mkLit(v, true));
    softLits.push(lit_Undef);
    activityLB.push(0);
    weights.push(0);
    softVarLocked.push(0);

    setDecisionVar(v, dvar);

    nbActiveVars.push(-1);
    nbActiveVars.push(-1);


    score.push(0);
    tmp_score.push(0);
    flip_time.push(0);
    tabu_sattime.push(0);
    assignsLS.push(false);
    inClauses.init(mkLit(v, true));
    neibors.init(v);
    unsatSVidx.push(-1);
    arm_n_picks.push(0);
    Vsoft.push(1);
    coresOfVar.init(v);
    hardened.push(false);
    amosOfVar.push(-1);

    rpr.push(lit_Undef);
    rpr.push(lit_Undef);

    return v;
}

bool Solver::addClause_(vec<Lit>& ps, int64_t weight) {
    assert(decisionLevel() == 0);
    if (!ok) return false;
    // Check if clause is satisfied and remove false/duplicate literals:
    sort(ps);
    Lit p; int i, j;
    if (drup_file){
        add_oc.clear();
        for (int i = 0; i < ps.size(); i++) add_oc.push(ps[i]); }
    for (i = j = 0, p = lit_Undef; i < ps.size(); i++)
        if (value(ps[i]) == l_True || ps[i] == ~p)
            return true;
        else if (value(ps[i]) != l_False && ps[i] != p)
            ps[j++] = p = ps[i];
    ps.shrink(i - j);

    if (drup_file && i != j){
#ifdef BIN_DRUP
        binDRUP('a', ps, drup_file);
        binDRUP('d', add_oc, drup_file);
#else
        for (int i = 0; i < ps.size(); i++)
            fprintf(drup_file, "%i ", (var(ps[i]) + 1) * (-2 * sign(ps[i]) + 1));
        fprintf(drup_file, "0\n");

        fprintf(drup_file, "d ");
        for (int i = 0; i < add_oc.size(); i++)
            fprintf(drup_file, "%i ", (var(add_oc[i]) + 1) * (-2 * sign(add_oc[i]) + 1));
        fprintf(drup_file, "0\n");
#endif
    }


    if (ps.size() == 0) {
        if (hardWeight>0 && weight >= hardWeight || initUB>0 && weight>initUB)
            return ok = false;
        else solutionCost += weight;
    }
    else if (hardWeight>0 && weight >= hardWeight  || initUB>0 && weight>initUB) {
        if (ps.size() == 1) {
            uncheckedEnqueue(ps[0]);
            return ok = (propagate() == CRef_Undef);
        }
        else{
            CRef cr = ca.alloc(ps, false);
            clauses.push(cr);
            attachClause(cr);
        }
		if(initUB>0 && weight>initUB && weight < hardWeight)
			satCost+=weight;
    }
    else {
        CRef cr = ca.alloc(ps, false);
        softClauses.push(cr);
        weightsBckp.push(weight);
    }
    return true;
}

// void Solver::attachSoftClause(CRef cr) {
//   const Clause& c = ca[cr];
//   OccLists<Lit, vec<softWatcher>, softWatcherDeleted>& ws = softWatches;
//   ws[~c[0]].push(softWatcher(cr));
//   softLiterals += c.size();
// }

// void Solver::detachSoftClause(CRef cr, bool strict) {
//     const Clause& c = ca[cr];
//     OccLists<Lit, vec<softWatcher>, softWatcherDeleted>& ws = softWatches;

//     if (strict){
//       remove(ws[~c[0]], softWatcher(cr));
//     }else{
//         // Lazy detaching: (NOTE! Must clean all watcher lists before garbage collecting this clause)
//         ws.smudge(~c[0]);
//     }
//     softLiterals -= c.size();
// }

// void Solver::removeSoftClause(CRef cr) {
//     Clause& c = ca[cr];

//     detachSoftClause(cr);
//     c.mark(1);
//     ca.free(cr);
// }

// void Solver::removeSoftSatisfied(vec<CRef>& cs)
// {
//     int i, j;
//     for (i = j = 0; i < cs.size(); i++){
//         Clause& c = ca[cs[i]];
//         if(c.mark()!=1){
//             if (satisfied(c))
//                 removeSoftClause(cs[i]);
//             else
//                 cs[j++] = cs[i];
//         }
//     }
//     cs.shrink(i - j);
// }

void Solver::attachClause(CRef cr) {
    const Clause& c = ca[cr];
    assert(c.size() > 1);
    OccLists<Lit, vec<Watcher>, WatcherDeleted>& ws = c.size() == 2 ? watches_bin : watches;
    ws[~c[0]].push(Watcher(cr, c[1]));
    ws[~c[1]].push(Watcher(cr, c[0]));
    if (c.learnt()) learnts_literals += c.size();
    else            clauses_literals += c.size(); }


void Solver::detachClause(CRef cr, bool strict) {
    const Clause& c = ca[cr];
    assert(c.size() > 1);
    OccLists<Lit, vec<Watcher>, WatcherDeleted>& ws = c.size() == 2 ? watches_bin : watches;

    if (strict){
        remove(ws[~c[0]], Watcher(cr, c[1]));
        remove(ws[~c[1]], Watcher(cr, c[0]));
    }else{
        // Lazy detaching: (NOTE! Must clean all watcher lists before garbage collecting this clause)
        ws.smudge(~c[0]);
        ws.smudge(~c[1]);
    }

    if (c.learnt()) learnts_literals -= c.size();
    else            clauses_literals -= c.size(); }


void Solver::removeClause(CRef cr) {
    Clause& c = ca[cr];
//    if(c.mark()==1)
//        exit(0);

    if (drup_file){
        if (c.mark() != 1){
#ifdef BIN_DRUP
            binDRUP('d', c, drup_file);
#else
            fprintf(drup_file, "d ");
            for (int i = 0; i < c.size(); i++)
                fprintf(drup_file, "%i ", (var(c[i]) + 1) * (-2 * sign(c[i]) + 1));
            fprintf(drup_file, "0\n");
#endif
        }else
            printf("c Bug. I don't expect this to happen.\n");
    }

    detachClause(cr);
    // Don't leave pointers to free'd memory!
    if (locked(c)){
        Lit implied = c.size() != 2 ? c[0] : (value(c[0]) == l_True ? c[0] : c[1]);
        vardata[var(implied)].reason = CRef_Undef; }
    if (c.mark() != 1 ) {
        c.mark(1);
        ca.free(cr);
    }
}


bool Solver::satisfied(const Clause& c) const {
    for (int i = 0; i < c.size(); i++)
        if (value(c[i]) == l_True)
            return true;
    return false; }


// Revert to the state at given level (keeping all assignment at 'level' but not beyond).
//
void Solver::cancelUntil(int level) {
    if (decisionLevel() > level){
        for (int c = trail.size()-1; c >= trail_lim[level]; c--){
            Var      x  = var(trail[c]);

            if (!VSIDS){
                uint32_t age = conflicts - picked[x];
                if (age > 0){
                    double adjusted_reward = ((double) (conflicted[x] + almost_conflicted[x])) / ((double) age);
                    double old_activity = activity_CHB[x];
                    activity_CHB[x] = step_size * adjusted_reward + ((1 - step_size) * old_activity);
                    if (order_heap_CHB.inHeap(x)){
                        if (activity_CHB[x] > old_activity)
                            order_heap_CHB.decrease(x);
                        else
                            order_heap_CHB.increase(x);
                    }
                }
#ifdef ANTI_EXPLORATION
                canceled[x] = conflicts;
#endif
            }
            assigns [x] = l_Undef;
            if (phase_saving > 1 || (phase_saving == 1) && c > trail_lim.last())
                polarity[x] = sign(trail[c]);
            insertAuxiVarOrder(x);
            insertVarOrder(x);
            if(auxiVar(x)) {
                hardenHeap.update(x);
                hardened[x]=false;
            }
        }

        qhead = trail_lim[level];
        trail.shrink(trail.size() - trail_lim[level]);
        trail_lim.shrink(trail_lim.size() - level);
        falseLits.shrink(falseLits.size() - falseLits_lim[level]);
        falseLits_lim.shrink(falseLits_lim.size() - level);

        countedWeight=countedWeight_lim[level];
        countedWeight_lim.shrink(countedWeight_lim.size() - level);

		satisfiedWeight=satisfiedWeight_lim[level];
		satisfiedWeight_lim.shrink(satisfiedWeight_lim.size() - level);

        for(int i = hardens_lim[level]; i < hardens.size(); i++) {
            assert(ca[hardens[i]].mark()!=1);
            ca[hardens[i]].mark(1);
            ca.free(hardens[i]);
        }
        hardens.shrink_(hardens.size()-hardens_lim[level]);
        hardens_lim.shrink(hardens_lim.size()-level);

		//cleanCores();

#ifndef  NDEBUG
		int64_t w = 0;
		for (int i = 0; i < falseLits.size(); ++i)
			w += weightsBckp[var(falseLits[i])];
		assert(w == countedWeight);
		int64_t wT = 0, wF = 0;
		for (int i = 0; i < trail.size(); i++) {
			Lit p = trail[i];
			Var v = var(p);
			if (auxiVar(v)) {
				if (softLits[v] == p)
					wT += weightsBckp[v];
				else
					wF += weightsBckp[v];
			}
		}
		assert(wF == countedWeight);
		assert(wT == satisfiedWeight);
#endif
        //	unLockedVars_lim.shrink(unLockedVars_lim.size() - level);
    }
}


void Solver::cancelUntilUB() {
    assert(countedWeight>=UB);
    assert(countedWeight_lim.size()==decisionLevel());
    int level = decisionLevel()-1;
    while(level>0 && countedWeight_lim[level]>UB)
        level--;

    printf("Canceled from %d to %d\n", decisionLevel(), level);
    cancelUntil(decisionLevel() - 1);
}


//=================================================================================================
// Major methods:


Lit Solver::pickBranchLit()
{
    Var next = var_Undef;
    //Heap<VarOrderLt>& order_heap = VSIDS ? order_heap_VSIDS : order_heap_CHB;
    Heap<VarOrderLt>& order_heap = DISTANCE ? order_heap_distance : (VSIDS ? order_heap_VSIDS : order_heap_CHB);

    // Random decision:
    /*if (drand(random_seed) < random_var_freq && !order_heap.empty()){
     next = order_heap[irand(random_seed,order_heap.size())];
     if (value(next) == l_Undef && decision[next])
     rnd_decisions++; }*/

    // Activity based decision:
    while (next == var_Undef || value(next) != l_Undef || !decision[next])
        if (order_heap.empty())
            return lit_Undef;
        else{
#ifdef ANTI_EXPLORATION
            if (!VSIDS){
                Var v = order_heap_CHB[0];
                uint32_t age = conflicts - canceled[v];
                while (age > 0){
                    double decay = pow(0.95, age);
                    activity_CHB[v] *= decay;
                    if (order_heap_CHB.inHeap(v))
                        order_heap_CHB.increase(v);
                    canceled[v] = conflicts;
                    v = order_heap_CHB[0];
                    age = conflicts - canceled[v];
                }
            }
#endif
            next = order_heap.removeMin();
        }

    // if (dynVar(next))
    //   printf("a");

    return mkLit(next, polarity[next]);
}

void Solver::reduceClause(CRef cr, int pathC) {
    nbFlyReduced++;
    Clause& c=ca[cr];
    assert(value(c[0]) == l_True);
    if (feasible || c.learnt()) {
        if (pathC == 1) {
            // if (c.learnt())
            // 	removeClause(cr);
            //the clause learnt from the conflict will take the place of cr
            return;
        }
        detachClause(cr, true);
        int max_i = 2;
        // Find the first literal assigned at the next-highest level:
        for (int i = 3; i < c.size(); i++)
            if (level(var(c[i])) >= level(var(c[max_i])))
                max_i = i;
        // here c must contain at least 3 literals assigned at level(var(c[1])): c[0], c[1] and c[max_i],
        // otherwise pathC==1, where c[0] is satisfied
        assert(level(var(c[1])) == level(var(c[max_i])));
        // put this literal at index 0:
        c[0] = c[max_i];

        for(int i=max_i+1; i<c.size(); i++)
            c[i-1] = c[i];
        c.shrink(1);
        attachClause(cr);
    }
}

void Solver::updateClauseUse(CRef confl, bool always) {
    Clause& c = ca[confl];
    int lbd = computeLBD(c);
    if (lbd < c.lbd() || always){
        if (lbd == 1)
            c.setSimplified(0);
        if (c.simplified() > 0)
            c.setSimplified(c.simplified()-1);
        if (c.learnt()) {
            if (c.lbd() <= 30) c.removable(false); // Protect once from reduction.
            // move confl into CORE or TIER2 if the new lbd is small enough
            if  (c.mark() != CORE){
                if (lbd <= core_lbd_cut){
                    learnts_core.push(confl);
                    c.mark(CORE);
                }else if (lbd <= tier2_lbd_cut && c.mark() == LOCAL){
                    // Bug: 'cr' may already be in 'learnts_tier2', e.g., if 'cr' was demoted from TIER2
                    // to LOCAL previously and if that 'cr' is not cleaned from 'learnts_tier2' yet.
                    learnts_tier2.push(confl);
                    c.mark(TIER2); }
            }
        }
        c.set_lbd(lbd);
    }
    if (c.learnt()) {
        if (c.mark() == TIER2 || c.mark() == CORE)
            c.touched() = conflicts;
        //   else if (c.mark() == LOCAL)
        claBumpActivity(c);
    }
    // else {
    //     if (c.used()==0 && c.simplified()==0) {
    //         // if (c.used()==0 && c.lbd() <= lbdLimitForOriCls) {
    //         usedClauses.push(confl);
    //         c.setUsed(1);
    //     }
    // }
}

/*_________________________________________________________________________________________________
 |
 |  analyze : (confl : Clause*) (out_learnt : vec<Lit>&) (out_btlevel : int&)  ->  [void]
 |
 |  Description:
 |    Analyze conflict and produce a reason clause.
 |
 |    Pre-conditions:
 |      * 'out_learnt' is assumed to be cleared.
 |      * Current decision level must be greater than root level.
 |
 |    Post-conditions:
 |      * 'out_learnt[0]' is the asserting literal at level 'out_btlevel'.
 |      * If out_learnt.size() > 1 then 'out_learnt[1]' has the greatest decision level of the
 |        rest of literals. There may be others from the same level though.
 |
 |________________________________________________________________________________________________@*/
void Solver::analyze(CRef confl, vec<Lit>& out_learnt, int& out_btlevel, int& out_lbd)
{

    int pathC = 0;
    Lit p; //     = lit_Undef;
	vec<Lit> c2;

    // Generate conflict clause:
    //
    out_learnt.push();      // (leave room for the asserting literal)
    int index   = trail.size() - 1;

    if (confl == CRef_Bin) {
        assert(level(var(binConfl[0])) == decisionLevel());
        assert(level(var(binConfl[1])) == decisionLevel());
        seen[var(binConfl[0])] = 1; seen[var(binConfl[1])] = 1;  pathC = 2;
        if (VSIDS){
            varBumpActivity(var(binConfl[0]), .5);
            varBumpActivity(var(binConfl[1]), .5);
            add_tmp.push(binConfl[0]);
            add_tmp.push(binConfl[1]);
        }else {
            conflicted[var(binConfl[0])]++;
            conflicted[var(binConfl[1])]++;
        }
        //     printf("c bin bin...\n");
    }
    else {
        updateClauseUse(confl);
        Clause& c = ca[confl];
        for(int i= 0; i<c.size(); i++)
            if (level(var(c[i])) > 0) {
                Var v=var(c[i]);
                if (VSIDS){
                    varBumpActivity(v, .5);
                    add_tmp.push(c[i]);
                }else
                    conflicted[v]++;
                seen[v] = 1;
                if (level(v) >= decisionLevel())
                    pathC++;
                else
                    out_learnt.push(c[i]);
            }
    }
    while (pathC > 0) {
        // Select next clause to look at:
        while (!seen[var(trail[index--])]);
        p     = trail[index+1];
        confl = reason(var(p));
        seen[var(p)] = 0; pathC--;
        if (pathC > 0)
            assert(confl != CRef_Undef); // (otherwise should be UIP)
        else
            break;

        bool hardenedLit = auxiLit(p) && hardened[var(p)];
        bool fromHarden=false;
        if(hardenedLit){
            assert(auxiLit(p));
            Clause & c = ca[confl];
            c[0]=p;
            int lbd = computeLBD(c);
            //Virtual clause, need to be created
            if(lbd<=tier2_lbd_cut) {
                fromHarden=true;
				//Important to make a copy, since alloc may reallocate 'c'
				getClauseLits(c,c2);
                confl = ca.alloc(c2, true);
                attachClause(confl);
            }
            else{
                for (int j = 1; j < c.size(); j++) {
                    Lit q = c[j];
                    Var v = var(q);
                    if (level(v) > 0) {
                        if (!seen[v]){
                            if (VSIDS) {
                                varBumpActivity(v, .5);
                                add_tmp.push(q);
                            } else
                                conflicted[v]++;
                            seen[v] = 1;
                            if (level(v) >= decisionLevel())
                                pathC++;
                            else
                                out_learnt.push(q);
                        }
                    }
                }
            }
        }

        if(!hardenedLit || fromHarden){
            Clause &c = ca[confl];
            fixBinClauseOrder(c);
            updateClauseUse(confl,fromHarden);
            assert(!fromHarden || c.mark()==CORE || c.mark()==TIER2);

            int nbSeen = 0, nbNotSeen = 0;
            int resolventSize = pathC + out_learnt.size() - 1;
            for (int j = 1; j < c.size(); j++) {
                Lit q = c[j];
                Var v = var(q);
                if (level(v) > 0) {
                    if (seen[v])
                        nbSeen++;
                    else /*if (!redundantLit(q))*/ {
                        nbNotSeen++;
                        if (VSIDS) {
                            varBumpActivity(v, .5);
                            add_tmp.push(q);
                        } else
                            conflicted[v]++;
                        seen[v] = 1;
                        if (level(v) >= decisionLevel()) {
                            pathC++;
                        } else
                            out_learnt.push(q);
                    }
                    //  else printf("m\n");
                }
            }
            assert(resolventSize == pathC + out_learnt.size() - 1 - nbNotSeen);
            if (p != lit_Undef && nbSeen >= resolventSize)
                reduceClause(confl, pathC); //printf("a\n");
        }

    }
    out_learnt[0] = ~p;

    simplifyConflictClause(out_learnt, out_btlevel, out_lbd);

    // if (out_lbd > lbdLimitForOriCls) {
    //     for(int i = saved; i < usedClauses.size(); i++)
    //         ca[usedClauses[i]].setUsed(0);
    //     usedClauses.shrink(usedClauses.size() - saved);
    // }
}


// Try further learnt clause minimization by means of binary clause resolution.
bool Solver::binResMinimize(vec<Lit>& out_learnt)
{
    // Preparation: remember which false variables we have in 'out_learnt'.
    counter++;
    for (int i = 1; i < out_learnt.size(); i++)
        seen2[var(out_learnt[i])] = counter;

    int to_remove = 0, limit=out_learnt.size()/2;
    for (int j=1; j<limit; j++) {
        Lit p=out_learnt[j];
        if (seen2[var(p)] == counter) {
            // Get the list of binary clauses containing 'p'.
            const vec<Watcher>& ws = watches_bin[~p];

            for (int i = 0; i < ws.size(); i++){
                Lit the_other = ws[i].blocker;
                // Does 'the_other' appear negatively in 'out_learnt'?
                if (seen2[var(the_other)] == counter && value(the_other) == l_True){
                    to_remove++;
                    seen2[var(the_other)] = counter - 1; // Remember to remove this variable.
                }
            }
        }
    }
    const vec<Watcher>& ws = watches_bin[~out_learnt[0]];
    for (int i = 0; i < ws.size(); i++){
        Lit the_other = ws[i].blocker;
        // Does 'the_other' appear negatively in 'out_learnt'?
        if (seen2[var(the_other)] == counter && value(the_other) == l_True){
            to_remove++;
            seen2[var(the_other)] = counter - 1; // Remember to remove this variable.
        }
    }
    // Shrink.
    if (to_remove > 0){
        int last = out_learnt.size() - 1;
        for (int i = 1; i < out_learnt.size() - to_remove; i++)
            if (seen2[var(out_learnt[i])] != counter)
                out_learnt[i--] = out_learnt[last--];
        out_learnt.shrink(to_remove);
    }
    return to_remove != 0;
}


// Check if 'p' can be removed. 'abstract_levels' is used to abort early if the algorithm is
// visiting literals at levels that cannot be removed later.
bool Solver::litRedundant(Lit p, uint32_t abstract_levels)
{
    analyze_stack.clear(); analyze_stack.push(p);
    int top = analyze_toclear.size();
    while (analyze_stack.size() > 0){
        Var v = var(analyze_stack.last());
        CRef rea = reason(v);
        assert(rea != CRef_Undef);

        Clause& c = ca[rea]; analyze_stack.pop();
        if(!auxiVar(v) || !hardened[v])
            fixBinClauseOrder(c);

        for (int i = 1; i < c.size(); i++){
            Lit p  = c[i];
            if (!seen[var(p)] && level(var(p)) > 0){
                if (reason(var(p)) != CRef_Undef && (abstractLevel(var(p)) & abstract_levels) != 0){
                    seen[var(p)] = 1;
                    analyze_stack.push(p);
                    analyze_toclear.push(p);
                }else{
                    for (int j = top; j < analyze_toclear.size(); j++)
                        seen[var(analyze_toclear[j])] = 0;
                    analyze_toclear.shrink(analyze_toclear.size() - top);
                    return false;
                }
            }
        }
    }

    return true;
}


/*_________________________________________________________________________________________________
 |
 |  analyzeFinal : (p : Lit)  ->  [void]
 |
 |  Description:
 |    Specialized analysis procedure to express the final conflict in terms of assumptions.
 |    Calculates the (possibly empty) set of assumptions that led to the assignment of 'p', and
 |    stores the result in 'out_conflict'.
 |________________________________________________________________________________________________@*/
void Solver::analyzeFinal(Lit p, vec<Lit>& out_conflict)
{
    out_conflict.clear();
    out_conflict.push(p);

    if (decisionLevel() == 0)
        return;

    seen[var(p)] = 1;

    for (int i = trail.size()-1; i >= trail_lim[0]; i--){
        Var x = var(trail[i]);
        if (seen[x]){
            if (reason(x) == CRef_Undef){
                assert(level(x) > 0);
                out_conflict.push(~trail[i]);
            }else{
                Clause& c = ca[reason(x)];
                for (int j = c.size() == 2 ? 0 : 1; j < c.size(); j++)
                    if (level(var(c[j])) > 0)
                        seen[var(c[j])] = 1;
            }
            seen[x] = 0;
        }
    }

    seen[var(p)] = 0;
}


void Solver::uncheckedEnqueue(Lit p, CRef from)
{
    assert(value(p) == l_Undef);
    Var x = var(p);
    if (!VSIDS){
        picked[x] = conflicts;
        conflicted[x] = 0;
        almost_conflicted[x] = 0;
#ifdef ANTI_EXPLORATION
        uint32_t age = conflicts - canceled[var(p)];
        if (age > 0){
            double decay = pow(0.95, age);
            activity_CHB[var(p)] *= decay;
            if (order_heap_CHB.inHeap(var(p)))
                order_heap_CHB.increase(var(p));
        }
#endif
    }

    assigns[x] = lbool(!sign(p));
    vardata[x] = mkVarData(from, decisionLevel());
    trail.push_(p);
    if (auxiVar(x) && weightsBckp[x] > 0){
		if(softLits[x]==~p) {// a soft clause is falsified
			falseLits.push(~p);
			if(weights[x]!=weightsBckp[x])
			    removeIsetsOfLit(~p);
			assert(weights[x]==weightsBckp[x]);
			countedWeight+=weights[x];
		}
		else {
            assert(value(p) == l_True);
			satisfiedWeight += weightsBckp[x];
		}
	}
}


/*_________________________________________________________________________________________________
 |
 |  propagate : [void]  ->  [Clause*]
 |
 |  Description:
 |    Propagates all enqueued facts. If a conflict arises, the conflicting clause is returned,
 |    otherwise CRef_Undef.
 |
 |    Post-conditions:
 |      * the propagation queue is empty, even if there was a conflict.
 |________________________________________________________________________________________________@*/
CRef Solver::propagate()
{
    softConflictFlag =false;
    // if (falseLits.size() >= UB) { // no need to propagate if a soft conflict occurs
    //   softConflictFlag=true;
    //   return CRef_Undef;
    // }
    CRef    confl     = CRef_Undef;
    int     num_props = 0;
    //   Lit conflLit = lit_Undef;
    watches.cleanAll();
    watches_bin.cleanAll();

    while (qhead < trail.size()){
        Lit            p   = trail[qhead++];     // 'p' is enqueued fact to propagate.
        // if (p == conflLit)
        //   break;
        vec<Watcher>&  ws  = watches[p];
        Watcher        *i, *j, *end;
        num_props++;

        vec<Watcher>& ws_bin = watches_bin[p];  // Propagate binary clauses first.
        for (int k = 0; k < ws_bin.size(); k++){
            Lit the_other = ws_bin[k].blocker;
            if (value(the_other) == l_False){
                binConfl[0] = ~p; binConfl[1]=the_other;
                confl = CRef_Bin;
                //confl = ws_bin[k].cref;
#ifdef LOOSE_PROP_STAT
                return confl;
#else
                goto ExitProp;
#endif
            }else if(value(the_other) == l_Undef) {
                uncheckedEnqueue(the_other, ws_bin[k].cref);
                // if (falseLits.size() >= UB && conflLit == lit_Undef) {
                //   assert(auxiVar(var(the_other)));
                //   conflLit = the_other;

// 		  softConflictFlag = true;
// #ifdef LOOSE_PROP_STAT
// 		  return confl;
// #else
// 		  goto ExitProp;
// #endif
                //	}
            }
        }
        for (i = j = (Watcher*)ws, end = i + ws.size();  i != end;){
            // Try to avoid inspecting the clause:
            Lit blocker = i->blocker;
            if (value(blocker) == l_True){
                *j++ = *i++; continue; }

            // Make sure the false literal is data[1]:
            CRef     cr        = i->cref;
            Clause&  c         = ca[cr];
            Lit      false_lit = ~p;
            if (c[0] == false_lit)
                c[0] = c[1], c[1] = false_lit;
            assert(c[1] == false_lit);

            // If 0th watch is true, then clause is already satisfied.
            Lit     first = c[0];
            //  Watcher w     = Watcher(cr, first);
            if (first != blocker && value(first) == l_True){
                i->blocker = first;
                *j++ = *i++; continue; }

            // Look for new watch:
            assert(c.lastPoint() >=2);
            if (c.lastPoint() > c.size())
                c.setLastPoint(2);
            for (int k = c.lastPoint(); k < c.size(); k++) {
                if (value(c[k]) == l_Undef) {
                    // watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
                    // the blocker is first in the watcher. However,
                    // the blocker in the corresponding watcher in ~first is not c[1]
                    Watcher w = Watcher(cr, first); i++;
                    c[1] = c[k]; c[k] = false_lit;
                    watches[~c[1]].push(w);
                    c.setLastPoint(k+1);
                    goto NextClause;
                }
                else if (value(c[k]) == l_True) {
                    i->blocker = c[k];  *j++ = *i++;
                    c.setLastPoint(k);
                    goto NextClause;
                }
            }
            for (int k = 2; k < c.lastPoint(); k++) {
                if (value(c[k]) ==  l_Undef) {
                    // watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
                    // the blocker is first in the watcher. However,
                    // the blocker in the corresponding watcher in ~first is not c[1]
                    Watcher w = Watcher(cr, first); i++;
                    c[1] = c[k]; c[k] = false_lit;
                    watches[~c[1]].push(w);
                    c.setLastPoint(k+1);
                    goto NextClause;
                }
                else if (value(c[k]) == l_True) {
                    i->blocker = c[k];  *j++ = *i++;
                    c.setLastPoint(k);
                    goto NextClause;
                }
            }

            // Did not find watch -- clause is unit under assignment:
            i->blocker=first;
            *j++ = *i++;
            if (value(first) == l_False){
                confl = cr;
                qhead = trail.size();
                // Copy the remaining watches:
                while (i < end)
                    *j++ = *i++;
            }else {
                uncheckedEnqueue(first, cr);
                // if (falseLits.size() >= UB && conflLit == lit_Undef) {
                //   assert(auxiVar(var(first)));
                //   conflLit = first;

                // qhead = trail.size();
                // // Copy the remaining watches:
                // while (i < end)
                //   *j++ = *i++;
                // softConflictFlag = true;
                //	}
            }
            NextClause:;
        }
        ws.shrink(i - j);
        // if (confl == CRef_Undef)
        //   if (shortenSoftClauses(p))
        //     break;
    }

    propagations += num_props;
    simpDB_props -= num_props;

    if (confl == CRef_Undef && countedWeight + laConflictCost>= UB) {
        assert(!CCPBadded || laConflictCost>0);
        softConflictFlag = true;
    }

    return confl;
}

bool Solver::redundantLit(Lit p) {
    Lit q=imply[toInt(p)];
    return q != lit_Undef && value(q) == l_False && seen[var(q)];
}

void Solver::getAllUIP(vec<Lit>& out_learnt, int& out_btlevel, int& out_lbd) {
    assert(out_learnt.size() > 2);
    vec<Lit> uips;
    uips.clear(); uips.push(out_learnt[0]);
    counter++;
    int minLevel=decisionLevel(), lbd=0;
    for(int i=1; i<out_learnt.size(); i++) {
        Var v=var(out_learnt[i]);
        if (level(v)>0) {
            assert(!seen[v]);
            seen[v]=1;
            pathCs[level(v)]++;
            if (minLevel>level(v))
                minLevel=level(v);
            if (seen2[level(v)] != counter) {
                lbd++;
                seen2[level(v)] = counter;
            }
        }
    }
    int limit=trail_lim[minLevel-1]; //begining position of level minLevel
    for(int i=trail_lim[level(var(out_learnt[1]))] - 1; i>=limit; i--) {

        // for(int ii=0; ii<learnts_tier2.size(); ii++) {
        // 	if (!ca[learnts_tier2[ii]].has_extra())
        // 	  printf("++++%d %llu\n", ii, conflicts);
        // 	assert(ca[learnts_tier2[ii]].has_extra());
        // }
        assert(limit>=0);
        Lit p=trail[i]; Var v=var(p);
        if (seen[v]) {
            int currentDecLevel=level(v);
            assert(pathCs[currentDecLevel] > 0);
            seen[v]=0;
            if (--pathCs[currentDecLevel]==0) {
                // v is the last var of the level directly involved in the conflict
                uips.push(~p); lbd--;
            }
            else {
                assert(reason(v) != CRef_Undef);
                Clause& c=ca[reason(v)];
                if(!auxiVar(v) || !hardened[v])
                    fixBinClauseOrder(c);

                // for(int ii=0; ii<learnts_tier2.size(); ii++) {
                //   if (!ca[learnts_tier2[ii]].has_extra())
                //     printf("----%d %d %llu\n", ii, i, conflicts);
                //   assert(ca[learnts_tier2[ii]].has_extra());
                // }
                int j;
                for (j = 1; j < c.size(); j++){
                    Lit q = c[j]; Var v1=var(q);
                    if (!seen[v1] && level(v1) > 0 && !redundantLit(q) && seen2[level(v1)] != counter)
                        break; // new level
                }
                if (j < c.size()) {
                    uips.push(~p);
                    if (uips.size() + lbd >= out_learnt.size()) {
                        for(int k=i; k>=limit; k--) {
                            Lit q=trail[k]; Var vv=var(q);
                            if (seen[vv]) {
                                seen[vv] = 0;
                                pathCs[level(vv)] = 0;
                            }
                        }
                        break;
                    }
                }
                else {
                    for (j = 1; j < c.size(); j++){
                        Lit q = c[j]; Var v1=var(q);
                        if (!seen[v1] && level(v1) > 0 && !redundantLit(q)){
                            assert(level(v1)<pathCs.size() && minLevel <= level(v1));
                            // if (minLevel>level(v1)) {
                            // 	minLevel=level(v1); limit=trail_lim[minLevel-1];
                            // }
                            seen[v1] = 1;
                            pathCs[level(v1)]++;
                        }
                    }
                }
            }
        }
    }
    if (uips.size() + lbd < out_learnt.size()) {
        int myLevel = decisionLevel() +1;
        out_learnt.clear();
        for(int i=0; i<uips.size(); i++) {
            out_learnt.push(uips[i]);
            assert(myLevel >= level(var(uips[i])));
            myLevel = level(var(uips[i]));
        }
        //   out_lbd = out_learnt.size();
        out_btlevel = level(var(out_learnt[1]));
    }
}

void Solver::seeReason(vec<Lit> & conflictClause, int & maxConflLevel, Lit q){
    Var v = var(q);
    assert(level(v) > 0);
    assert(value(q)==l_False);
    if (!seen[v]) {
        seen[v] = 1;
        conflictClause.push(q);
        if (level(v) > maxConflLevel)
            maxConflLevel = level(v);
    }
}

void Solver::seeReasons(vec<Lit> & conflictClause, int & maxConflLevel, vec<Lit> & reasons){
    for (int j = 0; j < reasons.size(); j++) {
        Lit q = reasons[j];
        Var v = var(q);
        assert(value(q) == l_False);
        if (!seen[v] && level(v)>0) {
            seen[v] = 1;
            conflictClause.push(q);
            if (level(v) > maxConflLevel)
                maxConflLevel = level(v);
        }
    }
}

void Solver::getConflictingClause(vec<Lit> & conflictClause, int & maxConflLevel){

    int64_t usedCountedWeight = countedWeight + laConflictCost;
    int debutFalse = falseLits_lim.size() > 0 ? falseLits_lim[0] : falseLits.size();
    maxConflLevel=0;

    //-1: not involved
    //-2: involved by more than one
    //i >=0: involved  just by i-th core
    vec<int> coreOfLevel(decisionLevel()+1, -1);
    vec<int> nLevelsOfCore(falseLits.size()+localCores.size(),0);
    vec<int> minLevelOfCore(falseLits.size()+localCores.size(),INT32_MAX);
    vec<int> skipCores; //Cores candidate to be skipped
    vec<int> neededCores; //Cores that cannot be skipped

    //Identify decision levels only involved by 1 core
    //and the cores that could be removed
    for(int i = debutFalse; i < falseLits.size(); i++) {
        Var v = var(falseLits[i]);
        if (coreOfLevel[level(v)] == -1)
            coreOfLevel[level(v)]=i;
        else if(coreOfLevel[level(v)] >= 0)
            coreOfLevel[level(v)]=-2;
        if(usedCountedWeight >= UB + weights[v])
            skipCores.push(i);
        else
            neededCores.push(i);
    }

    for(int i = 0; i < activeCores.size(); i++) {
        int core = activeCores[i];
        if (localCores[core].weight > 0) {
            vec<int> newLevels;
            for (int j = 0; j < localCores[core].reasons.size(); j++) {
                Lit q = localCores[core].reasons[j];
                Var v = var(q);
                if (coreOfLevel[level(v)] == -1)
                    newLevels.push(level(v));
                else if(coreOfLevel[level(v)] >= 0)
                    coreOfLevel[level(v)]=-2;
            }
            for(int j = 0; j< newLevels.size(); j++)
                coreOfLevel[newLevels[j]]= falseLits.size() + core;

            if(usedCountedWeight >= UB + localCores[core].weight)
                skipCores.push(falseLits.size() + core);
            else
                neededCores.push(falseLits.size() + core);
        }
    }

    //Compute the number of levels that each core would remove, and the minimum level
    for(int i = 1; i <= decisionLevel(); i++){
        int core = coreOfLevel[i];
        if(core>=0) { //If just one core uses this level
            if (nLevelsOfCore[core] == 0 )
                minLevelOfCore[core] = i;
            nLevelsOfCore[core]++;

        }
    }

    //Add all mandatory cores
    for(int i = 0; i < neededCores.size(); i++){
        int core=neededCores[i];
        if(core<falseLits.size()){
            Lit q = falseLits[core];
            seeReason(conflictClause,maxConflLevel,q);
        }
        else{
            core-=falseLits.size();
            seeReasons(conflictClause,maxConflLevel,localCores[core].reasons);
            for(int j = 0; j < localCores[core].refCores.size(); j++){
                int core2 = localCores[core].refCores[j];
                seeReasons(conflictClause,maxConflLevel,localCores[core2].reasons);
            }
        }
    }

    sort(skipCores,SkipCoresOrder(nLevelsOfCore,minLevelOfCore));
    //Add removable cores if cost is not reached
    for(int i = 0; i < skipCores.size(); i++){
        int core=skipCores[i];
        if(core<falseLits.size()){
            Lit q = falseLits[core]; Var v = var(q);
            assert(level(v) > 0);
            assert(value(q)==l_False);
            if(usedCountedWeight >= UB + weights[v]) {
                usedCountedWeight -= weights[v];
            }
            else {
                seeReason(conflictClause,maxConflLevel,q);
            }
        }
        else{
            core-=falseLits.size();
            if (usedCountedWeight >= UB + localCores[core].weight) {
                usedCountedWeight -= localCores[core].weight;
            }
            else {
                seeReasons(conflictClause,maxConflLevel,localCores[core].reasons);
                for(int j = 0; j < localCores[core].refCores.size(); j++){
                    int core2 = localCores[core].refCores[j];
                    seeReasons(conflictClause,maxConflLevel,localCores[core2].reasons);
                }
            }
        }
    }


    for(int a=0; a<conflictClause.size(); a++)
        seen[var(conflictClause[a])] = 0;

    //Check that some has been skipped if possible
    assert(skipCores.size()==0 || usedCountedWeight <  countedWeight + laConflictCost);
    assert(usedCountedWeight>=UB);

}


void Solver::getConflictingClauseSimple(vec<Lit> & conflictClause, int & maxConflLevel){

    int debutFalse = falseLits_lim.size() > 0 ? falseLits_lim[0] : falseLits.size();
    maxConflLevel=0;

    for(int i = debutFalse; i < falseLits.size(); i++)
        seeReason(conflictClause,maxConflLevel,falseLits[i]);


    for(int i = 0; i < activeCores.size(); i++) {
        int core = activeCores[i];
        if (localCores[core].weight > 0) {
            seeReasons(conflictClause,maxConflLevel,localCores[core].reasons);
            for(int j = 0; j < localCores[core].refCores.size(); j++){
                int core2 = localCores[core].refCores[j];
                seeReasons(conflictClause,maxConflLevel,localCores[core2].reasons);
            }
        }
    }


    for(int a=0; a<conflictClause.size(); a++)
        seen[var(conflictClause[a])] = 0;
}


void Solver::analyzeSoftConflict(vec<Lit>& out_learnt, int& out_btlevel, int& out_lbd)
{
    int pathC = 0;
    Lit p;
	vec<Lit> c2;
    CRef confl;

    if (countedWeight >= UB)
        pureSoftConfl++;

    // Generate conflict clause:
	vec<Lit> conflictClause;
	int maxConflLevel;
    getConflictingClauseSimple(conflictClause, maxConflLevel);

    out_learnt.push();      // (leave room for the asserting literal)


	for(int a=0; a<conflictClause.size(); a++) {
		Var v=var(conflictClause[a]);
		if (!seen[v] /*&& !redundantLit(conflictClause[a])*/) {
			assert(level(v)>0);
            seen[v] = 1;
            if (VSIDS){
                varBumpActivity(v, .5);
                add_tmp.push(conflictClause[a]);
            }else
                conflicted[v]++;
			if (level(v) >= maxConflLevel)
				pathC++;
			else
				out_learnt.push(conflictClause[a]);
		}
	}

	assert(pathC > 0 || maxConflLevel==0);
    if (maxConflLevel==0) {
        printf("c ***** \n");
        assert(pathC == 0 && UBconflictFlag);
        out_btlevel=0; out_lbd=0; out_learnt.clear();
        return;
    }

    int index   = trail.size() - 1;
    while (pathC > 0) {
        while (!seen[var(trail[index--])]);
        p     = trail[index+1];
        confl = reason(var(p));
        seen[var(p)] = 0;
        pathC--;
        // sign(p) returns the last bit of p. p is positive iff sign(p)= 0 or false
        // p should not be UIP if it is a negative auxi literal (i.e., if it represents a false soft clause)
        //if (pathC == 0 && !(auxiVar(var(p)) && sign(p)))
        //if (pathC == 0 && !(auxiVar(var(p))))
        if (pathC == 0)
            break;

        bool hardenedLit = auxiLit(p) && hardened[var(p)];
        bool fromHarden=false;
        if(hardenedLit){
            assert(auxiLit(p));
            Clause & c = ca[confl];
            c[0]=p;
            int lbd = computeLBD(c);
            //Virtual clause, need to be created
            if(lbd<=tier2_lbd_cut) {
                fromHarden=true;
				//Important to make a copy, since alloc may reallocate 'c'
				getClauseLits(c,c2);
                confl = ca.alloc(c2, true);
                attachClause(confl);
            }
            else{
                for (int j = 1; j < c.size(); j++) {
                    Lit q = c[j];
                    Var v = var(q);
                    if (level(v) > 0) {
                        if (!seen[v]){
                            if (VSIDS) {
                                varBumpActivity(v, .5);
                                add_tmp.push(q);
                            } else
                                conflicted[v]++;
                            seen[v] = 1;
                            if (level(v) >= maxConflLevel)
                                pathC++;
                            else
                                out_learnt.push(q);
                        }
                    }
                }
            }
        }

        if(!hardenedLit || fromHarden){
            assert(confl != CRef_Undef); // (otherwise should be UIP)
            Clause &c = ca[confl];

            fixBinClauseOrder(c);
            updateClauseUse(confl,fromHarden);
            assert(!fromHarden || c.mark()==CORE || c.mark()==TIER2);

            int nbSeen = 0, nbNotSeen = 0;
            int resolventSize = pathC + out_learnt.size() - 1;
            for (int j = 1; j < c.size(); j++) {
                Lit q = c[j];
                Var v = var(q);
                if (level(v) > 0) {
                    if (seen[v])
                        nbSeen++;
                    else {
                        // if (level(v) > 0 && !seen[v] && !redundantLit(q)) {
                        nbNotSeen++;
                        if (VSIDS) {
                            varBumpActivity(v, .5);
                            add_tmp.push(q);
                        } else
                            conflicted[v]++;
                        seen[v] = 1;
                        if (level(v) >= maxConflLevel) {
                            pathC++;
                        } else
                            out_learnt.push(q);
                    }
                }
            }
            assert(resolventSize == pathC + out_learnt.size() - 1 - nbNotSeen);
            if (pathC > 1 && nbSeen >= resolventSize) {
                reduceClause(confl, pathC); //printf("b\n");
            }
        }
    }
    out_learnt[0] = ~p;

    simplifyConflictClause(out_learnt, out_btlevel, out_lbd);
    assert(out_btlevel >0 || out_learnt.size() == 1);
    if (out_lbd > core_lbd_cut)
        getAllUIP(out_learnt, out_btlevel, out_lbd);


    // for(int i=0; i<out_learnt.size(); i++)
    //   printf("%d ", toInt(out_learnt[i]));
    // printf(", btlevel %d, lbd %d, trail: %d, level: %d, lim0: %d, confl: %llu, starts: %llu, lkUP: %llu, UP: %llu, falseLit1: %d, fsize: %d\n",
    // 	   out_btlevel, out_lbd, trail.size(), decisionLevel(), trail_lim[0],
    // 	   conflicts, starts, lk_propagations, propagations, toInt(falseLits[0]), nbFalseLits);
    // for(int i=0; i<conflLits.size(); i++)
    //   printf("%d ", toInt(conflLits[i]));
    // printf("\n%d\n", conflLits.size());


    // if (out_lbd > lbdLimitForOriCls) {
    //     for(int i = saved; i < usedClauses.size(); i++)
    //         ca[usedClauses[i]].setUsed(0);
    //     usedClauses.shrink(usedClauses.size() - saved);
    // }

}

void Solver::simplifyConflictClause(vec<Lit>& out_learnt, int& out_btlevel, int& out_lbd) {
    // Simplify conflict clause:
    int i, j;
    out_learnt.copyTo(analyze_toclear);
    if (ccmin_mode == 2){
        uint32_t abstract_level = 0;
        for (i = 1; i < out_learnt.size(); i++)
            abstract_level |= abstractLevel(var(out_learnt[i])); // (maintain an abstraction of levels involved in conflict)

        for (i = j = 1; i < out_learnt.size(); i++)
            if (reason(var(out_learnt[i])) == CRef_Undef || !litRedundant(out_learnt[i], abstract_level))
                out_learnt[j++] = out_learnt[i];

    }else if (ccmin_mode == 1){
        for (i = j = 1; i < out_learnt.size(); i++){
            Var x = var(out_learnt[i]);

            if (reason(x) == CRef_Undef)
                out_learnt[j++] = out_learnt[i];
            else{
                Clause& c = ca[reason(var(out_learnt[i]))];
                if(auxiVar(x) && hardened[x])
                    c[0]=out_learnt[i];
                for (int k = c.size() == 2 ? 0 : 1; k < c.size(); k++)
                    if (!seen[var(c[k])] && level(var(c[k])) > 0){
                        out_learnt[j++] = out_learnt[i];
                        break; }
            }
        }
    }else
        i = j = out_learnt.size();

    max_literals += out_learnt.size();
    out_learnt.shrink(i - j);
    tot_literals += out_learnt.size();

    out_lbd = computeLBD(out_learnt);
    if (out_lbd <= tier2_lbd_cut && out_learnt.size() <= 35) // Try further minimization?
        if (binResMinimize(out_learnt))
            out_lbd = computeLBD(out_learnt); // Recompute LBD if minimized.

    // Find correct backtrack level:
    //
    if (out_learnt.size() == 1)
        out_btlevel = 0;
    else{
        int max_i = 1;
        // Find the first literal assigned at the next-highest level:
        for (int i = 2; i < out_learnt.size(); i++)
            if (level(var(out_learnt[i])) > level(var(out_learnt[max_i])))
                max_i = i;
        // Swap-in this literal at index 1:
        Lit p             = out_learnt[max_i];
        out_learnt[max_i] = out_learnt[1];
        out_learnt[1]     = p;
        out_btlevel       = level(var(p));
    }

    if (VSIDS){
        for (int i = 0; i < add_tmp.size(); i++){
            Var v = var(add_tmp[i]);
            if (level(v) >= out_btlevel - 1)
                varBumpActivity(v, 1);
        }
        add_tmp.clear();
    }else{
        seen[var(out_learnt[0])] = true;
        for(int i = out_learnt.size() - 1; i >= 0; i--){
            Var v = var(out_learnt[i]);
            CRef rea = reason(v);
            if (rea != CRef_Undef){
                const Clause& reaC = ca[rea];
                if(auxiVar(v) && hardened[v])
                    reaC[0]=out_learnt[i];
                for (int i = 0; i < reaC.size(); i++){
                    Lit l = reaC[i];
                    if (!seen[var(l)]){
                        seen[var(l)] = true;
                        almost_conflicted[var(l)]++;
                        analyze_toclear.push(l); } } } } }
    for (int j = 0; j < analyze_toclear.size(); j++) seen[var(analyze_toclear[j])] = 0;    // ('seen[]' is now cleared)
}

// // Precondition: p is false and should be removed from the soft clauses it watches
// bool Solver::shortenSoftClauses(Lit p) {
//   vec<softWatcher>&  ws  = softWatches[p];
//   softWatcher        *i, *j, *end;
//   for (i = j = (softWatcher*)ws, end = i + ws.size();  i != end;){
//     CRef     cr= i->cref;
//     Clause&  c         = ca[cr];
//     assert(~p == c[0]);
//     // Look for new watch:
//     for (int k = 1; k < c.size(); k++)
//       if (value(c[k]) != l_False){
// 	c[0] = c[k]; c[k] = ~p;
// 	softWatches[~c[0]].push(softWatcher(cr));
// 	i++;
// 	goto NextClause;
//       }
//     // Did not find watch: the soft clause c is false under the current partial assignment:
//     *j++ = *i++;
//     falseSoftClauses.push(cr);
//     if (falseSoftClauses.size() >= UB) { //for unweighted MaxSAT
//       softConflictFlag = true;
//       while (i < end)
// 	*j++ = *i++;
//     }
//   NextClause:;
//   }
//   ws.shrink(i - j);
//   return softConflictFlag;
// }

/*_________________________________________________________________________________________________
 |
 |  reduceDB : ()  ->  [void]
 |
 |  Description:
 |    Remove half of the learnt clauses, minus the clauses locked by the current assignment. Locked
 |    clauses are clauses that are reason to some assignment. Binary clauses are never removed.
 |________________________________________________________________________________________________@*/
struct reduceDB_lt {
    ClauseAllocator& ca;
    reduceDB_lt(ClauseAllocator& ca_) : ca(ca_) {}
    bool operator () (CRef x, CRef y) {
        if (ca[x].activity() < ca[y].activity()) return true;
        if (ca[x].activity() > ca[y].activity()) return false;

        if(ca[x].lbd() > ca[y].lbd()) return true;
        if(ca[x].lbd() < ca[y].lbd()) return false;

        // Finally we can use old activity or size, we choose the last one

        return ca[x].size() > ca[y].size();
    }
};

bool Solver::simplifyLearnt_local() {
   // int learnts_local_size_before = learnts_local.size();
   // int savedTrail = trail.size();
    unsigned int nblevels;
    vec<Lit> lits;

    int nbSimplified = 0, nbSimplifing = 0, nbShortened=0, ci, cj;

    sort(learnts_local, reduceDB_lt(ca));

    int limit = 7*learnts_local.size() / 8;

    for (ci = limit, cj = limit; ci < learnts_local.size() ; ci++){
        CRef cr = learnts_local[ci];
        Clause& c = ca[cr];

        if (removed(cr)) continue;
        else if ((c.simplified() && !WithNewUB) || c.activity() == 0) {
            learnts_local[cj++] = learnts_local[ci];
            ////
            // if (c.used() == 0)
            nbSimplified++;
        }
        else{
            ////
            nbSimplifing++;
            // if (drup_file){
            //     add_oc.clear();
            //     for (int i = 0; i < c.size(); i++) add_oc.push(c[i]); }
            int oriLength = c.size();
            if (simplifyLearnt(c, cr, lits)) {

                if (drup_file && oriLength!=lits.size()) {
#ifdef BIN_DRUP
                    binDRUP('a', lits , drup_file);
//                    binDRUP('d', add_oc, drup_file);
#else
                    for (int i = 0; i < lits.size(); i++)
                        fprintf(drup_file, "%i ", (var(lits[i]) + 1) * (-2 * sign(lits[i]) + 1));
                    fprintf(drup_file, "0\n");

//                      fprintf(drup_file, "d ");
//                     for (int i = 0; i < add_oc.size(); i++)
//                         fprintf(drup_file, "%i ", (var(add_oc[i]) + 1) * (-2 * sign(add_oc[i]) + 1));
//                     fprintf(drup_file, "0\n");
#endif
                }
                if (lits.size() == 0)
                    return false;
                if (lits.size() == 1){
                  //  int savedFalseLits = falseLits.size();
                    // when unit clause occur, enqueue and propagate
                    uncheckedEnqueue(lits[0]);
                    if (propagate() != CRef_Undef || softConflictFlag==true){
                        //ok = false;
                        return false;
                    }
                    // delete the clause memory in logic
                    detachClause(cr, true);
                    c.mark(1);
                    ca.free(cr);
                    //updateIsetLock(savedFalseLits);
                }
                else {
                    if (c.size() > lits.size())
                        nbShortened++;
                    detachClause(cr, true);
                    for(int i=0; i<lits.size(); i++)
                        c[i]=lits[i];
                    c.shrink(c.size()-lits.size());
                    attachClause(cr);

                    nblevels = computeLBD(c);
                    if (nblevels < c.lbd()){
                        //printf("lbd-before: %d, lbd-after: %d\n", c.lbd(), nblevels);
                        c.set_lbd(nblevels);
                    }

                    if (c.lbd() <= core_lbd_cut){
                        learnts_core.push(cr);
                        c.mark(CORE);
                    }
                    else if (c.lbd() <= tier2_lbd_cut) {
                        learnts_tier2.push(cr);
                        c.mark(TIER2);
                    }
                    else learnts_local[cj++] = learnts_local[ci];
                    c.setSimplified(2);
                }
            }
        }
    }
    learnts_local.shrink(ci - cj);

    // printf("c nbLearnts_local %d / %d, nbSimplified: %d, nbSimplifing: %d, of which nbShortened: %d, fixed: %d\n",
    //           learnts_local_size_before, learnts_local.size(), nbSimplified, nbSimplifing, nbShortened, trail.size()- savedTrail);

    return true;
}

void Solver::reduceDB()
{
    int     i, j;
    //if (local_learnts_dirty) cleanLearnts(learnts_local, LOCAL);
    //local_learnts_dirty = false;
    // printf("c caSize: %d, caWasted: %d (%4.3f), nbCORE: %d, nbTIER2: %d, conflicts: %llu, hardConfl: %llu\n",
    // 	   ca.size(), ca.wasted(), (float)ca.wasted()/ca.size(), learnts_core.size(), learnts_tier2.size(), conflicts, conflicts-softConflicts);

    sort(learnts_local, reduceDB_lt(ca));

    int limit = learnts_local.size() / 2;
    int totalLocalSize=0, removedSize=0;
    for (i = j = 0; i < learnts_local.size(); i++){
        Clause& c = ca[learnts_local[i]];
        totalLocalSize += c.size();
        if (c.learnt() && c.mark() == LOCAL)
            if (c.removable() && !locked(c) && i < limit) {
                removedSize += c.size();
                removeClause(learnts_local[i]);
            }
            else{
                if (!c.removable()) limit++;
                c.removable(true);
                learnts_local[j++] = learnts_local[i];
            }
    }
    learnts_local.shrink(i - j);
    // printf("c removedSize: %d(%4.2f), over totalLocalSize: %d (%4.2f), NBremoved: %d, over nbLocalBefore: %d\n",
    // 	   removedSize, (float)removedSize/(i-j), totalLocalSize, (float)totalLocalSize/i, i-j, i);
    // printf("c %d ca size: %d, ca wasted: %d (%4.3f)\n\n",
    // 	   nbClauseReduce, ca.size(), ca.wasted(), (float)ca.wasted()/ca.size());
    checkGarbage();
}

// struct reduceTIER2_lt {
//     ClauseAllocator& ca;
//     reduceTIER2_lt(ClauseAllocator& ca_) : ca(ca_) {}
//   bool operator () (CRef x, CRef y) {

//     if (ca[x].touched() < ca[y].touched()) return true;
//     if (ca[x].touched() > ca[y].touched()) return false;

//     if(ca[x].lbd() > ca[y].lbd()) return true;
//     if(ca[x].lbd() < ca[y].lbd()) return false;

//     // Finally we can use old activity or size, we choose the last one

//      return ca[x].size() > ca[y].size();
//     }
// };

void Solver::reduceDB_Tier2() {
    sort(learnts_tier2, reduceTIER2_lt(ca));
    int i, j;
    int limit = learnts_tier2.size()/2;

    //  printf("\n conflicts: %llu, tier2: %d, \n", conflicts, learnts_tier2.size());
    for (i = j = 0; i < learnts_tier2.size(); i++){
        Clause& c = ca[learnts_tier2[i]];
        if (c.learnt() && c.mark() == TIER2) {
            assert(c.lbd() > 2);
            if (i < limit){
                learnts_local.push(learnts_tier2[i]);
                c.mark(LOCAL);
                //c.removable(true);
                c.activity() = 0;
                claBumpActivity(c);

                //	printf("i: %d, lbd: %d, touched: %u \n ", i, c.lbd(), c.touched());
            }else
                learnts_tier2[j++] = learnts_tier2[i];
        }
    }
    learnts_tier2.shrink(i - j);

    // printf("\ntier2: %d, last: %u, lastlbd: %d, core_lbd_cut: %d, core: %d\n",
    // 	  learnts_tier2.size(), ca[learnts_tier2.last()].touched(),
    // 	  ca[learnts_tier2.last()].lbd(), core_lbd_cut, learnts_core.size());
}

struct reduceCORE_lt {
    ClauseAllocator& ca;
    reduceCORE_lt(ClauseAllocator& ca_) : ca(ca_) {}
    bool operator () (CRef x, CRef y) {
        if(ca[x].lbd() > ca[y].lbd()) return true;
        if(ca[x].lbd() < ca[y].lbd()) return false;

        // Finally we can use old activity or size, we choose the last one

        return ca[x].size() > ca[y].size();
    }
};

void Solver::reduceDB_core()
{
    int     i, j;
    //if (local_learnts_dirty) cleanLearnts(learnts_local, LOCAL);
    //local_learnts_dirty = false;
    // printf("c caSize: %d, caWasted: %d (%4.3f), nbCORE: %d, nbTIER2: %d, conflicts: %llu, hardConfl: %llu\n",
    // 	   ca.size(), ca.wasted(), (float)ca.wasted()/ca.size(), learnts_core.size(), learnts_tier2.size(), conflicts, conflicts-softConflicts);

    sort(learnts_core, reduceCORE_lt(ca));

    int limit = learnts_core.size() / 2;
    //int totalLocalSize=0, removedSize=0;
    //int cut = (core_lbd_cut == 3) ? 3 : 4;

    // int meanSize;
    // for (i = 0; i < learnts_core.size(); i++){
    //   Clause& c = ca[learnts_core[i]];
    //   totalLocalSize += c.size();
    // }
    // if (i>0)
    //   meanSize = totalLocalSize/i;
    // else meanSize = 0;

    //  printf("\n conflicts: %llu, core: %d, \n", conflicts, learnts_core.size());
    for (i = j = 0; i < learnts_core.size(); i++){
        Clause& c = ca[learnts_core[i]];
        //	totalLocalSize += c.size();
        if (c.learnt() && c.mark() == CORE)
            if ( i < limit && c.lbd() > 2 && c.touched() + coreInactiveLimit < conflicts) {
                learnts_tier2.push(learnts_core[i]);
                c.mark(TIER2);

                //  printf("i: %d, lbd: %d, touched: %u\n", i, c.lbd(), c.touched());
            }
            else{
                // if (!c.removable()) limit++;
                //c.removable(true);
                learnts_core[j++] = learnts_core[i];
            }
    }
    learnts_core.shrink(i - j);
    // printf("c removedSize: %d(%4.2f), over totalCoreSize: %d (%4.2f), NBremoved: %d, over nbCoreBefore: %d\n",
    // 	   removedSize, (float)removedSize/(i-j> 0 ? i-j : 1), totalLocalSize, (float)totalLocalSize/i, i-j, i);
    // printf("c %d ca size: %d, ca wasted: %d (%4.3f)\n\n",
    // 	   nbClauseReduce, ca.size(), ca.wasted(), (float)ca.wasted()/ca.size());

    // printf("core: %d, last: %u, lastlbd: %d, core_lbd_cut: %d\n\n",
    // 	  learnts_core.size(), ca[learnts_core.last()].touched(),
    // 	      ca[learnts_core.last()].lbd(), core_lbd_cut);
}


void Solver::removeSatisfied(vec<CRef>& cs)
{
    int i, j;
    for (i = j = 0; i < cs.size(); i++){
        Clause& c = ca[cs[i]];
        if(c.mark()!=1){
            if (satisfied(c))
                removeClause(cs[i]);
            else
                cs[j++] = cs[i];
        }
    }
    cs.shrink(i - j);
}

void Solver::safeRemoveSatisfied(vec<CRef>& cs, unsigned valid_mark)
{
    int i, j;
    for (i = j = 0; i < cs.size(); i++){
        Clause& c = ca[cs[i]];
        if (c.mark() == valid_mark)
            if (satisfied(c))
                removeClause(cs[i]);
            else
                cs[j++] = cs[i];
    }
    cs.shrink(i - j);
}

void Solver::rebuildOrderHeap()
{
    vec<Var> vs;
    for (Var v = 0; v < nVars(); v++)
        if (decision[v] && value(v) == l_Undef)
            vs.push(v);

    order_heap_CHB  .build(vs);
    order_heap_VSIDS.build(vs);
    order_heap_distance.build(vs);

    vs.clear();
    for (int i = 0; i < nSoftLits; i++) {
        Var v = var(allSoftLits[i]);
        if (value(v) == l_Undef)
            vs.push(v);
    }
    orderHeapAuxi.build(vs);

}




/*_________________________________________________________________________________________________
 |
 |  simplify : [void]  ->  [bool]
 |
 |  Description:
 |    Simplify the clause database according to the current top-level assigment. Currently, the only
 |    thing done here is the removal of satisfied clauses, but more things can be put here.
 |________________________________________________________________________________________________@*/
bool Solver::simplify(bool simplifyOriginal)
{
    assert(decisionLevel() == 0);

    if (!ok || propagate() != CRef_Undef)
        return ok = false;

    if (nAssigns() == simpDB_assigns || (simpDB_props > 0))
        return true;

    // Remove satisfied clauses:
    removeSatisfied(learnts_core); // Should clean core first.
    safeRemoveSatisfied(learnts_tier2, TIER2);
    safeRemoveSatisfied(learnts_local, LOCAL);
    if (simplifyOriginal)        // Can be turned off.
        removeSatisfied(clauses);
    //  removeSoftSatisfied(softClauses);
    checkGarbage();
    rebuildOrderHeap();

    simpDB_assigns = nAssigns();
    simpDB_props   = clauses_literals + learnts_literals;   // (shouldn't depend on stats really, but it will do for now)

    return true;
}

// pathCs[k] is the number of variables assigned at level k,
// it is initialized to 0 at the begining and reset to 0 after the function execution
bool Solver::collectFirstUIP(CRef confl){
    // for(int i = 0; i<=decisionLevel(); i++)
    //   assert(pathCs[i] == 0);
    // for(int i=0; i<trail.size(); i++)
    //   if (level(var(trail[i])) > 0)
    //     assert(seen[var(trail[i])] == 0);
    //  counter++; vec<Var> myVars, myVars2; myVars.clear(), myVars2.clear();

    involved_lits.clear();
    int max_level=1;
    Clause& c=ca[confl]; int minLevel=decisionLevel();
    for(int i=0; i<c.size(); i++) {
        Var v=var(c[i]);
        //        assert(!seen[v]);
        if (level(v)>0) {
            seen[v]=1;
            var_iLevel_tmp[v]=1;
            pathCs[level(v)]++;

            // if (level(v) == 40  && conflicts == 458) {
            //   seen2[v]=counter; myVars.push(v); }

            if (minLevel>level(v)) {
                minLevel=level(v);
                assert(minLevel>0);
            }
            //    varBumpActivity(v);
        }
    }
    int limit=trail_lim[minLevel-1];
    for(int i=trail.size()-1; i>=limit; i--) {
        Lit p=trail[i]; Var v=var(p);
        if (seen[v]) {
            int currentDecLevel=level(v);
            //      if (currentDecLevel==decisionLevel())
            //      	varBumpActivity(v);
            seen[v]=0;
            if (--pathCs[currentDecLevel]!=0) {

                // if (currentDecLevel == 40 && conflicts == 458)
                // 	myVars2.push(v);

                // if (currentDecLevel == 40 && pathCs[currentDecLevel] == 1 && conflicts == 458) {
                // 	for(int ii=0; ii<i; ii++)
                // 	  if (seen2[var(trail[ii])] == counter)
                // 	    printf("**** ii: %d v: %d****\n", ii, var(trail[ii]));
                // 	for(int ii=0; ii<myVars.size(); ii++)
                // 	  printf("*%d %d*", myVars[ii], level(myVars[ii]));
                // 	printf("\n nb vars: %d\n\n", myVars.size());

                // 	for(int ii=0; ii<myVars2.size(); ii++)
                // 	  printf("*%d %d*", myVars2[ii], level(myVars2[ii]));
                // 	printf("\n nb vars2: %d\n\n", myVars2.size());

                // 	assert(myVars2.size() == myVars.size());
                // }

                Clause& rc=ca[reason(v)];
                int reasonVarLevel=var_iLevel_tmp[v]+1;
                if(reasonVarLevel>max_level) max_level=reasonVarLevel;
                if (rc.size()==2 && value(rc[0])==l_False) {
                    // Special case for binary clauses
                    // The first one has to be SAT
                    assert(value(rc[1]) != l_False);
                    Lit tmp = rc[0];
                    rc[0] =  rc[1], rc[1] = tmp;
                }
                for (int j = 1; j < rc.size(); j++){
                    Lit q = rc[j]; Var v1=var(q);
                    if (level(v1) > 0) {
                        if (minLevel>level(v1)) {
                            minLevel=level(v1); limit=trail_lim[minLevel-1]; 	assert(minLevel>0);
                        }
                        if (seen[v1]) {
                            if (var_iLevel_tmp[v1]<reasonVarLevel)
                                var_iLevel_tmp[v1]=reasonVarLevel;
                        }
                        else {
                            var_iLevel_tmp[v1]=reasonVarLevel;
                            //   varBumpActivity(v1);
                            seen[v1] = 1;
                            pathCs[level(v1)]++;

                            // if (level(v1) == 40  && conflicts == 458) {
                            //   seen2[v1]=counter; myVars.push(v1); }

                        }
                    }
                }
            }
            involved_lits.push(p);
        }
    }
    double inc=var_iLevel_inc;
    vec<int> level_incs; level_incs.clear();
    for(int i=0;i<max_level;i++){
        level_incs.push(inc);
        inc = inc/my_var_decay;
    }

    for(int i=0;i<involved_lits.size();i++){
        Var v =var(involved_lits[i]);
        //        double old_act=activity_distance[v];
        //        activity_distance[v] +=var_iLevel_inc * var_iLevel_tmp[v];
        activity_distance[v]+=var_iLevel_tmp[v]*level_incs[var_iLevel_tmp[v]-1];

        if(activity_distance[v]>1e100){
            for(int vv=0;vv<nVars();vv++)
                activity_distance[vv] *= 1e-100;
            var_iLevel_inc*=1e-100;
            for(int j=0; j<max_level; j++) level_incs[j]*=1e-100;
        }
        if (order_heap_distance.inHeap(v))
            order_heap_distance.decrease(v);

        //        var_iLevel_inc *= (1 / my_var_decay);
    }
    var_iLevel_inc=level_incs[level_incs.size()-1];
    return true;
}

CRef Solver::lPropagate() {
    CRef confl =  propagate();
#ifndef FLAG_NO_HARDEN
    while (confl == CRef_Undef && !softConflictFlag && harden())
        confl =  propagate();
#endif

    return confl;
}

int Solver::setCounter(CRef cr) {
    int j, k;
    Clause& c=ca[cr];
    counter++;
    for(j=0, k=0; j<c.size(); j++) {
        if (value(c[j]) == l_Undef) {
            seen2[toInt(c[j])] = counter;
            c[k++] = c[j];
        }
    }
    c.shrink(j-k);
    return k;
}

// return the number of literals whose seen2 is equal to counter, i.e. in the previous intersection.
// The seen2 of these literals are incremented for the next iterations
// nb is the number of literals in the new intersection whose seen2 is equal tp the new counter
int Solver::countCommunLiterals(CRef cr) {
    int i, j, nb=0;
    Clause& c=ca[cr];
    for(i=0,j=0; i<c.size(); i++) {
        if (value(c[i]) == l_Undef) {
            if (seen2[toInt(c[i])] == counter) {
                seen2[toInt(c[i])]++;
                nb++;
            }
            c[j++] = c[i];
        }
        else assert(i>1);
    }
    c.shrink(i-j);
    counter++;
    return nb;
}


void Solver::splitClauses(vec<CRef>& cs) {
    vec<Lit> communLits;
    communLits.clear();
    CRef cr=cs[0];
    Clause& c=ca[cr];
    int lbd = c.lbd();
    for(int i=0; i<c.size(); i++)
        if (seen2[toInt(c[i])] == counter) {
            communLits.push(c[i]);
        }
    Var v = newAuxiVar();
    Lit p = mkLit(v);

    int a, b, clauseType = LOCAL;
    bool toAttache;
    for(int i=0; i<cs.size(); i++) {
        CRef cr1=cs[i];
        Clause& c1 = ca[cr1];
        if (lbd > c1.lbd()) lbd = c1.lbd();
        assert(c1.mark() != 1);
        if (c1.mark() == CORE)
            clauseType = CORE;
        else if (c1.mark() == TIER2 && clauseType == LOCAL)
            clauseType = TIER2;

        if (seen2[toInt(c1[0])] == counter || seen2[toInt(c1[1])] == counter) {
            detachClause(cr1, true); toAttache=true;
        }
        else toAttache=false;

        //   detachClause(cr1, true);
        // int k=0;
        // for(a=0; a<c1.size(); a++) {
        //   if (seen2[toInt(c1[a])] == counter)
        // 	k++;
        // }
        // if (communLits.size() != k) {
        //   for(int aa=0; aa<c1.size(); aa++)
        // 	if (seen2[toInt(c1[aa])] == counter)
        // 	  printf("%d %llu, ", toInt(c1[aa]), seen2[toInt(c1[aa])]);
        //   printf("\n");
        //   for(int aa=0; aa<communLits.size(); aa++)
        // 	printf("%d %llu, ", toInt(communLits[aa]), seen2[toInt(communLits[aa])]);
        //   printf("****%d %d %d %d, ****\n\n", communLits.size(), k, i, cs.size());
        // }

        int k=0;
        for(a=0, b=0; a<c1.size(); a++) {
            if (seen2[toInt(c1[a])] == counter) {
                k++;
            }
            else c1[b++] = c1[a];
        }
        assert(communLits.size() == k);
        assert(b<c1.size() && a>b && a == c1.size());

        c1[b++] = ~p;
        c1.shrink(a-b);
        if (b<=1)
            printf("%d, %d, %d, %d, %d\n", b, k, communLits.size(), cs.size(), i);
        assert(b>1);
        if (toAttache)
            attachClause(cr1);
    }

    communLits.push(p);
    CRef cr2 = ca.alloc(communLits, true);
    attachClause(cr2); ca[cr2].mark(clauseType); ca[cr2].set_lbd(lbd);
    if (clauseType == CORE) {
        learnts_core.push(cr2); ca[cr2].touched() = conflicts;
    }
    else if (clauseType == TIER2) {
        learnts_tier2.push(cr2);  ca[cr2].touched() = conflicts;
    }
    else {
        learnts_local.push(cr2); claBumpActivity(ca[cr2]);
    }
    watches.cleanAll();
    watches_bin.cleanAll();

    nbSavedLits += cs.size() * (communLits.size() - 1) - (communLits.size() + 1);
    // printf("communLits: %d, nbCls: %d\n", communLits.size()-1, cs.size());
}

#define splitClauseSize 20
#define limitOfNbClausesToSplit 4

void Solver::identifyClausesToSplit(vec<CRef>& cs) {
    int i=0, j;
    vec<CRef> toSplit;

    removeSatisfied(cs);

    while (i<cs.size()) {
        CRef cr=cs[i];
        if (ca[cr].size() < splitClauseSize) {
            i++;
            continue;
        }
        toSplit.clear();
        int nbCommunLits = setCounter(cr), minSize=ca[cr].size();
        toSplit.push(cr);
        for(j=i+1; j<cs.size() && 2*nbCommunLits >= UB; j++) {
            CRef cr1 = cs[j];
            int oldMinSize = minSize, oldnbCommunLits = nbCommunLits;
            if (ca[cr1].size() < splitClauseSize)
                continue;
            if (ca[cr1].size() < minSize)
                minSize = ca[cr1].size();
            // intersection
            nbCommunLits = countCommunLiterals(cr1);
            if (nbCommunLits == ca[cr1].size()) {
                //	printf("removed %d clauses\n", toSplit.size());
                for(int a=0; a<toSplit.size(); a++)
                    removeClause(toSplit[a]);
                toSplit.clear();
                break;
            }
            else if (nbCommunLits == ca[cr].size()) {
                removeClause(cr1);
                continue;
            }
            if ( 2*nbCommunLits >= minSize )
                toSplit.push(cr1);
            else {
                //remove the last intersection
                Clause& c=ca[cr1];
                for(int a=0; a<c.size(); a++) {
                    if (seen2[toInt(c[a])] == counter)
                        seen2[toInt(c[a])]--;
                }
                counter--;
                minSize = oldMinSize; nbCommunLits = oldnbCommunLits;
                break;
            }
        }
        i=j;
        //|| (toSplit.size()>1 && nbCommunLits +1 == minSize))
        if (toSplit.size()>limitOfNbClausesToSplit)
            splitClauses(toSplit);
        // printf("communLits: %d, nbCls: %d, minSize: %d, Leanrts %d\n",
        //	   nbCommunLits, toSplit.size(), minSize, cs.size());
    }
    // printf(" ----------------- starts: %llu, UB: %llu\n", starts, UB);
}

void Solver::hardenForRestart() {
	/*for(int idx=hardenIndex.size()>0 ? hardenIndex.last() : 0; idx<nSoftLits; idx++) {
		Lit p=softLitsWeightOrder[idx];
		if(weights[var(p)]+countedWeight+rootConflCost<UB)
			break;
		else if (value(p) == l_Undef) {
			uncheckedEnqueue(p);
			fixedByHardens++; fixedByQuasiConfl++;
		}
	}*/
}

void Solver::simplelookback(CRef confl, Var falseVar, vec<Lit>& lits, vec<Lit>& out_learnt) {
    int pathC=0;
    out_learnt.clear(); lits.clear();
    if (confl == CRef_Bin) {
        assert(level(var(binConfl[0])) > decisionLevel());
        assert(level(var(binConfl[1])) > decisionLevel());
        seen[var(binConfl[0])] = 1; seen[var(binConfl[1])] = 1;  pathC = 2;
    }
    else {
        Clause& c = ca[confl];
        if (falseVar != var_Undef) {
            if (c.size() == 2 && value(c[0]) == l_False) {
                // Special case for binary clauses: the first one has to be SAT
                assert(value(c[1]) == l_True);
                Lit tmp = c[0];
                c[0] = c[1]; c[1]=tmp;
            }
            assert(!seen[falseVar] && level(falseVar) > decisionLevel());
            out_learnt.push(~softLits[falseVar]); lits.push(~softLits[falseVar]);
        }
        for(int i=(falseVar == var_Undef ? 0 : 1); i<c.size(); i++) {
            Lit q=c[i]; Var v = var(q);
            if (level(v) > 0 && !seen[v]) {
                seen[v]=1;
                if (level(v) > decisionLevel())
                    pathC++;
            }
        }
    }
    int index = trail.size() - 1;
    while (index >= trailRecord) {
        Lit p = trail[index--]; Var v = var(p);
        if (seen[v]) {
            seen[v] = 0; pathC--;
            confl = reason(v);
            if (pathC == 0 && falseVar == var_Undef && lits.size() == 0) {
                out_learnt.push(~p);
                for(index = trail.size() - 1; index >= trailRecord; index--) {
                    Lit q = trail[index]; Var vv = var(q);
                    assert(!seen[vv]);
                    assigns[vv] = l_Undef;
                    if (auxiVar(vv))
                        insertAuxiVarOrder(vv);
                }
                qhead = trailRecord;
                trail.shrink(trail.size() - trailRecord);
                return;
            }
            if (confl == CRef_Undef) {
                lits.push(~p); out_learnt.push(~p);
            }
            else {
                Clause& rc = ca[confl];
                // Special case for binary clauses: the first one has to be SAT
                if (rc.size() == 2 && value(rc[0]) == l_False) {
                    assert(value(rc[1]) == l_True);
                    Lit tmp = rc[0];
                    rc[0] = rc[1], rc[1] = tmp;
                }
                for (int j = 1; j < rc.size(); j++){
                    Lit q = rc[j]; Var vv=var(q);
                    if (level(vv) > 0 && !seen[vv]) {
                        seen[vv] = 1;
                        if (level(vv) > decisionLevel())
                            pathC++;
                    }
                }
            }
        }
    }
}

//TODO: must be fixed if maxresolution inference is used
void Solver::removeIsetsOfLit(Lit p){
    assert(auxiLit(p) && value(p)==l_False);
    Var v = var(p);
    assert(laConflictCost>=weightsBckp[v]-weights[v]);
    laConflictCost-=weightsBckp[v]-weights[v];
    vec<int> coresToIncrease;
    for(int i = 0; i < coresOfVar[v].size(); ++i){
        int iset = coresOfVar[v][i];
        assert(iset<localCores.size());
        if(localCores[iset].weight>0){ //Avoid revisiting if the iset was desactivated by another lit
            vec<Lit> & lits = localCores[iset].lits;
            for(int j = 0; j < lits.size(); ++j){
                Lit pp = lits[j]; Var vv = var(pp);
                assert(v==vv || value(pp)!=l_False);
                if(weights[vv]==0){
                    for(int k = 0; k < coresOfVar[vv].size(); k++){
                        int core = coresOfVar[vv][k];
                        assert(core<localCores.size());
                        if(!localCores[core].toUpdate) {
                            coresToIncrease.push(core);
                            localCores[core].toUpdate=true;
                        }
                    }
                }
                weights[vv]+=localCores[iset].weight;
                assert(weights[vv]<=weightsBckp[vv]);
                hardenHeap.update(vv);
                if(value(pp)==l_Undef){

                    //if(weights[vv]==0)
                    //    restoredLitFlag=true;
                    insertAuxiVarOrder(vv);
                    lastConflLits.push(pp);
                }
            }
            localCores[iset].weight=0;
        }
    }
    for(int i = 0; i < coresToIncrease.size(); i++){
        int core = coresToIncrease[i];
        if(localCores[core].weight>0)
            updateCore(core);
        localCores[core].toUpdate=false;
    }
    coresOfVar[v].clear();
    assert(weights[v]==weightsBckp[v]);
}




void Solver::setConflictForRestart(int& nbIsets) {
//Not used, to implement if needed
	assert(0);
}

void Solver::resetConflictsForRestart(int nbIsets, bool clearConflLits, bool pushConflLit) {
//Not used, to implement if needed
	assert(0);
}


int Solver::lookaheadForRestart() {
//Not used, to implement if needed
	assert(0);
}

int64_t Solver::lookaheadComputeInitLB() {
	//Not used, to implement if needed
	assert(0);
	return rootConflCost;
}


double Solver::avgAct(vec<CRef>& cs, int& nb0) {
    double act=0;
    nb0=0;
    for(int i=0; i<cs.size(); i++) {
        if (ca[cs[i]].activity() == 0)
            nb0++;
        else act += ca[cs[i]].activity();
    }
    if (act>0)
        return act/cs.size();
    else return 0;
}

/*_________________________________________________________________________________________________
 |
 |  search : (nof_conflicts : int) (params : const SearchParams&)  ->  [lbool]
 |
 |  Description:
 |    Search for a model the specified number of conflicts.
 |
 |  Output:
 |    'l_True' if a partial assigment that is consistent with respect to the clauseset is found. If
 |    all variables are decision variables, this means that the clause set is satisfiable. 'l_False'
 |    if the clause set is unsatisfiable. 'l_Undef' if the bound on number of conflicts is reached.
 |________________________________________________________________________________________________@*/
lbool Solver::search(int& nof_conflicts)
{

	static int noSattiime=0;
	static int sattimeWait=0;

#ifndef NDEBUG
    for(int i = 0; i < nSoftLits; i++)
        assert(!auxiLit(allSoftLits[i]) || value(allSoftLits[i])!=l_Undef||hardenHeap.inHeap(var(allSoftLits[i])));
#endif

    assert(ok);
    int         backtrack_level;
    int lbd;
    vec<Lit>    learnt_clause;
    bool        cached = false;

    static int64_t prevUB=0;
    starts++;


    assert(hardens.size()==0);

    // if (prevUB != UB && PBC.size()>0) {

    //     for (int ci=0; ci < PBC.size(); ci++)
    //         removeClause(PBC[ci]);
    //     PBC.clear();
    //     CCPBadded=false;

    //     collectDynVars();

    //     watches.cleanAll();
    //     watches_bin.cleanAll();
    //     checkGarbage();
    // }

    if (lPropagate() != CRef_Undef || softConflictFlag){
    	conflicts++;
        return l_False;
    }



#ifndef FLAG_NO_ADDPB
    if (prevUB != UB && UB>1) {
        addPBConstraints();
        if (lPropagate() != CRef_Undef || softConflictFlag) {
            conflicts++;
            return l_False;
        }
    }
#endif


	if (subconflicts >= curSimplify * nbconfbeforesimplify){

		//int nbIsets=lookaheadForRestart();

        rootConflCost=0;
		bool toSimplify = qhead==trail.size();

		/*if (nbIsets==NON ||
			(qhead < trail.size() && (propagate() != CRef_Undef || softConflictFlag))) {
			if(nbIsets!=NON)
				resetConflictsForRestart(nbIsets,true,true);
			return l_False;
		}*/
		if (toSimplify) {
			nbSimplifyAll++;
			if (!simplifyAll()) {
				//resetConflictsForRestart(nbIsets,false,true);
				return l_False;
			}
			curSimplify = (subconflicts / nbconfbeforesimplify) + 1;
			nbconfbeforesimplify += incSimplify;
		}
		//resetConflictsForRestart(nbIsets,true,true);
	}

	if(prevUB<UB) {
		localCores.clear();
		lastCores.clear();
		freeCores.clear();
	}

    prevUB = UB;

    //hardenLevel = INT32_MAX;
    softLearnts.clear(); hardLearnts.clear();
    assert(laConflictCost==0);
    //assert(localCores.size()==0);
	assert(activeCores.size()==0);

    for (;;){
        CRef confl = lPropagate();
        if(confl == CRef_Undef && !softConflictFlag) {
            if(lookahead()){ //True iff lookahead was done and some propagation was done or LB was computed
                confl = LHconfl;
                if(confl==CRef_Undef && !softConflictFlag)
                    confl = lPropagate();
                if(activeCores.size()>0 && !softConflictFlag) {
                    resetConflicts();
                }
            }
        }
        if(confl!=CRef_Undef || softConflictFlag){

            if (LHconfl != CRef_Undef)
                la_conflicts++;

           /* if(confl==CRef_Undef){
                assert(softConflictFlag);
                registerLAsuccess();
            }*/

            // CONFLICT
            if (VSIDS){
                if (--timer == 0 && var_decay < 0.95) timer = 5000, var_decay += 0.01;
            }else
            if (step_size > min_step_size) step_size -= step_size_dec;

            conflicts++; nof_conflicts--; subconflicts++;

            if (softConflictFlag) {
				softConflicts++;
				if(countedWeight<UB) {
                    assert(countedWeight+laConflictCost>=UB);
                    la_softConflicts++;
                }
			}


            if (decisionLevel() == 0){
                if(activeCores.size()>0) {
                    resetConflicts();
                }
                UBconflictFlag=false; softConflictFlag=false;
                return l_False;
            }

            learnt_clause.clear();

            DISTANCE=0;

            softLearnt = false;
            if (softConflictFlag) {
                analyzeSoftConflict(learnt_clause, backtrack_level, lbd);
                if(activeCores.size()>0) {
                    resetConflicts();
                }
                UBconflictFlag=false; softConflictFlag=false;softLearnt = true;
            }
            else
                analyze(confl, learnt_clause, backtrack_level, lbd);

            cancelUntil(backtrack_level);

            if (backtrack_level == 0 && learnt_clause.size()==0) return l_False;

            lbd--;
            if (VSIDS){
                cached = false;
                conflicts_VSIDS++;
                lbd_queue.push(lbd);
                global_lbd_sum += (lbd > 50 ? 50 : lbd);
            }

            if (learnt_clause.size() == 1){
                uncheckedEnqueue(learnt_clause[0]);
            }else{
                CRef cr = ca.alloc(learnt_clause, true);
                if (learnt_clause.size() > splitClauseSize && lbd<=tier2_lbd_cut) {
                    if (softLearnt)
                        softLearnts.push(cr);
                    else  hardLearnts.push(cr);
                }
                ca[cr].set_lbd(lbd);
                if (lbd <= core_lbd_cut){
                    learnts_core.push(cr);
                    ca[cr].mark(CORE);
                    ca[cr].touched() = conflicts;
                }else if (lbd <= tier2_lbd_cut){
                    learnts_tier2.push(cr);
                    ca[cr].mark(TIER2);
                    ca[cr].touched() = conflicts;
                }else{
                    learnts_local.push(cr); }
                claBumpActivity(ca[cr]);
                attachClause(cr);
                uncheckedEnqueue(learnt_clause[0], cr);
            }
            if (drup_file){
#ifdef BIN_DRUP
                binDRUP('a', learnt_clause, drup_file);
#else
                for (int i = 0; i < learnt_clause.size(); i++)
                    fprintf(drup_file, "%i ", (var(learnt_clause[i]) + 1) * (-2 * sign(learnt_clause[i]) + 1));
                fprintf(drup_file, "0\n");
#endif
            }

            if (VSIDS) varDecayActivity();
            claDecayActivity();
            /*if (--learntsize_adjust_cnt == 0){
             learntsize_adjust_confl *= learntsize_adjust_inc;
             learntsize_adjust_cnt    = (int)learntsize_adjust_confl;
             max_learnts             *= learntsize_inc;

             if (verbosity >= 1)
             printf("c | %9d | %7d %8d %8d | %8d %8d %6.0f | %6.3f %% |\n",
             (int)conflicts,
             (int)dec_vars - (trail_lim.size() == 0 ? trail.size() : trail_lim[0]), nClauses(), (int)clauses_literals,
             (int)max_learnts, nLearnts(), (double)learnts_literals/nLearnts(), progressEstimate()*100);
             }*/

        }else{
            assert(countedWeight < UB);
            if (qhead < trail.size())
                continue;
            // NO CONFLICT
            bool restart = false;
            if (!VSIDS)
                restart = nof_conflicts <= 0;
            else if (!cached){
                restart = (lbd_queue.full() && (lbd_queue.avg() * 0.8 > global_lbd_sum / conflicts_VSIDS)) || (nof_conflicts <= 0);
                cached = true;
            }
            if (restart /*|| !withinBudget()*/){
                lbd_queue.clear();
                cached = false;
                // Reached bound on number of conflicts:
                progress_estimate = progressEstimate();

                cancelUntil(0);
                return l_Undef; }

            // Simplify the set of problem clauses:
            if (decisionLevel() == 0 && !simplify())
                return l_False;

            if (learnts_tier2.size() >= tier2Limit){
                // next_T2_reduce = subconflicts + 10000;
                //	next_T2_reduce = conflicts + 10000 + 300*nbClauseReduce;;
                reduceDB_Tier2(); }
            if (subconflicts >= next_L_reduce){
                next_L_reduce = subconflicts + 15000;
                //next_L_reduce = conflicts + 15000+300*nbClauseReduce;
                //nbClauseReduce++;
                reduceDB(); }

            if (learnts_core.size() >= coreLimit){
                //next_L_reduce = conflicts + 15000;
                coreLimit += coreLimit/10;
                nbClauseReduce++;
                reduceDB_core(); }

            Lit next = lit_Undef;
            /*while (decisionLevel() < assumptions.size()){
             // Perform user provided assumption:
             Lit p = assumptions[decisionLevel()];
             if (value(p) == l_True){
             // Dummy decision level:
             newDecisionLevel();
             }else if (value(p) == l_False){
             analyzeFinal(~p, conflict);
             return l_False;
             }else{
             next = p;
             break;
             }
             }

             if (next == lit_Undef)*/
            // New variable decision:
            decisions++;
            next = pickBranchLit();

            if (next == lit_Undef) {
                // better solution found
                feasible = true;
                assert(laConflictCost==0);
                assert(countedWeight < UB);
                int nbFixeds = trail_lim.size() == 0 ? 0 : trail_lim[0];
                int nbFalses = falseLits_lim.size() == 0 ? 0 : falseLits_lim[0];

                float meanLB=0, dev=0, succRate=0;
                if (nbLKsuccess>savednbLKsuccess) {
                    meanLB= (float)totalPrunedLB/(nbLKsuccess-savednbLKsuccess);
                    dev = sqrt((float)totalPrunedLB2/(nbLKsuccess-savednbLKsuccess) - meanLB*meanLB);
                }
                if (LOOKAHEAD > savedLOOKAHEAD)
                    succRate = (float) (nbLKsuccess-savednbLKsuccess)/(LOOKAHEAD-savedLOOKAHEAD);

                printf("c UB=%llu succs, sol=%llu, confls=%llu, hconfls=%llu, core %d, tier2 %d, local %d,  %d soft cls unsat (%d at L0), %d fixed vars at L0, softCnfl %d, nbFlyRd %d, nbFixedLH %llu\n",
                       UB, countedWeight, conflicts, conflicts-softConflicts, learnts_core.size(), learnts_tier2.size(), learnts_local.size(),
                       falseLits.size(), nbFalses, nbFixeds, pureSoftConfl, nbFlyReduced, nbFixedByLH);

                // printf("c nbHardens %d (fixed %llu), shorten: %llu, prunedLB %4.2f, dev %4.2f, succRate %4.2f, nbSucc %llu, lk: %llu, shorten: %llu, quasiC: %llu (fixed: %llu)\n\n",
                //        nbHardens, fixedByHardens, nbSavedLits, meanLB, dev, succRate, nbLKsuccess-savednbLKsuccess, LOOKAHEAD-savedLOOKAHEAD, nbSavedLits, quasiSoftConflicts, fixedByQuasiConfl);
                // totalPrunedLB=0; totalPrunedLB2=0; savedLOOKAHEAD = LOOKAHEAD; savednbLKsuccess=nbLKsuccess;
		printf("c nbHardens %d (fixed %llu), shorten: %llu, prunedLB %4.2f, dev %4.2f, succRate %4.2f, nbSucc %llu, lk: %llu\n\n",
                       nbHardens, fixedByHardens, nbSavedLits, meanLB, dev, succRate, nbLKsuccess-savednbLKsuccess, LOOKAHEAD-savedLOOKAHEAD);
		printf("c shorten: %llu, quasiC: %llu (fixed: %llu), myderivedCost %lld, fsblEq %d, nbEqUse %d\n\n",
		       nbSavedLits, quasiSoftConflicts, fixedByQuasiConfl, myDerivedCost,
		       feasibleNbEq, nbEqUse);
                totalPrunedLB=0; totalPrunedLB2=0; savedLOOKAHEAD = LOOKAHEAD; savednbLKsuccess=nbLKsuccess;

		extendEquivLitValue(0);
		
                UB = countedWeight;
                checkSolution();
                WithNewUB = true;
                //  printf("c UB=%llu at conflicts=%llu and hard conflicts=%llu\n",
                //     UB, conflicts, conflicts-softConflicts);
                printf("o %lld\n",solutionCost+UB+fixedCostBySearch+derivedCost);
                model.growTo(nbOrignalVars,l_Undef);
                for (int i = 0; i < nbOrignalVars; i++)
                    model[i] = value(i);

				assert(UB==0 || falseLits.size()>0);

                if (UB==0)
                    return l_True;
                else{
					if (level(var(falseLits.last()))==0)
						infeasibleUB=UB;
					if (infeasibleUB >= UB)
						return l_False;
				}
		
		cancelUntil(0);

                if (PBC.size()>0) {
                    for (int ci=0; ci < PBC.size(); ci++)
                        removeClause(PBC[ci]);
                    PBC.clear();
                    CCPBadded=false;

                    collectDynVars();

                    watches.cleanAll();
                    watches_bin.cleanAll();
                    checkGarbage();
                }

				printf("c Satttime wait=%d n=%d\n",sattimeWait,noSattiime);
				if(sattimeWait==noSattiime || equivLits.size() > prevEquivLitsNb) {

				  for (int i=0; i < learnts_local.size(); i++)
				    if (ca[learnts_local[i]].mark() == LOCAL)
				      removeClause(learnts_local[i]);
				  learnts_local.clear();
				  watches.cleanAll();
				  watches_bin.cleanAll();
				  checkGarbage();

				  int64_t savedUB=UB;
				  
				  if (sattime(1000000)) {
				    if (UB < savedUB) {
				      noSattiime = 0;

				      falseLitsRecord = falseLits.size(); trailRecord = trail.size();
				      countedWeightRecord=countedWeight;
				      satisfiedWeightRecord=satisfiedWeight;
				      
				      testedVars.clear(); 
                                      for (int v = 0; v < staticNbVars; v++) {
                                        if (assigns[v] == l_Undef) {
					  testedVars.push(v);
					  if (rpr[toInt(mkLit(v))]==lit_Undef) {
					    // model[v] = !polarity[v] ? l_True : l_False;    
					    assigns[v]=!polarity[v] ? l_True : l_False;
					  }
					}
                                      }
				      // if (conflicts==38534)
				      // 	printf("sdf ");
				      
                                      extendEquivLitValue(0);

				      model.growTo(nbOrignalVars);
                                      for (int v = 0; v < nbOrignalVars; v++) {
                                        model[v] = value(v);
                                      }

				      cancelUntilTrailRecord();
				      
				      for(int i=0; i<testedVars.size(); i++)
                                        assigns[testedVars[i]]=l_Undef;
                                      testedVars.clear();

				      // model.growTo(nbOrignalVars);
				      // for (int v = 0; v < nbOrignalVars; v++) {
				      // 	if (assigns[v] == l_Undef)
				      // 	  model[v] = !polarity[v] ? l_True : l_False;
				      // }
				    } else
				      noSattiime++;
				  }
				  else return l_False;
				  sattimeWait=0;
				}
				else
					sattimeWait++;

				if (UB==0)
					return l_True;
				else if (infeasibleUB >= UB)
					return l_False;

                return l_Undef;
                //cancelUntilUB();
            }
            else {
                // Increase decision level and enqueue 'next'
                newDecisionLevel();
                uncheckedEnqueue(next);
            }
        }
    }
}


double Solver::progressEstimate() const
{
    double  progress = 0;
    double  F = 1.0 / nVars();

    for (int i = 0; i <= decisionLevel(); i++){
        int beg = i == 0 ? 0 : trail_lim[i - 1];
        int end = i == decisionLevel() ? trail.size() : trail_lim[i];
        progress += pow(F, i) * (end - beg);
    }

    return progress / nVars();
}

/*
 Finite subsequences of the Luby-sequence:

 0: 1
 1: 1 1 2
 2: 1 1 2 1 1 2 4
 3: 1 1 2 1 1 2 4 1 1 2 1 1 2 4 8
 ...


 */

static double luby(double y, int x){

    // Find the finite subsequence that contains index 'x', and the
    // size of that subsequence:
    int size, seq;
    for (size = 1, seq = 0; size < x+1; seq++, size = 2*size+1);

    while (size-1 != x){
        size = (size-1)>>1;
        seq--;
        x = x % size;
    }

    return pow(y, seq);
}

bool Solver::uncheckedEnqueueForLK(Lit p, CRef from){
    assert(value(p) == l_Undef);
    Var v = var(p);
    assigns[v] = lbool(!sign(p)); // this makes a lbool object whose value is sign(p)
    // vardata[x] = mkVarData(from, decisionLevel());
    vardata[v].reason = from;
    vardata[v].level = decisionLevel() + 1;
    trail.push_(p);

    if(auxiVar(v)){
        if(from==CRef_Undef){
            assert(softLits[v]==p);
            //Mark its isets as non-unlockable
            /*for(int i=0; i<coresOfVar[v].size(); i++){
                int iset=coresOfVar[v][i];
                if(unlockableIset[iset]){
                    unlockableIset[iset]=false;
                    nonUnlockableIsets.push(iset);
                }
            }*/
        }
        else if(softLits[v]==~p){// a soft clause is falsified
            if(weights[v]>0)
                return false;
           /* else{
         //   	printf("c ENTER UNLOCK with size %d: ",coresOfVar[v].size());
                for(int i = 0; i < coresOfVar[v].size(); i++){
                    int is = coresOfVar[v][i];
                    assert(is < localCores.size());
                    if(unlockableIset[is] && isetUnlockingVar[is]==var_Undef){
                        isetUnlockingVar[is]=v;
                        unlockedIsets.push(is);
                        for(int j = 0; j < localCores[is].size(); j++){
                            Var w = var(localCores[is][j]);
                            assert(weights[w]<weightsBckp[w]);
                            if(value(w)==l_Undef){
                                lastConflLits.push(softLits[w]); //TODO: better here or to the heap?
                                weights[w]+=isetsWeights[is];
                                assert(weights[w]<=weightsBckp[w]);
                                if(unlockedIsetsOfVar[w].size()==0){
                                	unlockedVars.push(w);
                                }
                                unlockedIsetsOfVar[w].push(is);
                            }
                        }
                    }
                }
            }*/
        }
    }
    return true;
}

CRef Solver::propagateForLK() {
    falseVar = var_Undef;
    CRef    confl = CRef_Undef;
    int     num_props = 0;
    watches.cleanAll();
    watches_bin.cleanAll();
    while (qhead < trail.size()) {
        Lit            p = trail[qhead++];     // 'p' is enqueued fact to propagate.
        vec<Watcher>&  ws = watches[p];
        Watcher        *i, *j, *end;
        num_props++;
        // First, Propagate binary clauses
        vec<Watcher>&  wbin = watches_bin[p];

        for (int k = 0; k<wbin.size(); k++) {
            Lit imp = wbin[k].blocker;
            if (value(imp) == l_False) {
                    binConfl[0] = ~p;
                    binConfl[1] = imp;
                    return CRef_Bin;
            }
            if (value(imp) == l_Undef) {
                if (!uncheckedEnqueueForLK(imp, wbin[k].cref)) {
                    falseVar = var(imp);
                    return CRef_Undef;
                }
            }
        }
        for (i = j = (Watcher*)ws, end = i + ws.size(); i != end;) {
            // Try to avoid inspecting the clause:
            Lit blocker = i->blocker;
            if (value(blocker) == l_True) {
                *j++ = *i++; continue;
            }
            // Make sure the false literal is data[1]:
            CRef     cr = i->cref;
            Clause&  c = ca[cr];
            Lit      false_lit = ~p;
            if (c[0] == false_lit)
                c[0] = c[1], c[1] = false_lit;
            assert(c[1] == false_lit);
            // If 0th watch is true, then clause is already satisfied.
            // However, 0th watch is not the blocker, make it blocker using a new watcher w
            // why not simply do i->blocker=first in this case?
            Lit     first = c[0];
            //  Watcher w     = Watcher(cr, first);
            if (first != blocker && value(first) == l_True){
                i->blocker = first;
                *j++ = *i++; continue;
            }
            assert(c.lastPoint() >=2);
            if (c.lastPoint() > c.size())
                c.setLastPoint(2);
            for (int k = c.lastPoint(); k < c.size(); k++) {
                if (value(c[k]) == l_Undef) {
                    // watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
                    // the blocker is first in the watcher. However,
                    // the blocker in the corresponding watcher in ~first is not c[1]
                    Watcher w = Watcher(cr, first); i++;
                    c[1] = c[k]; c[k] = false_lit;
                    watches[~c[1]].push(w);
                    c.setLastPoint(k+1);
                    goto NextClause;
                }
                else if (value(c[k]) == l_True) {
                    i->blocker = c[k];  *j++ = *i++;
                    c.setLastPoint(k);
                    goto NextClause;
                }
            }
            for (int k = 2; k < c.lastPoint(); k++) {
                if (value(c[k]) ==  l_Undef) {
                    // watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
                    // the blocker is first in the watcher. However,
                    // the blocker in the corresponding watcher in ~first is not c[1]
                    Watcher w = Watcher(cr, first); i++;
                    c[1] = c[k]; c[k] = false_lit;
                    watches[~c[1]].push(w);
                    c.setLastPoint(k+1);
                    goto NextClause;
                }
                else if (value(c[k]) == l_True) {
                    i->blocker = c[k];  *j++ = *i++;
                    c.setLastPoint(k);
                    goto NextClause;
                }
            }
            // Did not find watch -- clause is unit under assignment:
            i->blocker = first;
            *j++ = *i++;
            if (value(first) == l_False) {
                confl = cr;
                qhead = trail.size();
                // Copy the remaining watches:
                while (i < end)
                    *j++ = *i++;
            }
            else {
                if (!uncheckedEnqueueForLK(first, cr)) {
                    qhead = trail.size();
                    // Copy the remaining watches:
                    while (i < end)
                        *j++ = *i++;
                    falseVar = var(first);
                }
            }
            NextClause:;
        }
        ws.shrink(i - j);
        // if (confl == CRef_Undef)
        // 	if (shortenSoftClauses(p))
        // 	  break;
    }
    lk_propagations += num_props;
    return confl;
}

int Solver::seeUnlockLits(int unlockedVar, int64_t costToReach) {
	//Since the cost is split, not all isets might end up being used, only the ones required to reach the cost!
	//Therefore we might be able to spare some sets.
	//Strategy: at first pass, take the ones already seen.
	//At second pass, select the isets until cost is completed

/*	vec<int> & visets = unlockedIsetsOfVar[unlockedVar];

  int nbfalse=0, j=0;
  int64_t reachedCost = 0;
  for(int i=0, j=0; i<visets.size() && reachedCost<costToReach; i++) {
	  Var v = isetUnlockingVar[visets[i]];
	  if(seen[v]){
		  int aux = visets[i];
		  visets[i]=visets[j];
		  visets[j++]=aux;
		  reachedCost+=isetsWeights[aux];
	  }
  }
  while(j<visets.size() && reachedCost<costToReach){
	  Var v = isetUnlockingVar[visets[j]];
	  assert(v!=var_Undef);
	  assert(value(softLits[v])==l_False);
	  if(!seen[v]){
		  seen[v]=1;
		  nbfalse++;
	  }
	  reachedCost+=isetsWeights[visets[j]];
	  j++;
  }
  return nbfalse;*/
return 0;
}


int64_t Solver::lookbackGetMinIsetCost(CRef confl, Var falseVar) {
	int64_t minISetCost = INT64_MAX;
	if(falseVar != var_Undef) {
        assert(weights[falseVar]>0);
        minISetCost = weights[falseVar];
    }

	if (confl == CRef_Bin) {
		assert(level(var(binConfl[0])) > decisionLevel());
		assert(level(var(binConfl[1])) > decisionLevel());
		seen[var(binConfl[0])] = 1; seen[var(binConfl[1])] = 1;
	}
	else {
		Clause& c = ca[confl];
		if (falseVar != var_Undef) {
			fixBinClauseOrder(c);
			assert(!seen[falseVar] && level(falseVar) > decisionLevel());
		}
		for(int i=(falseVar == var_Undef ? 0 : 1); i<c.size(); i++) {
			Lit q=c[i]; Var v = var(q);
			if (level(v) > decisionLevel())
				seen[v]=1;
		}
	}
	int index = trail.size() - 1;
	while (index >= trailRecord) {
		Lit p = trail[index--];
		Var v = var(p);
		if (seen[v]) {
			seen[v] = 0;
			confl = reason(v);

			if(confl == CRef_Undef){
				assert(nonLockedAuxiLit(p));
				if(weights[v]<minISetCost) {
                    assert(weights[v]>0);
                    minISetCost = weights[v];
                }
			}
			else {
				Clause &rc = ca[confl];
                if(!auxiVar(v) || !hardened[v])
				    fixBinClauseOrder(rc);
				int nbSeen = 0;
				for (int j = 1; j < rc.size(); j++) {
					Lit q = rc[j];
					Var vv = var(q);
					if (level(vv) > decisionLevel())
						seen[vv] = 1;
				}
			}
		}
	}
	return minISetCost;
}


//out_learnt stores all literals of smaller DL involved with the LA conflict, as well as the false var if any
//the list is used to unsee the literals when finished
//also, if the iset size after looking at the IG is 0, out_learnt contains the needed info for fixByLookahead
void Solver::lookbackResetTrail(CRef confl, Var falseVar, vec<Lit>& out_learnt, int coreidx, int64_t & minISetCost, bool resDone, int64_t remainingCost) {
    int pathC=0;
    out_learnt.clear();
    out_learnt.push();
    LocalCore & core = localCores[coreidx];
    int64_t newMinCost = INT64_MAX; //This is used in case of earlier exit of lookback


    if (confl == CRef_Bin) {
        assert(level(var(binConfl[0])) > decisionLevel());
        assert(level(var(binConfl[1])) > decisionLevel());
        seen[var(binConfl[0])] = 1; seen[var(binConfl[1])] = 1;  pathC = 2;
        if (VSIDS) {
            varBumpActivity(var(binConfl[0]), .1);
            varBumpActivity(var(binConfl[0]), .1);
        }
    }
    else {
        Clause& c = ca[confl];
        if (falseVar != var_Undef) {
			assert(weights[falseVar]>=minISetCost);
			core.lits.push(softLits[falseVar]);
            fixBinClauseOrder(c);
            if(weights[falseVar]<newMinCost)
                newMinCost=weights[falseVar];
            //if (unlockedIsetsOfVar[falseVar].size()>0)
            //	pathC += seeUnlockLits(falseVar,minISetCost);

            assert(!seen[falseVar] && level(falseVar) > decisionLevel());
            out_learnt.push(softLits[falseVar]);
        }
        for(int i=(falseVar == var_Undef ? 0 : 1); i<c.size(); i++) {
            Lit q=c[i]; Var v = var(q);
            if (level(v) > 0) {
                if (!seen[v]) {
                assert(!seen[v]);
                    seen[v]=1;
                    if (level(v) > decisionLevel())
                        pathC++;
                    else {
                        //Note that involvedLits can contain lits from other isets
                        //This is not the case for out_learnt
                        out_learnt.push(q);
						core.reasons.push(q);
                    }
                    if (VSIDS)
                        varBumpActivity(v, .1);
                }
            }
        }
    }
    int index = trail.size() - 1;
    while (index >= trailRecord) {
        Lit p = trail[index--];
        Var v = var(p);
        if (seen[v]) {
            seen[v] = 0; pathC--;
            confl = reason(v);


            //We will need to keep this decrease only if confl==CRef_Undef,
            //  unless we enter the following special case, where it is accepted to use a propagated softLit (i.e. confl!=CRef_Undef)
            //  for the iset in replacement


            //If UIP is reached: pathC==0.
            //And the iset is empty until now: localCores[nbIsets].size() == 0
            //And
            //      is not the last iset (i.e. the one triggering the soft conflict): minIsetCost < remainingCost
            //      or the recently visited lit is soft, and therefore the unique soft lit to be included in the iset

            if (pathC == 0 && core.lits.size() == 0 && core.softCl.size()==0 &&
				(minISetCost < remainingCost|| (nonLockedAuxiLit(p) && /*unlockedIsetsOfVar[v].size()==0 &&*/ weights[v]>=minISetCost) )
            )
            {
                out_learnt[0] = ~p; assigns[v] = l_Undef;

                if(nonLockedAuxiLit(p) && weights[v] < newMinCost)
                    newMinCost=weights[v];

                //If creating the unit iset will trigger the soft conflict, do it.
                    // This branch can be seen as a premature exit of the loop, since we already know that pathC==0
                //Otherwise, we exit with an empty iset and p will be propagated by fixByLookahead
                //Note that here p is not necessarily a manually assigned softLit for LA but can be a propagated one.
                //  In this case it acts in replacement and takes it place in the iset
                if (nonLockedAuxiLit(p) && newMinCost >= remainingCost) {
					minISetCost=newMinCost;
                    core.lits.push(p);
				}
                if (auxiVar(v))
                    insertAuxiVarOrder(v);
                for(; index >= trailRecord; index--) {
                    Lit q = trail[index];
                    Var vv = var(q);
                    assert(!seen[vv]);
                    assigns[vv] = l_Undef;
                    if (auxiVar(vv))
                        insertAuxiVarOrder(vv);
                }
                break;
            }
            if (confl == CRef_Undef) { //Propagated soft literal for LA
                assert(nonLockedAuxiLit(p));
				core.lits.push(p);
				out_learnt.push(~p);
				assert(minISetCost<=weights[v]);
                if(weights[v]<newMinCost)
                    newMinCost=weights[v];
				//If v has been unlocked, we need to see the literal 'y' that unlocked its iset (for each unlocked iset),
				//Since we need to include in the new core and reasons all literals x1 .. xn
				//that triggered x1 /\ ... /\ xn ->(UP) ~y. The lookback process will then see x1 .. xn
				//if (unlockedIsetsOfVar[v].size() > 0)
				//	pathC += seeUnlockLits(v, minISetCost);
            }
            else {
                //Undo the minimum for a softLit p s.t. reason(p)!=CRef_Undef, and therefore is not put in isets
                if (auxiVar(v))
                    insertAuxiVarOrder(v);



                Clause &rc = ca[confl];
                if(!auxiVar(v) || !hardened[v])
                    fixBinClauseOrder(rc);
                int nbSeen = 0;
                int resolventSize = pathC + out_learnt.size();
                for (int j = 1; j < rc.size(); j++) {
                    Lit q = rc[j];
                    Var vv = var(q);
                    if (level(vv) > 0) {
                        if (seen[vv])
                            nbSeen++;
                        else {
                            seen[vv] = 1;
                            if (level(vv) > decisionLevel())
                                pathC++;
                            else {
                                out_learnt.push(q);
								core.reasons.push(q);
                            }
                            if (VSIDS)
                                varBumpActivity(vv, .1);
                        }
                    }
                }
                if (!resDone && nbSeen >= resolventSize) {
                    assert(falseVar == var_Undef);
                    reduceClause(confl, pathC);
                }
            }
        }
        else if (nonLockedAuxiVar(v))
            insertAuxiVarOrder(v);
        assigns[v] = l_Undef;
    }
    qhead = trailRecord;
    trail.shrink(trail.size() - trailRecord);

    assert((core.lits.size()==0 && core.softCl.size()== 0) || newMinCost==minISetCost);

	int lvl=0;
    for(int i=0; i<core.reasons.size(); i++) {
		Var v = var(core.reasons[i]);
		if(level(v)>lvl)
			lvl= level(v);
		seen[v] = 0;
	}
	core.level=lvl;
}

void Solver::bumpConflVars() {
    for(int i=0; i<conflLits.size(); i++) {
        if (conflLits[i] != lit_Undef) {
            Var v = var(conflLits[i]);
            assert(v>=0 && v<activityLB.size());
            double oldAct = activityLB[v];
            // the two equations are equivalent, but the practical precision is different
            // activityLB[v] = stepSizeLB + (1-stepSizeLB)*oldAct;
            activityLB[v] = oldAct + (1-oldAct)*stepSizeLB;
            insertAuxiVarOrder(v);
            assert(activityLB[v] >= oldAct);
            orderHeapAuxi.increase(v);
        }
    }
}

Var Solver::pickAuxiVar() {
    Var v = var_Undef;
    while(lastConflLits.size() > 0) {
        Lit p=lastConflLits[lastConflLits.size()-1];
        lastConflLits.shrink_(1);
	if (weights[var(p)]>0)
	  assert(auxiVar(var(p)));
        if (value(p) == l_Undef && weights[var(p)]>0)
            return var(p);
    }
    while(!orderHeapAuxi.empty()){
        v = orderHeapAuxi.removeMin();
        assert(v!=var_Undef);
	if (weights[v]>0)
	  assert(auxiVar(v));
        if (value(v) == l_Undef && weights[v]>0)
            return v;
    }
    return var_Undef;
}

void Solver::resetIsetData(){
	/*
	for(int i = 0; i < nonUnlockableIsets.size(); i++)
		unlockableIset[nonUnlockableIsets[i]]=true;
	nonUnlockableIsets.clear();

	for(int i = 0; i < unlockedIsets.size(); i++)
		isetUnlockingVar[i]=var_Undef;
	unlockedIsets.clear();

	for(int i = 0; i < unlockedVars.size(); i++){
		Var v = unlockedVars[i];
		for(int j = 0; j < unlockedIsetsOfVar[v].size(); j++){
			weights[v]-=isetsWeights[unlockedIsetsOfVar[v][j]];
		}
		unlockedIsetsOfVar[v].clear();
	}
	unlockedVars.clear();*/

}

//This method updates the reasons of the cores
//A core can be seen as r1 /\  ... /\ rn -> -s1 \/ ... \/ -sn : weight
//At the moment of core definition, r1...rn are true and s1..sn are undefined
//Weight is the minimum of the weights of s1...sn
//When the weiths of s1..sn are increased (freed from other cores) during search,
// 'weight' can be increased. If some 'si' becomes to true, it can be moved
// to the l.h.s. of the implications, i.e. the reasons, if this allows a greater minimum 'weight'
//This is the case when weights[si]<0. This is what this method does
/*void Solver::updateReasons(){
    for(int i = 0; i < varsInCores.size(); i++){
        Var v = varsInCores[i];
        assert(weights[v]>=0 || value(softLits[v])==l_True);
        if(weights[v]<0 && level(v)>0){
            for(int j = 0; j < coresOfVar[v].size(); j++){
                int core = coresOfVar[v][j];
                if(localCores[core].weight>0) {
                    localCores[core].reasons.push(~softLits[v]);
                    localCores[core].nExtraReasons++;
                }
            }
        }
    }
}*/

void Solver::updateCore(int core){
    assert(core>=0);
    assert(core < localCores.size());
    LocalCore & lc = localCores[core];


    int64_t minW = INT64_MAX;
    for (int i = 0; i < lc.lits.size(); i++) {
        Lit q = lc.lits[i];
        Var x = var(q);
        assert(value(q) != l_False);
        if (weights[x] < minW)
            minW = weights[x];
    }
    assert(minW>=0);

    if (minW > 0) {
        for (int i = 0; i < lc.lits.size(); i++) {
            Lit q = lc.lits[i];
            Var x = var(q);
            assert(weights[x] >= minW);
            weights[x] -= minW;
            hardenHeap.update(x);

        }
        lc.weight += minW;
        laConflictCost += minW;
        updateCost+=minW;
    }
}

void Solver::setConflict(int newCore, int64_t iSetCost) {

	const vec<Lit> & lits = localCores[newCore].lits;
    const vec<CRef> & softCl = localCores[newCore].softCl;
    assert(iSetCost>0);
    vec<int> seenIsets;

    nonInferenceCost+=iSetCost;

    for(int i=0; i<lits.size(); i++) {
        Lit p = lits[i];
        Var v = var(p);
        assert(weights[v] >= iSetCost);


        if (coresOfVar[v].size() == 0)
            varsInCores.push(v);
        coresOfVar[v].push(newCore);

        assert(weights[v]>=iSetCost);
        weights[v] -= iSetCost;
        hardenHeap.update(v);
       // printf("%llu", costToTake);
        assert(weights[v] <= weightsBckp[v]);
        if(weights[v]>0)
            lastConflLits.push(p);

    }

    assert(iSetCost>0);
	localCores[newCore].weight=iSetCost;
	//localCores[newCore].nExtraReasons=0;
    laConflictCost += iSetCost;
	activeCores.push(newCore);
}

void Solver::resetConflicts() {

    conflLits.clear();
	while(lastCores.size() > 0){
		freeCores.push(lastCores.last());
		lastCores.pop();
	}

#ifndef NDEBUG
    for(int i = 0; i < nVars(); i++){
        assert(!seen[i]);
    }
#endif
//printf("Reseting cores:");
    for(int i=0; i<activeCores.size(); i++) {
		//printf(" %d",activeCores[i]);
		LocalCore & c = localCores[activeCores[i]];
		for(int k=0; k<c.lits.size(); k++) {
            Lit p = c.lits[k];
            Var v = var(p);
            if(!seen[v]) {
                coresOfVar[v].clear();
                if(value(p)==l_False)
                    countedWeight+=weightsBckp[v]-weights[v];
                weights[v] = weightsBckp[v];
                hardenHeap.update(v);
				conflLits.push(p);
                seen[v]=1;
            }
            assert(weights[v]==weightsBckp[v]);
        }
        //Only keep cores that did not use maxsat resolution soft clauses
        if(c.softCl.size()==0)
		    lastCores.push(activeCores[i]);
        else
            freeCores.push(activeCores[i]);
    }
	//printf("\n");
    for(int i = 0; i < conflLits.size(); i++) {
		Var v = var(conflLits[i]);
		assert(v>=0 && v<activityLB.size());
		double oldAct = activityLB[v];
		// the two equations are equivalent, but the practical precision is different
		// activityLB[v] = stepSizeLB + (1-stepSizeLB)*oldAct;
		activityLB[v] = oldAct + (1-oldAct)*stepSizeLB;
		insertAuxiVarOrder(v);
		assert(activityLB[v] >= oldAct);
		orderHeapAuxi.increase(v);
		seen[var(conflLits[i])] = 0;
	}

    //localCores.clear();
	activeCores.clear();
	laConflictCost=0;
    varsInCores.clear();

    if(countedWeight>=UB)
        softConflictFlag=true;

#ifndef NDEBUG
    for(int i = 0; i < nSoftLits; i++)
      if (auxiVar(var(allSoftLits[i])))
        assert(weights[var(allSoftLits[i])]==weightsBckp[var(allSoftLits[i])]);
#endif

}

void Solver::resetConflicts_() {

    for(int i=0; i<activeCores.size(); i++) {
		int core = activeCores[i];
		LocalCore & c = localCores[core];
		for(int k=0; k<c.lits.size(); k++) {
            Lit p = c.lits[k];
            Var v = var(p);
            //assert(weights[v]<weightsBckp[v]||coresOfVar[v].size()==0);
            assert(weights[v]==weightsBckp[v]||coresOfVar[v].size()>0);
            if(weights[v]<weightsBckp[v]) {
                coresOfVar[v].clear();
                weights[v] = weightsBckp[v];
                hardenHeap.update(v);
                insertAuxiVarOrder(v);
            }
            assert(weights[v]==weightsBckp[v]);
        }
		freeCores.push(core);
    }


    ///localCores.clear();
	activeCores.clear();
	laConflictCost=0;
    varsInCores.clear();

#ifndef NDEBUG
    for(int i = 0; i < nSoftLits; i++)
      if (auxiVar(var(allSoftLits[i])))
        assert(weights[var(allSoftLits[i])]==weightsBckp[var(allSoftLits[i])]);
#endif
}

Var Solver::simplePickAuxiVar() {
    Var v = var_Undef;
    while (v == var_Undef || value(v) != l_Undef ){
        if (orderHeapAuxi.empty())
            return var_Undef;
        else {
            v = orderHeapAuxi.removeMin();
            assert(auxiVar(v));
        }
    }
    return v;
}


void Solver::simplifyQuasiConflictClause(vec<Lit>& out_learnt, int& out_btlevel, int& out_lbd) {
    // Simplify conflict clause:
    int i, j;
    out_learnt.copyTo(analyze_toclear);
    if (ccmin_mode == 2){
        uint32_t abstract_level = 0;
        for (i = 1; i < out_learnt.size(); i++)
            abstract_level |= abstractLevel(var(out_learnt[i])); // (maintain an abstraction of levels involved in conflict)

        for (i = j = 1; i < out_learnt.size(); i++)
            if (reason(var(out_learnt[i])) == CRef_Undef || !litRedundant(out_learnt[i], abstract_level))
                out_learnt[j++] = out_learnt[i];

    }else if (ccmin_mode == 1){
        for (i = j = 1; i < out_learnt.size(); i++){
            Var x = var(out_learnt[i]);

            if (reason(x) == CRef_Undef)
                out_learnt[j++] = out_learnt[i];
            else{
                Clause& c = ca[reason(var(out_learnt[i]))];
                if(auxiVar(x) && hardened[x])
                    c[0]=out_learnt[i];
                for (int k = c.size() == 2 ? 0 : 1; k < c.size(); k++)
                    if (!seen[var(c[k])] && level(var(c[k])) > 0){
                        out_learnt[j++] = out_learnt[i];
                        break; }
            }
        }
    }else
        i = j = out_learnt.size();

    max_literals += out_learnt.size();
    out_learnt.shrink(i - j);
    tot_literals += out_learnt.size();

    out_lbd = computeLBD(out_learnt);
    if (out_lbd <= tier2_lbd_cut && out_learnt.size() <= 35) // Try further minimization?
        if (binResMinimize(out_learnt))
            out_lbd = computeLBD(out_learnt); // Recompute LBD if minimized.

    // Find correct backtrack level:
    //
    if (out_learnt.size() == 1)
        out_btlevel = 0;
    else{
        int max_i = 1;
        // Find the first literal assigned at the next-highest level:
        for (int i = 2; i < out_learnt.size(); i++)
            if (level(var(out_learnt[i])) > level(var(out_learnt[max_i])))
                max_i = i;
        // Swap-in this literal at index 1:
        Lit p             = out_learnt[max_i];
        out_learnt[max_i] = out_learnt[1];
        out_learnt[1]     = p;
        out_btlevel       = level(var(p));
    }

    if (VSIDS){
        add_tmp.clear();
    }
    for (int j = 0; j < analyze_toclear.size(); j++) seen[var(analyze_toclear[j])] = 0;    // ('seen[]' is now cleared)
}

void Solver::analyzeQuasiSoftConflict(vec<Lit>& out_learnt, int& out_btlevel, int& out_lbd)
{

    int pathC = 0;
    Lit p;
	vec<Lit> c2;
    CRef confl;
    // Generate conflict clause:
    //
    out_learnt.push();      // (leave room for the asserting literal)
    int index   = trail.size() - 1;
    assert(countedWeight + laConflictCost < UB);
    int debutFalse = falseLits_lim.size() > 0 ? falseLits_lim[0] : falseLits.size();
    int nbFalseLits = falseLits.size();
    int maxConflLevel = (falseLits.size() > 0) ? level(var(falseLits[nbFalseLits-1])) : 0;

    //updateReasons();

	for(int i = 0; i < activeCores.size(); i++){
		int core = activeCores[i];
        if(localCores[core].weight > 0) {
            seeReasons(falseLits,maxConflLevel,localCores[core].reasons);
            for(int j = 0; j < localCores[core].refCores.size(); j++){
                int core2 = localCores[core].refCores[j];
                seeReasons(falseLits,maxConflLevel,localCores[core2].reasons);
            }
        }
	}

    for(int a=nbFalseLits; a<falseLits.size(); a++)
        seen[var(falseLits[a])] = 0;

    for(int a=debutFalse; a<falseLits.size(); a++) {
        Var v=var(falseLits[a]);
        assert(level(v) > 0);
        if (!seen[v] && !redundantLit(falseLits[a])) {
            seen[v] = 1;
            // if (VSIDS){
            //   varBumpActivity(v, .5);
            //   add_tmp.push(falseLits[a]);
            // }else
            //   conflicted[v]++;
            if (level(v) >= maxConflLevel)
                pathC++;
            else
                out_learnt.push(falseLits[a]);
        }
    }

    falseLits.shrink(falseLits.size() - nbFalseLits);
    assert(pathC > 0 || maxConflLevel==0);
    if (maxConflLevel==0) {
        printf("c ***** top quasi confl at level %d*****\n", decisionLevel());
        assert(pathC == 0);
        out_btlevel=0; out_lbd=0; out_learnt.clear();
        return;
    }
    while (pathC > 0) {
        while (!seen[var(trail[index--])]);
        p     = trail[index+1];
        confl = reason(var(p));
        seen[var(p)] = 0;
        pathC--;
        // sign(p) returns the last bit of p. p is positive iff sign(p)= 0 or false
        // p should not be UIP if it is a negative auxi literal (i.e., if it represents a false soft clause)
        //if (pathC == 0 && !(auxiVar(var(p)) && sign(p)))
        //if (pathC == 0 && !(auxiVar(var(p))))
        if (pathC == 0)
            break;

        bool hardenedLit = auxiLit(p) && hardened[var(p)];
        bool fromHarden=false;
        if(hardenedLit){
            assert(auxiLit(p));
            Clause & c = ca[confl];
            c[0]=p;
            int lbd = computeLBD(c);
            //Virtual clause, need to be created
            if(lbd<=tier2_lbd_cut) {
                fromHarden=true;
				//Important to make a copy, since alloc may reallocate 'c'
				getClauseLits(c,c2);
                confl = ca.alloc(c2, true);
                attachClause(confl);
            }
            else{
                for (int j = 1; j < c.size(); j++) {
                    Lit q = c[j];
                    Var v = var(q);
                    if (level(v) > 0) {
                        if (!seen[v] && !redundantLit(q)){
                            seen[v] = 1;
                            if (level(v) >= maxConflLevel)
                                pathC++;
                            else
                                out_learnt.push(q);
                        }
                    }
                }
            }
        }

        if(!hardenedLit || fromHarden){
            assert(confl != CRef_Undef); // (otherwise should be UIP)
            Clause &c = ca[confl];
            fixBinClauseOrder(c);

            updateClauseUse(confl,fromHarden);
            assert(!fromHarden || c.mark()==CORE || c.mark()==TIER2);

            for (int j = 1; j < c.size(); j++) {
                Lit q = c[j];

                if (!seen[var(q)] && level(var(q)) > 0 && !redundantLit(q)) {
                    seen[var(q)] = 1;
                    if (level(var(q)) >= maxConflLevel) {
                        pathC++;
                    } else
                        out_learnt.push(q);
                }
            }
        }
    }
    out_learnt[0] = ~p;

    simplifyQuasiConflictClause(out_learnt, out_btlevel, out_lbd);
    assert(out_btlevel >0 || out_learnt.size() == 1);

    if (out_lbd > core_lbd_cut)
        getAllUIP(out_learnt, out_btlevel, out_lbd);


    // for(int i=0; i<out_learnt.size(); i++)
    //   printf("%d ", toInt(out_learnt[i]));
    // printf(", btlevel %d, lbd %d, trail: %d, level: %d, lim0: %d, confl: %llu, starts: %llu, lkUP: %llu, UP: %llu, falseLit1: %d, fsize: %d\n",
    // 	   out_btlevel, out_lbd, trail.size(), decisionLevel(), trail_lim[0],
    // 	   conflicts, starts, lk_propagations, propagations, toInt(falseLits[0]), nbFalseLits);
    // for(int i=0; i<conflLits.size(); i++)
    //   printf("%d ", toInt(conflLits[i]));
    // printf("\n%d\n", conflLits.size());


    // if (out_lbd > lbdLimitForOriCls) {
    //     for(int i = saved; i < usedClauses.size(); i++)
    //         ca[usedClauses[i]].setUsed(0);
    //     usedClauses.shrink(usedClauses.size() - saved);
    // }
}

bool Solver::hardenFromQuasiSoftConflict() {
/*
	assert(laConflictCost+countedWeight<UB);
	int firstToHarden=NON;

	for(int i=hardenBeginningIndex; i<nSoftLits; i++) {
		Lit p=softLitsWeightOrder[i];
		if (weightsBckp[var(p)]+laConflictCost+countedWeight<UB)
			break;
		else if (weights[var(p)]+laConflictCost+countedWeight>=UB &&
				 value(p) == l_Undef) {
			firstToHarden=i;
			break;
		}
	}

	if(firstToHarden==NON)
		return false;

	vec<Lit> learnt_clause;
	int backtrack_level, lbd;
	learnt_clause.clear();
	analyzeQuasiSoftConflict(learnt_clause, backtrack_level, lbd);

	vec<Lit> ps;
	ps.clear();

	if (learnt_clause.size() > 0) {
		Lit p = learnt_clause[0];
		if (level(var(p)) < decisionLevel()) {
			cancelUntil(level(var(p)));
		}
		assert(level(var(p)) == decisionLevel());

		ps.push();
		for(int i=0; i<learnt_clause.size(); i++)
			ps.push(learnt_clause[i]);
	}
	else
		cancelUntil(0);

	for(int i=firstToHarden; i<nSoftLits; i++) {
		Lit p=softLitsWeightOrder[i];
		if (weightsBckp[var(p)]+laConflictCost+countedWeight<UB)
			break;
        // Note: this is the remaining weight after possibly being added to an iset
        // Still might trigger hardening
		else if (weights[var(p)]+laConflictCost+countedWeight>=UB &&
				 value(p) == l_Undef) {
			CRef cr = CRef_Undef;
			if(ps.size()>1) {
				ps[0] = p;
				cr=ca.alloc(ps, true);
				hardens.push(cr);
				attachClause(cr);
			}
			uncheckedEnqueue(p, cr);
			fixedByHardens++; fixedByQuasiConfl++;
		}
		} */
    return true;
}


bool Solver::fixByLookahead(vec<Lit>& out_learnt) {
    bool reset=false;
    int btlevel, lbd;
    nbFixedByLH++;
    for(int i=1; i<out_learnt.size(); i++)
        seen[var(out_learnt[i])]=1;
    simplifyQuasiConflictClause(out_learnt, btlevel, lbd);
    cancelUntil(btlevel);
    if (out_learnt.size() == 1)
        uncheckedEnqueue(out_learnt[0]);
    else {
        CRef cr = ca.alloc(out_learnt, true);
        if (out_learnt.size() > splitClauseSize && lbd<=tier2_lbd_cut)
            hardLearnts.push(cr);
        ca[cr].set_lbd(lbd);
        if (lbd <= core_lbd_cut){
            learnts_core.push(cr);
            ca[cr].mark(CORE);
            ca[cr].touched() = conflicts;
        }else if (lbd <= tier2_lbd_cut){
            learnts_tier2.push(cr);
            ca[cr].mark(TIER2);
            ca[cr].touched() = conflicts;
        }else{
            learnts_local.push(cr); }
        claBumpActivity(ca[cr]);
        attachClause(cr);
        uncheckedEnqueue(out_learnt[0], cr);
    }
    return reset;
}

bool Solver::enqueueAssumptions(int & nextIdx, bool recheckNext) {
    bool someEnqueued=false;
	if(recheckNext) {
        while (nextIdx < lastCores.size() && !someEnqueued) {
            int core = lastCores[nextIdx];
            LocalCore &c = localCores[core];
            assert(c.softCl.size() == 0);
            bool active = true;
            for (int j = 0; j < c.lits.size() && active; j++) {
                Lit p = c.lits[j];
                Var v = var(p);
                if (value(p) == l_False)
                    active = false;
            }
            if (active) {
                for (int j = 0; j < c.lits.size(); j++) {
                    Lit p = c.lits[j];
                    Var v = var(p);
                    if (value(v) == l_Undef && weights[v] > 0) {
                        uncheckedEnqueueForLK(p);
                        someEnqueued = true;
                    }
                }
            } else {
                for (int j = 0; j < c.lits.size(); j++)
                    if (value(c.lits[j]) == l_Undef && weights[var(c.lits[j])] > 0)
                        lastConflLits.push(c.lits[j]);
            }

            nextIdx++;
        }

        if (someEnqueued)
            return true;
        if (activeCores.size() > 0) {
            vec<Lit> &lits = localCores[activeCores.last()].lits;
            for (int i = lits.size() - 1; i >= 0; i--) {
                if (nonLockedAuxiVar(var(lits[i])) && value(lits[i]) == l_Undef) {
                    uncheckedEnqueueForLK(lits[i]);
                    someEnqueued = true;
                }
            }
        }
    }


    if(someEnqueued)
        return true;

    Var v = pickAuxiVar();
    if (v == var_Undef)
        return false;

    assert(nonLockedAuxiVar(v));
    uncheckedEnqueueForLK(softLits[v]);
    return true;
}

int Solver::pickCoreIdx(){
	int core;
	if(freeCores.size()==0){
		core = localCores.size();
		localCores.push();
	}
	else{
		core=freeCores.last();
		freeCores.pop();
        LocalCore & c = localCores[core];
        c.reset();
	}

	return core;
}

void Solver::moreLookahead(){
    vec<Lit> out_learnt;
    setTrailRecord();
    UBconflictFlag=false; softConflictFlag=false; falseVar = var_Undef;
    bool foundCores=false;
	bool recheckNext=true;
    bool maxResDone=false;
	int nextIdx=0;
    resetIsetData();

    bool foundAfter=0;
    while (countedWeight + laConflictCost < UB) {
        if(!enqueueAssumptions(nextIdx, recheckNext)) {
            cancelUntilTrailRecordFillHeap();
            break;
		}
		recheckNext=false;

        CRef confl = propagateForLK();
        if (confl != CRef_Undef || falseVar != var_Undef) {
            foundCores=true;
            if(maxResDone)
                foundAfter++;

            assert(falseVar==var_Undef || reason(falseVar)!=CRef_Undef);
            if(confl==CRef_Undef) confl=reason(falseVar);

			int coreIdx = pickCoreIdx();
            int64_t coreCost = lookbackGetMinIsetCost(confl, falseVar);
            lookbackResetTrail(confl, falseVar, out_learnt, coreIdx, coreCost, maxResDone, UB - countedWeight - laConflictCost);
            assert(coreCost>0);
            falseVar = var_Undef;
            recheckNext=true;
            LocalCore & core = localCores[coreIdx];


            //This case is triggered when it is discovered that a literal can be propagated at DL,
            //because only  assigning ~out_learnt[0] suffices to derive a conflicting clause
            if (core.lits.size() == 0 && core.softCl.size()==0){
				freeCores.push(coreIdx);
                resetConflicts_();
                fixByLookahead(out_learnt);
                CRef confl = lPropagate();
                if (confl != CRef_Undef || softConflictFlag) {
                    if (confl != CRef_Undef) {
                        LHconfl = confl;
                        softConflictFlag=false;
                        UBconflictFlag=false;
                    }
                    return;
                }
                setTrailRecord();
                assert(UB>countedWeight);
                assert(laConflictCost==0);
                assert(activeCores.size()==0);
                lastConflLits.clear();
                maxResDone=false;
				nextIdx=0;
                /*for(int i=conflLits.size()-1; i>=0; i--)
                    if  (conflLits[i] != lit_Undef)
                        lastConflLits.push(conflLits[i]);*/
            }
            else
                setConflict(coreIdx, coreCost);

        }
    }
    if(countedWeight + laConflictCost >= UB){
        assert(LHconfl==CRef_Undef);
        softConflictFlag=true; UBconflictFlag=true;
    }


}


void Solver::cleanCores(){
	int i,j;
	for(i = 0,j=0; i < lastCores.size(); i++){
		int core=lastCores[i];
		if(localCores[core].level<=decisionLevel())
			lastCores[j++] = core;
		else
			freeCores.push(core);
	}
	lastCores.shrink(i - j);
}


//#define printTestedVar

// The involvedClauses stack stores the hard clauses that make disjoint conflicting soft clauses.
// If Ub is reached, the stack (together with the involved flag of each involved clauses) is cleared
// when analyzing the soft conflict
// Otherwise, it is cleared here before returning true.
bool Solver::lookahead() {
    static int64_t thres=2;
    static int prevConflicts=0;
    static int64_t maxSuccLB=0;
    static int64_t prevUB=0;
    static int nbSample=0;
    static double sumLB=0;
    static double sumSQLB=0;
    static double coef = 2;
    static int myLH=0;
    static int mySucc=0;
    static bool lastSucc=false;

    assert(UB>countedWeight);

    LHconfl = CRef_Undef;

#ifdef FLAG_NO_LA
    return false;
#endif

    int64_t lb = UB-countedWeight;
    if(lb>totalCost-satisfiedWeight-countedWeight) //Impossible to reach UB
        return false;

    if (UB != prevUB) {
        prevUB = UB; nbSample=0; sumLB=0; sumSQLB=0;
    }

    // for(int i=0; i<nVars(); i++)
    //   assert(!involved[i]);
    // if (UB < prevUB) {
    //   maxSuccLB = 0;
    //   // maxSuccLB -= prevUB - UB;
    //   // if (maxSuccLB < 0)
    //   //   maxSuccLB=0;
    //   // printf("c maxSuccLB: %d, UB: %llu \n", maxSuccLB, UB);
    //   prevUB = UB;
    // }


#ifndef FLAG_ALWAYS_LA
    int sampled=0;
    if (conflicts > prevConflicts) {
        if (drand(random_seed) < 0.01) {
            thres = lb;
            sampled=1;
        }
        else thres = maxSuccLB;
        // if (thres > UB/2)
        //   printf("c %d %llu\n", thres, UB/2);
        //  assert(thres <= UB/2);
        prevConflicts = conflicts;
    }
    if (LOOKAHEAD == nbLKsuccess || lastSucc)
        thres = UB;
    if (lb > thres)
        return false;


    if (stepSizeLB > 0.06) stepSizeLB -= 0.000001;

    if (!sampled)
        myLH+=2;
#endif

    LOOKAHEAD++;


    assert(laConflictCost==0);
    assert(activeCores.size()==0);

    lastConflLits.clear();
    /*for(int i=conflLits.size()-1; i>=0; i--)
        if  (conflLits[i] != lit_Undef)
            lastConflLits.push(conflLits[i]);*/

#ifndef NDEBUG
	assert(lastCores.size() + freeCores.size() == localCores.size());

	/*for(int i = 0; i < freeCores.size(); i++) {
		assert(freeCores[i]<localCores.size());
		seen[freeCores[i]] = 1;
	}
	for(int i = 0; i < lastCores.size(); i++) {
		assert(lastCores[i] < localCores.size());
		seen[lastCores[i]] = 1;
	}
	for(int i=0; i < localCores.size(); i++){
		assert(seen[i]);
		seen[i]=0;
	}*/
#endif

	moreLookahead();

#ifndef FLAG_ALWAYS_LA
    if (softConflictFlag) {
        lastSucc=true;
        if (sampled) {
            assert(lb+countedWeight+laConflictCost>=UB);
            int64_t totalCost = countedWeight+laConflictCost+lb-UB;
            nbSample++;
            sumLB += totalCost; sumSQLB += totalCost * totalCost;
            double meanLB = ((double)sumLB)/nbSample;
            double meanSQLB = ((double)sumSQLB)/nbSample;
            double stddev = sqrt(meanSQLB - meanLB*meanLB);
            if (myLH > 0) {
                int rate = (mySucc * 100)/myLH;
                if (rate > 85 && (meanLB + coef*stddev) < UB)
                    coef += 0.1;
                else if (rate <= 70 && (meanLB + coef*stddev) > 1)
                    coef -= 0.1;
                // if ((meanLB + coef*stddev) > UB+1)
                //   coef = (UB+1 - meanLB)/stddev;
                //  printf("rate : %d, coef: %2.1lf, UB: %llu, new thres: %d, mean: %4.2lf, stddev: %4.2lf\n", rate, coef, UB, (int)(meanLB + coef*stddev), meanLB, stddev);
            }
            else {
                if (coef < 2)
                    coef = 2;
                //	  printf("no LH\n");
            }
            maxSuccLB = (int64_t) (meanLB + coef*stddev);
            //myLH=0; mySucc = 0;
        }
        else { mySucc+=2; }

        nbLKsuccess++; totalPrunedLB += lb; totalPrunedLB2 += lb*lb;
    }
    else {
        lastSucc=false;
        if (!sampled) {
            mySucc+=1;
            /* if(LHconfl==CRef_Undef)
                 mySucc += 1;
             else myLH-=2;*/
        }
        thres = lb - 1; //(lb+nbConfl)/2;
        prevConflicts = conflicts;
    }
#endif

    return activeCores.size()>0 || LHconfl!=CRef_Undef;
}


// for each soft clause of the form 1 2 3, create a new variable non decisional v and
// add a hard equivalence v <--> 1 2 3, meaning: add a hard clause -v 1 2 3
//    then add 3 hard clauses v -1, v -2, v -3
void Solver::addHardClausesForSoftClauses() {
    vec<Lit> lits;
    int nbUnitSoft=0, nbNonUnitSoft=0;
    hardSoftClauses.clear();
    nbOrignalVars = nVars();
    unitSoftLits.clear(); nonUnitSoftLits.clear(); //allSoftLits.clear();
    int i2=0;
    for(int i=0; i<softClauses.size(); i++) {
        lits.clear();
        Clause& c=ca[softClauses[i]];
        int sat=0;
        for (int j=0; j<c.size(); j++) {
            if (value(c[j]) == l_Undef)
                lits.push(c[j]);
            else if (value(c[j]) == l_True)
                sat=1;
        }
        if (sat==0) {
            if (lits.size() == 0)
                solutionCost += weightsBckp[i];
            else {
                Lit p = lits[0];
                Var v = var(p);
                //If another soft clause exists for the same literal, just accumulate weights
                if (lits.size() == 1) {
                    //If maintains polarity, just accumulate
                    if (v < softLits.size() && softLits[v] == p)
                        weights[v] += weightsBckp[i];
                    //If changes polarity
                    else if (v < softLits.size() && softLits[v] == ~p) {
                        //If weight is not surpassed, keep polarity
                        if (weights[v] > weightsBckp[i]){
                            solutionCost+=weightsBckp[i];
                            weights[v] -= weightsBckp[i];
                        }
                        //Otherwise switch polarity
                        else {
                            solutionCost+=weights[v];
                            weights[v]=weightsBckp[i]-weights[v];
                            softLits[v] = p;
                        }
                    }
                    else{
                        declareSoftLit(p, true, weightsBckp[i]);
                        nbUnitSoft++;
                    }
                }
                //If no unit soft clause, or another unit soft clause exists for the negated literal, introduce new softLit
                else {
                    assert(lits.size()>1);
                    nbNonUnitSoft++;
                    Lit p = createHardClausesFromLits(lits, weightsBckp[i]);
                    allSoftLits.push(p);
                    softClauses[i2++]=softClauses[i];
                }
            }
        }
    }
    int i=0, j=0;
    for(; i < unitSoftLits.size(); i++){
        Lit p = unitSoftLits[i];
        Var v = var(p);
        if(weights[v]==0) {
            softLits[v] = lit_Undef;
            nSoftLits--;
            nbUnitSoft--;
        }
        else {
            unitSoftLits[j++] = softLits[var(unitSoftLits[i])]; //The polarity might have changed
            allSoftLits.push(softLits[var(unitSoftLits[i])]);
        }
    }
    unitSoftLits.shrink(i-j);
    printf("c nb soft clauses and lits: %d, %d, of which %d unit, %d nonUnit and %llu empty\n",
           softClauses.size(), nbUnitSoft+nbNonUnitSoft, nbUnitSoft, nbNonUnitSoft, solutionCost);
    softClauses.shrink(softClauses.size()-i2);
    assert(nSoftLits==allSoftLits.size());
    weights.copyTo(weightsBckp);
}

void Solver::insertAuxiVarOrder(Var x) {
    if (!orderHeapAuxi.inHeap(x) && (auxiVar(x))) orderHeapAuxi.insert(x);
}

void Solver::removeLearntClauses() {
    for (int i=0; i < learnts_local.size(); i++)
        removeClause(learnts_local[i]);
    learnts_local.clear();
    for (int i=0; i < learnts_tier2.size(); i++)
        removeClause(learnts_tier2[i]);
    learnts_tier2.clear();
    for (int i=0; i < learnts_core.size(); i++)
        removeClause(learnts_core[i]);

    assert(hardens.size()==0);

    for(int i=0; i < PBC.size(); i++)
        removeClause(PBC[i]);
    PBC.clear();
    CCPBadded=false;

    for(int i=0; i<isetClauses.size(); i++)
        removeClause(isetClauses[i]);
    isetClauses.clear();

    learnts_core.clear();
    watches.cleanAll();
    watches_bin.cleanAll();
    checkGarbage();

    dynVars.clear();
    for(int i=nVars() - 1; i>=staticNbVars; i--) {
        decision[i] = false;
        dynVars.push(i);
    }
}

void Solver::cancelUntilBeginning(int begnning) {

    for (int c = trail.size()-1; c >= begnning; c--){
        Var      x  = var(trail[c]);
        if (!VSIDS){
            uint32_t age = conflicts - picked[x];
            if (age > 0){
                double adjusted_reward = ((double) (conflicted[x] + almost_conflicted[x])) / ((double) age);
                double old_activity = activity_CHB[x];
                activity_CHB[x] = step_size * adjusted_reward + ((1 - step_size) * old_activity);
                if (order_heap_CHB.inHeap(x)){
                    if (activity_CHB[x] > old_activity)
                        order_heap_CHB.decrease(x);
                    else
                        order_heap_CHB.increase(x);
                }
            }
#ifdef ANTI_EXPLORATION
            canceled[x] = conflicts;
#endif
        }
        assigns [x] = l_Undef;
        if (phase_saving > 1 || (phase_saving == 1) && c > trail_lim.last())
            polarity[x] = sign(trail[c]);
        insertAuxiVarOrder(x);
        insertVarOrder(x);
        seen[x] = 0;
        if(auxiVar(x)) {
            hardenHeap.update(x);
            hardened[x]=false;
        }
    }
    // for(int c=begnning; c<trail_lim[0]; c++)
    //   seen[var(trail[c])] = 0;
    qhead = begnning;
    trail.shrink(trail.size() - begnning);
    trail_lim.shrink(trail_lim.size());
    falseLits.shrink(falseLits.size());
    falseLits_lim.shrink(falseLits_lim.size());
    countedWeight_lim.shrink(countedWeight_lim.size());
    countedWeight=0;
	satisfiedWeight_lim.shrink(satisfiedWeight_lim.size());
	satisfiedWeight=0;

    for(int i = 0; i < hardens.size(); i++) {
        assert(ca[hardens[i]].mark()!=1);
        ca[hardens[i]].mark(1);
        ca.free(hardens[i]);
    }
    hardens.shrink_(hardens.size());
    hardens_lim.shrink(hardens_lim.size());

    int nbeq=0;
    for(Var v=0; v<nVars(); v++) {
      Lit p=mkLit(v);
      if (rpr[toInt(p)] != lit_Undef) {
	assert(rpr[toInt(~p)] == ~rpr[toInt(p)]);
	rpr[toInt(p)] = lit_Undef;
	rpr[toInt(~p)] = lit_Undef;
	nbeq++;
      }
    }
    assert(equivLits.size() == nbeq);
    feasibleNbEq=0; equivLits.clear(); prevEquivLitsNb=0; myDerivedCost=0;
    nbSoftEq = 0;

#ifndef  NDEBUG
	int64_t w = 0;
	for (int i = 0; i < falseLits.size(); ++i)
		w += weightsBckp[var(falseLits[i])];
	assert(w == countedWeight);
	int64_t wT = 0, wF = 0;
	for (int i = 0; i < trail.size(); i++) {
		Lit p = trail[i];
		Var v = var(p);
		if (auxiVar(v)) {
			if (softLits[v] == p)
				wT += weightsBckp[v];
			else
				wF += weightsBckp[v];
		}
	}
	assert(wF == countedWeight);
	assert(wT == satisfiedWeight);
#endif

}

void Solver::checkSolution() {
#ifndef NDEBUG
    for(int i = 0; i < nVars(); i++)
        assert(!decision[i] || value(i)!=l_Undef);

    int64_t weight=0;
    for(int i=0; i<nSoftLits; i++){
      if (auxiVar(var(allSoftLits[i])) && value(allSoftLits[i]) == l_False) {
            weight+=weightsBckp[var(allSoftLits[i])];
        }
    }

    if (weight != countedWeight) {
        printf("c **** error in weight, real weight: %llu, recorded weight: %llu****\n",
               weight, countedWeight);
    }
    assert(weight == countedWeight);

    // printf("c there are %d hard clauses\n", clauses.size());
    for(int i=0; i<clauses.size(); i++)
      if (!removed(clauses[i]) && !satisfied(ca[clauses[i]])) {
            printf("c clause %d non-satisfied: ", clauses[i]);
            Clause& c=ca[clauses[i]];
            for(int j=0; j<c.size(); j++)
                printf(" %d ", toInt(c[j]));
            printf("\n");
        }
#endif
}

//For a set of literals 1 2 3, create a new soft lit x and create
// hard clauses encoding x <-> 1 2 3 (-x 1 2 3, x -1, x -2, x -3)
Lit Solver::createHardClausesFromLits(vec<Lit> &lits, int64_t weight) {
    Var vv=newVar(false, false);
    Lit pp = mkLit(vv);
    declareSoftLit(pp,false,weight);

    lits.push(~pp);
    CRef cr = ca.alloc(lits, false);
    clauses.push(cr);
    attachClause(cr);
    //   hardSoftClauses.push(cr);

    lits.pop();
    vec<Lit> ps;
    ps.clear();
    ps.push(pp);
    ps.push(); // leave a room for the second literal
    for (int ii=0; ii<lits.size(); ii++) {
        ps[1] = ~lits[ii];
        CRef cr = ca.alloc(ps, false);
        clauses.push(cr);
        attachClause(cr);
        imply[toInt(lits[ii])] = pp;
    }
    return pp;
}

struct unitSoftLits_lt {
    vec2<Lit, vec<Lit> >& conflictLits;
    unitSoftLits_lt(vec2<Lit, vec<Lit> >& conflictLits_) : conflictLits(conflictLits_) {}
    bool operator () (Lit l1, Lit l2) {
        return conflictLits[l1].size() < conflictLits[l2].size();
    }
};



void Solver::partition() {
    vec<Lit> remainingLits, candidateLits, iset;
    int i, j;
    int nbIsets=0;

    int initNSoftLits=nSoftLits;

    for(Var vv = 0; vv < initNSoftLits; vv++) {
        remainingLits.clear();
        if(!seen[vv]) {
            seen[vv] = 1;
            if (value(vv) == l_Undef && conflictLits[softLits[vv]].size() > 0)
                remainingLits.push(softLits[vv]);
            else continue;
        }
        else continue;

        //Fill remainingLits with the connected component of remainingLits[0]
        assert(remainingLits.size()==1);
        for(i=0; i < remainingLits.size(); i++){
            Lit p = remainingLits[i];
            const vec<Lit> & lits = conflictLits[p];
            for(j=0; j < lits.size(); j++){
                Lit q = lits[j];
                if(!seen[var(q)]){
                    seen[var(q)]=1;
                    if(value(q)==l_Undef) {
                        assert(conflictLits[q].size()>0);
                        remainingLits.push(q);
                    }
                }
            }
        }

        //Find the partition of remainingLits
        while (remainingLits.size() > 0) {
            if(candidateLits.size()>remainingLits.size())
                candidateLits.shrink(candidateLits.size()-remainingLits.size());
            else
                candidateLits.growTo(remainingLits.size());
            for (i = 0; i < candidateLits.size(); i++) {
                Lit p = remainingLits[i];
                candidateLits[i] = p;
                softVarLocked[var(p)] = 0;
            }

            //Find the next iset
            iset.clear();
            int64_t minW = INT64_MAX;
            while (candidateLits.size() > 0) {
                //Find the best iset among the candidates
                Lit best = lit_Undef;
                int idx = -1;

                for (i = 0, j=0; i < candidateLits.size(); i++) {
                    Lit p = candidateLits[i];
                    if(softVarLocked[var(p)]==iset.size()) {
                        if (best == lit_Undef
                            || conflictLits[p].size() < conflictLits[best].size()
                            || conflictLits[p].size() == conflictLits[best].size() &&
                               weights[var(p)] > weights[var(best)]) {
                            best = p;
                            idx = j;
                        }
                        candidateLits[j++]=candidateLits[i];
                    }
                }
                candidateLits.shrink(i-j);

                if(best!=lit_Undef) {
                    //Put the candidate into the iset
                    iset.push(best);
                    if (weights[var(best)] < minW)
                        minW = weights[var(best)];

                    candidateLits[idx]=candidateLits.last();
                    candidateLits.pop();
                    const vec<Lit> & lits = conflictLits[best];
                    for(j=0; j < lits.size(); j++){
                        Lit q = lits[j];
                        softVarLocked[var(q)]++;
                    }
                }
            }

            //Construct the iset
            if (iset.size() > 1) {
                createHardClausesFromLits(iset, minW);
                nbIsets++;
            }

            //If the iset size is 0, also temporarity make weight 0 for the lit to be removed from lists
            for (int k = 0; k < iset.size(); k++) {
                assert(weights[var(iset[k])] >= minW);
                weights[var(iset[k])] -= minW;
                if (weights[var(iset[k])] == 0 && iset.size() != 1) {
                    softLits[var(iset[k])] = lit_Undef;
                    nSoftLits--;
                }
            }
            derivedCost += minW * (iset.size() - 1);


            //Update remaining lits
            for (i = 0, j = 0; i < remainingLits.size(); i++) {
                Lit p = remainingLits[i];
                //Only keep lits with weight>0
                if (weights[var(p)] > 0) {
                    //From those, only keep the ones with some incomp.
                    vec<Lit> &litsI = conflictLits[p];
                    int k, l;
                    for (k = 0, l = 0; k < litsI.size(); k++)
                        if (weights[var(litsI[k])] > 0)
                            litsI[l++] = litsI[k];
                    litsI.shrink(k - l);
                    if (litsI.size() > 0)
                        remainingLits[j++] = remainingLits[i];
                }
            }
            remainingLits.shrink(i - j);

            if (iset.size() == 1)
                weights[var(iset[0])] = minW;
        }
    }
    for(Var vv = 0; vv < initNSoftLits; vv++)
        seen[vv]=0;

    for(i=0, j=0; i<unitSoftLits.size(); i++)
        if (softLits[var(unitSoftLits[i])] != lit_Undef) {
            unitSoftLits[j++] = unitSoftLits[i];
        }
    unitSoftLits.shrink(i-j);
    for(i=0, j=0; i<nonUnitSoftLits.size(); i++)
        if (softLits[var(nonUnitSoftLits[i])] != lit_Undef) {
            nonUnitSoftLits[j++] = nonUnitSoftLits[i];
        }
    nonUnitSoftLits.shrink(i-j);
    printf("c isets %d, derivedCost %llu\n", nbIsets, derivedCost);
}


void Solver::partition2() {
    vec<Lit> remainingLits, candidateLits, iset;
    int i, j;
    int nbIsets=0;

    int initSoftLits=allSoftLits.size();
    for(int ii = 0; ii < allSoftLits.size(); ii++) {
        Var vv = var(allSoftLits[ii]);
        remainingLits.clear();
        if(!seen[vv]) {
            assert(auxiVar(vv));
            seen[vv] = 1;
            if (value(vv) == l_Undef && conflictLits[softLits[vv]].size() > 0) {
                remainingLits.push(softLits[vv]);
            }
            else continue;
        }
        else continue;

        //Fill remainingLits with the connected component of remainingLits[0]
        assert(remainingLits.size()==1);
        for(i=0; i < remainingLits.size(); i++){
            Lit p = remainingLits[i];
            const vec<Lit> & lits = conflictLits[p];
            for(j=0; j < lits.size(); j++){
                Lit q = lits[j];
                if(!seen[var(q)]){
                    seen[var(q)]=1;
                    if(value(q)==l_Undef) {
                        assert(conflictLits[q].size()>0);
                        remainingLits.push(q);
                    }
                }
            }
        }

        sort(remainingLits,LitOrderPartition(weights,conflictLits));

        //Find the partition of remainingLits
        for(int jj=0; jj < remainingLits.size(); jj++){
            Lit pjj = remainingLits[jj];
            if (!auxiLit(pjj))
                continue;

            candidateLits.clear();
            candidateLits.push(pjj);
            vec<Lit> visited;

            //Find the next iset
            iset.clear();
            int64_t minW = INT64_MAX;
            while (candidateLits.size() > 0) {
                //Find the best iset among the candidates
                Lit best = candidateLits[0];
                int idx = 0;
                for (i = 1; i < candidateLits.size(); i++) {
                    Lit p = candidateLits[i];
                    if (conflictLits[p].size() < conflictLits[best].size()
                        || conflictLits[p].size() == conflictLits[best].size() &&
                           weights[var(p)] > weights[var(best)]) {
                        best = p;
                        idx = j;
                    }
                }
                if(best!=lit_Undef) {
                    //Put the candidate into the iset
                    iset.push(best);
                    if (weights[var(best)] < minW)
                        minW = weights[var(best)];

                    const vec<Lit> & lits = conflictLits[best];
                    assert(lits.size()>0);
                    candidateLits.clear();
                    for(j=0; j < lits.size(); j++){
                        Lit q = lits[j];
                        assert(q!=best);
                        softVarLocked[var(q)]++;
                        if(softVarLocked[var(q)]==1)
                            visited.push(q);
                        if(value(q)==l_Undef && weights[var(q)]>0 && softVarLocked[var(q)]==iset.size()) {
                            candidateLits.push(q);
                        }
                    }
                }
            }
            for(i = 0; i < visited.size(); i++)
                softVarLocked[var(visited[i])]=0;
            if(iset.size()>1) {
                assert(minW>0);
                //Construct the iset
                sort(iset, LitOrderWeightDec(weights));
                vec<Lit> cl(2,lit_Undef);
                while (iset.size() > 1) {
                    assert(minW>0);
                    cl[1] = ~createHardClausesFromLits(iset, minW);
                    if (cl[0] != lit_Undef) {
                        CRef cr = ca.alloc(cl, false);
                        clauses.push(cr);
                        attachClause(cr);
                    }
                    cl[0] = ~cl[1];
                    int last = iset.size();
                    for (int k = iset.size() - 1; k >= 0; --k) {
                        weights[var(iset[k])] -= minW;
                        assert(weights[var(iset[k])]>=0);
                        if (weights[var(iset[k])] == 0) {
                            removeSoftLit(iset[k]);
                            last = k;
                        }
                    }
                    derivedCost += minW*(iset.size()-1);
                    nbIsets++;
                    iset.shrink(iset.size() - last);
                    if (iset.size() > 0)
                        minW = weights[var(iset.last())];
                }
                jj--;
            }
        }
    }
    for(int ii = 0; ii < allSoftLits.size(); ii++) {
        Var vv = var(allSoftLits[ii]);
        seen[vv] = 0;
    }

    allSoftLits.clear();
    for(i=0, j=0; i<unitSoftLits.size(); i++)
        if (softLits[var(unitSoftLits[i])] != lit_Undef) {
            unitSoftLits[j++] = unitSoftLits[i];
            allSoftLits.push(unitSoftLits[i]);
        }
    unitSoftLits.shrink(i-j);
    for(i=0, j=0; i<nonUnitSoftLits.size(); i++)
        if (softLits[var(nonUnitSoftLits[i])] != lit_Undef) {
            nonUnitSoftLits[j++] = nonUnitSoftLits[i];
            allSoftLits.push(nonUnitSoftLits[i]);
        }
    nonUnitSoftLits.shrink(i-j);
    assert(allSoftLits.size()==nSoftLits);
    weights.copyTo(weightsBckp);
    printf("c isets %d, derivedCost %llu, reduction of soft from %d to %d\n", nbIsets, derivedCost,initSoftLits,nSoftLits);
}



void Solver::partitionAMO() {
	vec<Lit> candidateLits;
	int i, j;

    assert(nSoftLits==allSoftLits.size());
	for(int i = 0; i < nSoftLits; i++) {
        Var vv = var(allSoftLits[i]);
        if (value(vv) == l_Undef)
            candidateLits.push(~softLits[vv]);
    }

	sort(candidateLits,LitOrderPartitionInverse(weights,conflictLits));

	//Find the partition
	for(int ii=0; ii < candidateLits.size(); ii++){
		Lit pii = candidateLits[ii];
		if(!seen[var(pii)]) {
			vec<Lit> visited;
			int newAmo = amos.size();
			amos.init(newAmo);
			amos[newAmo].push(pii);
			seen[var(pii)] = 1;
			vec<Lit> &mutex = conflictLits[pii];
			sort(mutex, LitOrderPartitionInverse(weights, conflictLits));
			for (i = 0; i < mutex.size(); i++) {
				visited.push(mutex[i]);
				softVarLocked[var(mutex[i])]++;
			}

			for (i = 0; i < mutex.size(); i++) {
				if (!seen[var(mutex[i])] && value(mutex[i])==l_Undef && softVarLocked[var(mutex[i])] == amos[newAmo].size()) {
					amos[newAmo].push(mutex[i]);
					seen[var(mutex[i])] = 1;
					const vec<Lit> &lits = conflictLits[mutex[i]];
					for (j = 0; j < lits.size(); j++) {
						Lit q = lits[j];
						softVarLocked[var(q)]++;
						if (softVarLocked[var(q)] == 1)
							visited.push(q);
					}
				}

			}
			for (i = 0; i < visited.size(); i++)
				softVarLocked[var(visited[i])] = 0;
		}
	}

    for(int i = 0; i < nSoftLits; i++) {
        Var vv = var(allSoftLits[i]);
		assert(value(vv)!=l_Undef || seen[vv]);
		seen[vv]=0;
	}

	printf("c amos %d, lits %d\n", amos.size(), candidateLits.size());

}

void Solver::desactivateSoftLits() {
    for(int i = 0; i < allSoftLits.size(); i++)
        softLits[var(allSoftLits[i])]=lit_Undef;
}

void Solver::activateSoftLits() {
    for(int i = 0; i < allSoftLits.size(); i++)
        softLits[var(allSoftLits[i])]=allSoftLits[i];
}


void Solver::addConflictLit(Lit p, Lit q) {
    int i;
    vec<Lit>& lits1=conflictLits[p];
    for(i=0; i<lits1.size(); i++)
        if (lits1[i] == q)
            break;
    if (i==lits1.size())
        lits1.push(q);
    vec<Lit>& lits2=conflictLits[q];
    for(i=0; i<lits2.size(); i++)
        if (lits2[i] == p)
            break;
    if (i==lits2.size())
        lits2.push(p);
}

bool Solver::findConflictSoftLits() {
    CRef confl;
    int initTrail = trail.size(), nbConflLits=0, nbFailedLits=0, nbConfLits2=0;
    int i, j;

    //Could be improved, no need to have a list for both literals,
    //just one list per var


    falseLits.clear();
    falseLitsRecord = 0; trailRecord = trail.size();  rootConflCost = 0;
    countedWeight=0; countedWeightRecord=0; satisfiedWeight=0; satisfiedWeightRecord=0;
	for(i=0; i<unitSoftLits.size(); i++) {
        conflictLits[unitSoftLits[i]].clear();
    }
    for(i=0; i<unitSoftLits.size(); i++) {
        Lit p=unitSoftLits[i];
        if (value(p) != l_Undef)
            continue;
        simpleUncheckEnqueue(p);
        confl = simplePropagate();
        if (confl != CRef_Undef || softConflictFlag){
            cancelUntilTrailRecord();
            softConflictFlag=false;
            uncheckedEnqueue(~p);
            if (propagate() != CRef_Undef  || softConflictFlag){
                return false;
            }
			setTrailRecord();
            nbFailedLits++;
        }
        else {
            if (falseLits.size() > 0) {
                nbConflLits += falseLits.size();
                for(j=falseLitsRecord; j<falseLits.size(); j++)
                    addConflictLit(p, falseLits[j]);
            }
            cancelUntilTrailRecord();
        }
    }
    printf("c conflLits %d, conflLits2 %d, nbFailedLits %d, fixedVarsBypreproc %d, totalFixedVars %d\n",
           nbConflLits, nbConfLits2, nbFailedLits, trail.size()-initTrail, trail.size());

    if (nbConflLits > 0)
        partition2();


    return true;
}


bool Solver::findAMOs() {
	CRef confl;
	int initTrail = trail.size(), nbConflLits=0, nbFailedLits=0;
	int i, j;

    for(int i = 0; i < nVars(); i++) {
        conflictLits[mkLit(i,true)].clear();
        conflictLits[mkLit(i,false)].clear();
    }

	setTrailRecord();
	vec<Lit> trueLits;
	for(i=0; i<nSoftLits; i++) {
		Lit p=allSoftLits[i];
		if (value(p) != l_Undef)
			continue;
		simpleUncheckEnqueue(~p);
		confl = simplePropagateForAMO(trueLits);
		if (confl != CRef_Undef || softConflictFlag){
			cancelUntilTrailRecord();
			softConflictFlag=false;
			uncheckedEnqueue(p);
			if (propagate() != CRef_Undef  || softConflictFlag){
				return false;
			}
			setTrailRecord();
			nbFailedLits++;
		}
		else {
			if (trueLits.size() > 0) {
				nbConflLits += trueLits.size();
				for(j=0; j<trueLits.size(); j++)
					addConflictLit(~p, ~trueLits[j]);
			}
			cancelUntilTrailRecord();
		}
		trueLits.clear();
	}
	printf("c mutexes %d, nbFailedLits %d, \n",nbConflLits, nbFailedLits);

	partitionAMO();

	conflictLits.clear(true);

	return true;
}


bool Solver::findImplications() {
    CRef confl;
    int nfixed=0, nadded=0, nused=0;

    int i, j;
    vec<Lit> propLits;

    falseLits.clear();
    setTrailRecord();

    assert(nonUnitSoftLits.size()==softClauses.size());
    int ikept=0;
    for(i=0; i<nonUnitSoftLits.size(); i++) {
        Lit pi = nonUnitSoftLits[i];
        assert(auxiLit(pi));
        if(value(pi)!=l_Undef) {
            nonUnitSoftLits[ikept++]=nonUnitSoftLits[i];
            continue;
        }
        CRef cr = softClauses[i];
        Clause & c = ca[cr];
        assert(c.size()>1);
        bool first = true;
        propLits.clear();

        for(j=0; j < c.size(); j++){
            Lit p=c[j];
            if(value(p)==l_True) {
                assert(value(pi)==l_True);
                break;
            }
            else if (value(p) == l_False)
                continue;
            simpleUncheckEnqueue(p);
            confl = simplePropagate();
            if (confl != CRef_Undef || softConflictFlag){
                cancelUntilTrailRecord();
                softConflictFlag=false;
                uncheckedEnqueue(~p);
                nfixed++;
                if (propagate() != CRef_Undef  || softConflictFlag)
                    return false;
                setTrailRecord();
            }
            else {
                if(first) {
                    for(int k = trailRecord; k < trail.size(); k++)
                        if(trail[k]!=pi)
                            propLits.push(trail[k]);
                    first = false;
                }
                else{
                    counter++;
                    for(int k = trailRecord; k < trail.size(); k++)
                        seen2[toInt(trail[k])]=counter;
                    assert(seen2[toInt(pi)]==counter);
                    int ii, jj;
                    for (ii = 0, jj = 0; ii < propLits.size(); ii++)
                        if (seen2[toInt(propLits[ii])]==counter)
                            propLits[jj++] = propLits[ii];
                    propLits.shrink(ii - jj);
                }
                cancelUntilTrailRecord();
            }
        }

        if(value(pi)!=l_True && propLits.size()>0) {
            nused++;
            unitSoftLits.push(nonUnitSoftLits[i]);
        }
        else{
            nonUnitSoftLits[ikept++]=nonUnitSoftLits[i];
            continue;
        }

        vec<Lit> newcl(2);
        newcl[0]=~pi;

        for(j = 0; j < propLits.size(); j++){
            newcl[1]=propLits[j];
            if(var(newcl[1])!=var(pi) && value(newcl[1])!=l_True){
                if(value(newcl[0])==l_False){
                    assert(value(newcl[1])!=l_False); //Otherwise conflict detected
                    uncheckedEnqueue(newcl[1]);
                    nfixed++;
                    if (propagate() != CRef_Undef  || softConflictFlag)
                        return false;
                    else if (value(newcl[0]) == l_True)
                        break;
                }
                else{
                    assert(value(newcl[0])==l_Undef);
                    if(value(newcl[1])==l_False){
                        uncheckedEnqueue(newcl[0]);
                        nfixed++;
                        if (propagate() != CRef_Undef  || softConflictFlag)
                            return false;
                        break;
                    }
                    else{
                        CRef cr = ca.alloc(newcl, false);
                        clauses.push(cr);
                        attachClause(cr);
                        nadded++;
                    }
                }
            }
        }
    }
    printf("c Fixed %d and added %d implication bin clauses for %d lits out of %d\n",
           nfixed, nadded, nused, nonUnitSoftLits.size());
    nonUnitSoftLits.shrink(i-ikept);
    return true;
}



void Solver::trimSoftLiterals(){

    fixedCost=0;
    int i, j;
    allSoftLits.clear();
    for(i=0, j=0; i<unitSoftLits.size(); i++) {
        Lit p = unitSoftLits[i];
        if (value(p) == l_Undef) {
            totalCost+=weights[var(p)];
            unitSoftLits[j++] = p;
            allSoftLits.push(p);
        }
        else {
            if (value(p) == l_False)
                fixedCost += weights[var(p)];
            else satCost += weights[var(p)];
            removeSoftLit(p);
        }
    }
    unitSoftLits.shrink(i-j);
    for(i=0, j=0; i<nonUnitSoftLits.size(); i++) {
        Lit p=nonUnitSoftLits[i];
        if (value(p) == l_Undef) {
            totalCost+=weights[var(p)];
            nonUnitSoftLits[j++] = p;
            allSoftLits.push(p);
        }
        else {
            if (value(p) == l_False)
                fixedCost += weights[var(p)];
            else satCost += weights[var(p)];
            removeSoftLit(p);
        }
    }
    nonUnitSoftLits.shrink(i-j);

    nSoftLits=unitSoftLits.size()+nonUnitSoftLits.size();
    weights.copyTo(weightsBckp);

	counter++;
	for(i=0, j=0; i < softLitsPBorder.size(); i++) {
		Lit p=softLitsPBorder[i];
		if (value(p) == l_Undef) {
			Lit q= imply[toInt(p)];
			if (auxiLit(p) && seen2[var(p)] < counter) {
				softLitsPBorder[j++] = p; seen2[var(p)] = counter;
			}
			else if (!auxiLit(p) && q != lit_Undef && seen2[var(q)] < counter && value(q)==l_Undef) {
				softLitsPBorder[j++] = q; seen2[var(q)] = counter;
			}
		}
	}
	softLitsPBorder.shrink(i - j);
	assert(softLitsPBorder.size() == nSoftLits);


	objForSearch = totalCost;
	fixedCostBySearch=fixedCost;
    relaxedCost = 0;

	printf("c fixedCost %llu, satCost %llu, totalFixedVars %d, objForSearch: %llu\n\n",
		   fixedCost, satCost, trail.size(), objForSearch);

	staticNbVars = nVars();
	//At this point, all variables have been created and renamed.
	//Some data structures that had not been used before, especially the ones indexed by var, are now created

	for(int i = 0; i < amos.size(); i++)
		for (int j = 0; j < amos[i].size(); j++)
			amosOfVar[var(amos[i][j])] = i;

    rebuildOrderHeap();
    minWeight=INT64_MAX;
    for(int i = 0; i < nSoftLits; i++) {
        Var v = var(allSoftLits[i]);
        assert(weights[v]>0);
        if(weights[v]<minWeight)
            minWeight=weights[v];
        hardenHeap.insert(v);
    }
}

void Solver::simpleuncheckedEnqueueForLK(Lit p, CRef from){
    assert(value(p) == l_Undef);
    Var v = var(p);
    assigns[v] = lbool(!sign(p)); // this makes a lbool object whose value is sign(p)
    // vardata[x] = mkVarData(from, decisionLevel());
    vardata[v].reason = from;
    vardata[v].level = decisionLevel() + 1;
    trail.push_(p);
}


CRef Solver::simplepropagateForLK() {
    falseVar = var_Undef;
    CRef    confl = CRef_Undef;
    int     num_props = 0;
    watches.cleanAll();
    watches_bin.cleanAll();
    while (qhead < trail.size()) {
        Lit            p = trail[qhead++];     // 'p' is enqueued fact to propagate.
        vec<Watcher>&  ws = watches[p];
        Watcher        *i, *j, *end;
        num_props++;
        // First, Propagate binary clauses
        vec<Watcher>&  wbin = watches_bin[p];

        for (int k = 0; k<wbin.size(); k++) {
            Lit imp = wbin[k].blocker;
            if (value(imp) == l_False) {
                binConfl[0] = ~p; binConfl[1]=imp;
                return CRef_Bin;
                //	return wbin[k].cref;
            }
            if (value(imp) == l_Undef) {
                simpleuncheckedEnqueueForLK(imp, wbin[k].cref);
                if (auxiVar(var(imp)) && value(softLits[var(imp)]) == l_False && !softVarLocked[var(imp)]) {
                    falseVar = var(imp);
                    return CRef_Undef;
                }
            }
        }
        for (i = j = (Watcher*)ws, end = i + ws.size(); i != end;) {
            // Try to avoid inspecting the clause:
            Lit blocker = i->blocker;
            if (value(blocker) == l_True) {
                *j++ = *i++; continue;
            }
            // Make sure the false literal is data[1]:
            CRef     cr = i->cref;
            Clause&  c = ca[cr];
            Lit      false_lit = ~p;
            if (c[0] == false_lit)
                c[0] = c[1], c[1] = false_lit;
            assert(c[1] == false_lit);
            // If 0th watch is true, then clause is already satisfied.
            // However, 0th watch is not the blocker, make it blocker using a new watcher w
            // why not simply do i->blocker=first in this case?
            Lit     first = c[0];
            //  Watcher w     = Watcher(cr, first);
            if (first != blocker && value(first) == l_True){
                i->blocker = first;
                *j++ = *i++; continue;
            }
            assert(c.lastPoint() >=2);
            if (c.lastPoint() > c.size())
                c.setLastPoint(2);
            for (int k = c.lastPoint(); k < c.size(); k++) {
                if (value(c[k]) != l_False) {
                    // watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
                    // the blocker is first in the watcher. However,
                    // the blocker in the corresponding watcher in ~first is not c[1]
                    Watcher w = Watcher(cr, first); i++;
                    c[1] = c[k]; c[k] = false_lit;
                    watches[~c[1]].push(w);
                    c.setLastPoint(k+1);
                    goto NextClause;
                }
            }
            for (int k = 2; k < c.lastPoint(); k++) {
                if (value(c[k]) != l_False) {
                    // watcher i is abandonned using i++, because cr watches now ~c[k] instead of p
                    // the blocker is first in the watcher. However,
                    // the blocker in the corresponding watcher in ~first is not c[1]
                    Watcher w = Watcher(cr, first); i++;
                    c[1] = c[k]; c[k] = false_lit;
                    watches[~c[1]].push(w);
                    c.setLastPoint(k+1);
                    goto NextClause;
                }
            }
            // Did not find watch -- clause is unit under assignment:
            i->blocker = first;
            *j++ = *i++;
            if (value(first) == l_False) {
                confl = cr;
                qhead = trail.size();
                // Copy the remaining watches:
                while (i < end)
                    *j++ = *i++;
            }
            else {
                simpleuncheckedEnqueueForLK(first, cr);
                if (auxiVar(var(first)) && value(softLits[var(first)]) == l_False
                    && !softVarLocked[var(first)]) {
                    qhead = trail.size();
                    // Copy the remaining watches:
                    while (i < end)
                        *j++ = *i++;
                    falseVar = var(first);
                }
            }
            NextClause:;
        }
        ws.shrink(i - j);
        // if (confl == CRef_Undef)
        // 	if (shortenSoftClauses(p))
        // 	  break;
    }
    lk_propagations += num_props;
    return confl;
}


void Solver::simplelookbackResetTrail(CRef confl, bool fromFalseVar) {
	int64_t minISetCost=INT64_MAX;
    if (confl == CRef_Bin) {
        assert(level(var(binConfl[0])) > decisionLevel());
        assert(level(var(binConfl[1])) > decisionLevel());
        seen[var(binConfl[0])] = 1; seen[var(binConfl[1])] = 1;
    }
    else {
        Clause& c = ca[confl];
        if (fromFalseVar) {
			fixBinClauseOrder(c);
			minISetCost=weights[falseVar];
		}

        for(int i=(fromFalseVar ? 1 : 0); i<c.size(); i++) {
            Lit q=c[i]; Var v = var(q);
            if (!seen[v] && level(v) > decisionLevel())
                seen[v]=1;
        }
    }
    int index = trail.size() - 1;
    while (index >= trailRecord) {
        Lit p = trail[index--];
        Var v = var(p);
        if (seen[v]) {
            seen[v] = 0;
            confl = reason(v);
            if (confl == CRef_Undef) {
                conflLits.push(p);      softVarLocked[v]=1;
				if(minISetCost>weights[v])
					minISetCost=weights[v];
            }
            else {
                if (auxiVar(v))
                    insertAuxiVarOrder(v);
                Clause& rc = ca[confl];
                if(!auxiVar(v) || !hardened[v])
				    fixBinClauseOrder(rc);
                for (int j = 1; j < rc.size(); j++){
                    Lit q = rc[j]; Var vv=var(q);
                    if (!seen[vv] && level(vv) > decisionLevel()){
                        seen[vv] = 1;
                    }
                }
            }
        }
        else if (auxiVar(v))
            insertAuxiVarOrder(v);
        assigns[v] = l_Undef;
    }
    qhead = trailRecord;
    trail.shrink(trail.size() - trailRecord);
}


bool Solver::detectInitConflicts() {
    vec<Lit> ps;
    //  int baseLevel = decisionLevel();
    int nbConfl=0, nbLits=0;
    trailRecord = trail.size();
    UBconflictFlag=false; softConflictFlag=false; falseVar = var_Undef;
    LOOKAHEAD++; //newDecisionLevel();
    lastConflLits.clear(); conflLits.clear();
    int i, point=0;
    bool flag=true;
    do {
        if (flag)
            for (i=0; i< nonUnitSoftLits.size(); i++) {
                Lit p = nonUnitSoftLits[i];
                if (value(p) == l_Undef && !softVarLocked[var(p)])
                    simpleuncheckedEnqueueForLK(softLits[var(p)]);
            }
        flag=false;      conflLits.clear();
        for(i=point; i<unitSoftLits.size(); i++) {
            Lit p=unitSoftLits[i];
            if (value(p) == l_Undef && !softVarLocked[var(p)]) {
                simpleuncheckedEnqueueForLK(softLits[var(p)]);
                CRef confl = simplepropagateForLK();
                if (confl != CRef_Undef) {
                    simplelookbackResetTrail(confl, false); nbConfl++;
                    flag=true; point = i;
                    break;
                }
                else if (falseVar != var_Undef) {
                    simplelookbackResetTrail(reason(falseVar), true); nbConfl++;
                    softVarLocked[falseVar]=1;
                    conflLits.push(softLits[falseVar]);
                    falseVar = var_Undef;
                    flag=true; point = i;
                    break;
                }
            }
        }
        if (flag) {
            ps.clear();
            for(int i=0; i<conflLits.size(); i++) {
                Lit p = conflLits[i];
                softVarLocked[var(p)] = 0;
                ps.push(~p);
            }
            if (ps.size() == 1) {
                uncheckedEnqueue(ps[0]);
                if (propagate() != CRef_Undef  || softConflictFlag==true)
                    return false;
            }
            else {
                CRef cr=ca.alloc(ps, false);
                clauses.push(cr);
                attachClause(cr);
            }
            softVarLocked[var(conflLits[0])] = 1; lastConflLits.push(conflLits[0]);
            nbLits += ps.size();
        }
        if (i == unitSoftLits.size() && point > 0)
            point = 0;
    } while (point > 0 || i < unitSoftLits.size());

    for(int i=0; i<lastConflLits.size(); i++)
        softVarLocked[var(lastConflLits[i])] = 0;
    lastConflLits.clear();
    for(int i=trailRecord; i< trail.size(); i++) {
        Var v=var(trail[i]);
        assigns[v] = l_Undef;
    }
    trail.shrink(trail.size() - trailRecord);
    qhead = trailRecord;
    // trail_lim.shrink(1);
    printf("c %d conflict sets found with length %d\n", nbConfl, nbLits);
    return true;
}


Var Solver::pickHardenVar(){
    Var v = hardenHeap.empty() ? var_Undef : hardenHeap[0];
    while(v!=var_Undef && value(v)!=l_Undef){
        hardenHeap.removeMin();
        v = hardenHeap.empty() ? var_Undef : hardenHeap[0];
    }
    return v;
}

//Return true iff some hardenning has happened
bool Solver::harden() {
    assert(laConflictCost+countedWeight<UB);

    bool first=true;
    vec<Lit> learnt_clause;
    int backtrack_level, lbd;
    int64_t lb = UB - countedWeight - laConflictCost;
    Var v = pickHardenVar();
    CRef cr = CRef_Undef;

    while(v!=var_Undef && weights[v]>=lb){
        assert(value(v)==l_Undef);
        if(first){
            nbHardens++;
            analyzeQuasiSoftConflict(learnt_clause, backtrack_level, lbd);
            if (learnt_clause.size() > 0) {
                Lit p = learnt_clause[0];
                if (level(var(p)) < decisionLevel())
                    cancelUntil(level(var(p)));
                assert(level(var(p)) == decisionLevel());

                vec<Lit> hCl;
                hCl.push();
                for(int i = 0; i < learnt_clause.size(); i++)
                    hCl.push(learnt_clause[i]);
                cr = ca.alloc(hCl, true);
                hardens.push(cr);
            }
            else
                cancelUntil(0);
            first=false;
        }
        Lit p = softLits[v];
        uncheckedEnqueue(p, cr);
        if(cr!=CRef_Undef)
            hardened[v]=true;
        fixedByHardens++;
        v = pickHardenVar();
    }
/*#ifndef NDEBUG
    for(Var v = 0; v < nSoftLits; v++)
        assert(value(v)!=l_Undef || laConflictCost+countedWeight+weights[v]<UB);
#endif*/
    return !first;
}


void Solver::cleanClausesForNewVars(vec<CRef>& cs) {
    int i, j;
    for (i = j = 0; i < cs.size(); i++){
        CRef cr = cs[i];
        Clause& c = ca[cr];
        bool sat=false;
        if(c.mark()!=1){
            for (int ii = 0; ii < c.size(); ii++){
                Lit p=c[ii];
                if (value(p) == l_True || dynVar(var(p))) {
                    sat = true;
                    break;
                }
                // Lit p=c[ii];
                // if (value(p) == l_True){
                //   sat = true;
                //   break;
                // }
                //	else if (value(p) == l_Undef && dynVar(var(p)) && !seen[var(p)])
                // seen[var(p)] = 1;
            }
            if (sat)
                removeClause(cr);
                // else {
                // 	int li, lj;
                // 	for (li = lj = 0; li < c.size(); li++){
                // 	  Lit p=c[li];
                // 	  if (value(p) != l_False){
                // 	    c[lj++] = p;
                // 	    if (dynVar(var(p)) && !seen[var(p)])
                // 	      seen[var(p)] = 1;
                // 	  }
                // 	  else assert(li>1);
                // 	}
                // 	if (lj==2) {
                // 	  detachClause(cr, true);
                // 	  c.shrink(li - lj);
                // 	  attachClause(cr);
                // 	}
                // 	else {
                // 	  assert(lj>2);
                // 	  c.shrink(li - lj);
                // 	}
            else cs[j++] = cr;
            // }
        }
    }
    cs.shrink(i - j);
}

void Solver::collectDynVars() {
    cleanClausesForNewVars(learnts_core);
    cleanClausesForNewVars(learnts_tier2);
    cleanClausesForNewVars(learnts_local);
    checkGarbage();
    dynVars.clear();
    int i, j;
    // for(i=0, j=0; i<trail.size(); i++) {
    //   if (dynVar(var(trail[i])))
    //  assigns[var(trail[i])] = l_Undef;
    //   else trail[j++] = trail[i];
    // }
    // trail.shrink(i-j);

    for(i=nVars() - 1; i>=staticNbVars; i--) {
        //  decision[i] = true;
        if (seen[i])
            seen[i] = 0;
        else if (value(i) == l_Undef) {
            dynVars.push(i);
            decision[i]=false;
        }
    }

    rebuildOrderHeap();
    // for(int i=0; i<nVars(); i++)
    //   if (value(i) == l_Undef || level(i) > 0)
    //     assert(!seen[i]);
}

Var Solver::newAuxiVar(bool sign)
{
    if (dynVars.size() > 0) {
        int v=dynVars.last();
        dynVars.pop();
        Lit p = mkLit(v);
        watches_bin[p].clear();
        watches_bin[~p].clear();
        watches[p].clear();
        watches[~p].clear();
        imply[toInt(p)] = lit_Undef;
        imply[toInt(~p)] = lit_Undef;
        decision[v] = false;
        assigns[v] = l_Undef;

        softLits[v] = lit_Undef;
        activityLB[v] = 0;
        weights[v]=0;
        softVarLocked[v]=false;

        score[v]=0;
        tmp_score[v]=0;
        flip_time[v]=0;
        tabu_sattime[v]=0;
        assignsLS[v]=false;
        inClauses[p].clear();
        inClauses[~p].clear();
        neibors[v].clear();
        unsatSVidx[v]=-1;
        arm_n_picks[v]=0;
        Vsoft[v]=1;
        coresOfVar[v].clear();
        hardened[v]=false;
        amosOfVar[v]=-1;

        return v;
    }
    int v = nVars();
    watches_bin.init(mkLit(v, false));
    watches_bin.init(mkLit(v, true ));
    watches  .init(mkLit(v, false));
    watches  .init(mkLit(v, true ));
    assigns  .push(l_Undef);
    vardata  .push(mkVarData(CRef_Undef, 0));
    activity_CHB  .push(0);
    activity_VSIDS.push(rnd_init_act ? drand(random_seed) * 0.00001 : 0);

    picked.push(0);
    conflicted.push(0);
    almost_conflicted.push(0);
#ifdef ANTI_EXPLORATION
    canceled.push(0);
#endif

    seen     .push(0);
    seen2    .push(0);
    seen2    .push(0);
    polarity .push(sign);
    decision .push(false);
    trail    .capacity(v+1);
    //  setDecisionVar(v, dvar);
    decision[v] = false;

    activity_distance.push(0);
    var_iLevel.push(0);
    var_iLevel_tmp.push(0);
    pathCs.push(0);
    imply.push(lit_Undef);
    imply.push(lit_Undef);

    // softWatches.init(mkLit(v, false));
    // softWatches.init(mkLit(v, true));

    // lookaheadCNT.push(0);

    /*

    activityLB.push(0); //SOFT

     //SOFT
    inConflict.push(NON); //SOFT
    unlockReason.push(var_Undef); //SOFT
    inConflicts.push(NON); //SOFT
    */

    conflictLits.init(mkLit(v, false));
    conflictLits.init(mkLit(v, true));
    softLits.push(lit_Undef);
    softVarLocked.push(0);
    activityLB.push(0);
    weights.push(0);

    involved.push(0);

    nbActiveVars.push(-1);
    nbActiveVars.push(-1);

    score.push(0);
    tmp_score.push(0);
    flip_time.push(0);
    tabu_sattime.push(0);
    assignsLS.push(false);
    inClauses.init(mkLit(v, true));
    neibors.init(v);
    unsatSVidx.push(-1);
    arm_n_picks.push(0);
    Vsoft.push(1);
    coresOfVar.init(v);
    hardened.push(false);
    amosOfVar.push(-1);

    rpr.push(lit_Undef);
    rpr.push(lit_Undef);
    
    return v;
}


// create clauses for q1¬x1 + q2¬x2 + ... + qn¬xn <= k
// Precondition: n>k>0
// Should be called only at the root of the search tree
void Solver::addPBConstraints() {

	vec2<int,vec<Lit> > X;
	vec2<int,vec<int64_t> > Q;
	int64_t maxCost=0;

	counter++;
	int nbLits = 0;
	for(int i = 0; i < softLitsPBorder.size(); i++){
		int ii = amosOfVar[var(softLitsPBorder[i])];
        if(ii==-1){
            Lit p = softLitsPBorder[i];
            if(!auxiVar(var(p))) //Soft literal might have been removed
                continue;
            if(value(p)==l_Undef) {
                int64_t w = weights[var(p)];
#ifndef FLAG_NO_HARDEN
                assert(w < UB - countedWeight);
#endif
                if (w < UB - countedWeight) {
                    maxCost+=w;
                    nbLits++;
                    Q.init(Q.size());
                    X.init(X.size());
                    Q[Q.size() - 1].push(w);
                    X[X.size() - 1].push(~p);
                }
                else
                    uncheckedEnqueue(p);
            }
        }
        else {
            if (seen2[ii] < counter) {
                seen2[ii] = counter;
                int64_t amoMax = INT32_MIN;
                vec<Lit> x;
                for (int j = 0; j < amos[ii].size(); j++) {
                    Lit p = amos[ii][j];
                    if(!auxiVar(var(p))) //Soft literal might have been removed
                        continue;
                    if (value(p) == l_Undef) {
                        int64_t w = weights[var(p)];
#ifndef FLAG_NO_HARDEN
                        assert(w < UB - countedWeight);
#endif
                        if (w < UB - countedWeight) {
                            if (w > amoMax)
                                amoMax = w;
                            x.push(p);
                        } else
                            uncheckedEnqueue(~p);
                    }
                }

                if (x.size() > 0) {
                    nbLits += x.size();
                    maxCost += amoMax;
                    Q.init(Q.size());
                    X.init(X.size());
                    for (int k = 0; k < x.size(); k++) {
                        Lit p = x[k];
                        Q[Q.size() - 1].push(weights[var(p)]);
                        X[X.size() - 1].push(p);
                    }
                }
            }
        }
	}


	int64_t K =  UB - 1 - countedWeight;
#ifndef FLAG_ALWAYS_ADDPB
	if (X.size() < 2 || K < 1 || maxCost <= K || nbLits > 5000 || (nbLits > 500 && nbLits*K>100000))
		return;
#else
	if (X.size() < 2 || K < 1 || maxCost <= K)
        return;
#endif

	if(K<50) {
		addPBConstraintMDD(Q, X, K);
		printf("c Added PB MDD for |%d,%d| <= %lld : %d\n",X.size(),nbLits,K,PBC.size());
		GACPBadded=true;
		CCPBadded=true;
	}
	else {
		addPBConstraintGPW(Q, X, K);
		printf("c Added PB GGPW for |%d,%d| <= %lld : %d\n",X.size(),nbLits,K,PBC.size());
		CCPBadded=true;
	}

	//addPBConstraintMTO(Q, X, K);
	rebuildOrderHeap();
}

void Solver::addPBConstraintMTO(vec2<int,vec<int64_t> >& coefs, vec2<int, vec<Lit> > & activeSoftLits, int64_t k){


	int64_t k2 = k;
	int m = activeSoftLits.size(); //Number of variables
	int n = 0; //number of bits
	while (k2) {
		k2 >>= 1;
		++n;
	}

	vec<Lit>  result(n,lit_Undef);
	nLevelsMTO(coefs,activeSoftLits,0,m,result);

	vec<Lit> ps;
	for(int i = n-1; i >= 0; i--){
		if(result[i]!=lit_Undef) {
			ps.push(~result[i]);
			if (!nthBit(k, i)) {
				if (ps.size() == 1)
					uncheckedEnqueue(ps[0]);
				else
					addPBClause(ps);
				ps.pop();
			}
		}
		else if(nthBit(k, i))
			break;
	}
}

void Solver::nLevelsMTO(vec2<int, vec<int64_t> > &q, vec2<int, vec<Lit> > &x, int lIndex, int m, vec<Lit> & result){
	int n = result.size();

	//Base case, leaf
	if(m==1){
		vec<Lit> ps(2);
		for(int i = 0; i < n; i++) {
			bool created=false, used=false;
			for(int j = 0; j < q[lIndex].size(); j++){
				if(nthBit(q[lIndex][j],i)){
					if(used) {
						if (!created) {
							ps[0] = ~result[i];
							ps[1] = mkLit(newAuxiVarForPB());
							result[i]=ps[1];
							addPBClause(ps);
							created=true;
						}
						ps[0] = ~x[lIndex][j];
						ps[1] = result[i];
						addPBClause(ps);
					}
					else{
						result[i] = x[lIndex][j];
						used=true;
					}
				}
			}
		}
	}
        //Recursive case, branch in the binary tree
    else{
        vec<Lit> ps;
        vec<Lit> left(n,lit_Undef), right(n,lit_Undef);
        int lSize = m/2;
        int rSize = m - m/2;
        nLevelsMTO(q,x,lIndex, lSize, left);
        nLevelsMTO(q,x,lIndex+lSize, rSize, right);

        vec<Lit> c(n-1,lit_Undef); //carry

        int h = 0;
        while(h < n-1){
            //====When carry in is false====
            //left and not(carry) -> result
            if(left[h]!=lit_Undef) {
                ps.clear();
                ps.push(~left[h]); ps.push(mtoCreate(c[h])); ps.push(mtoCreate(result[h]));
                addPBClause(ps);
            }

            //right and not(carry) -> result
            if(right[h]!=lit_Undef) {
                ps.clear();
                ps.push(~right[h]);ps.push(mtoCreate(c[h]));ps.push(mtoCreate(result[h]));
                addPBClause(ps);
            }

            //left and right -> carry
            if(left[h]!=lit_Undef && right[h]!=lit_Undef) {
                ps.clear();
                ps.push(~left[h]);ps.push(~right[h]);ps.push(mtoCreate(c[h]));
                addPBClause(ps);
            }

            //====When carry in can exist====
            if(h>0){
                //carryin and not(carry) -> result
                if(c[h-1]!=lit_Undef) {
                    ps.clear(); ps.push(~c[h - 1]);ps.push(mtoCreate(c[h]));ps.push(mtoCreate(result[h]));
                    addPBClause(ps);
                }
                //carryin and left -> carry
                if(left[h]!=lit_Undef && c[h-1]!=lit_Undef){
                    ps.clear();
                    ps.push(~c[h-1]); ps.push(~left[h]); ps.push(mtoCreate(c[h]));
                    addPBClause(ps);
                }

                //carryin and right -> carry
                if(right[h]!=lit_Undef&& c[h-1]!=lit_Undef){
                    ps.clear();
                    ps.push(~c[h-1]); ps.push(~right[h]); ps.push(mtoCreate(c[h]));
                    addPBClause(ps);
                }

                //carryin and left and right -> result
                if(left[h]!=lit_Undef && right[h]!=lit_Undef && c[h-1]!=lit_Undef) {
                    ps.clear();
                    ps.push(~c[h-1]); ps.push(~left[h]); ps.push(~right[h]); ps.push(mtoCreate(result[h]));
                    addPBClause(ps);
                }
            }
            ++h;
        }

        //====Clauses of the uppermost digits====
        // left -> result
        if(left[h]!=lit_Undef) {
            ps.clear();
            ps.push(~left[h]); ps.push(mtoCreate(result[h]));
            addPBClause(ps);
        }

        // right -> result
        if(right[h]!=lit_Undef) {
            ps.clear();
            ps.push(~right[h]); ps.push(mtoCreate(result[h]));
            addPBClause(ps);
        }

        // carryin -> result
        if(h>0 && c[h-1]!=lit_Undef) {
            ps.clear();
            ps.push(~c[h - 1]); ps.push(mtoCreate(result[h]));
            addPBClause(ps);
        }

        // not(left) or not(right)
        if(left[h]!=lit_Undef && right[h]!=lit_Undef) {
            ps.clear();
            ps.push(~left[h]); ps.push(~right[h]);
            addPBClause(ps);
        }

        // not(left) or not(carryin)
        if(left[h]!=lit_Undef && h>0 && c[h-1]!=lit_Undef) {
            ps.clear();
            ps.push(~left[h]); ps.push(~c[h-1]);
            addPBClause(ps);
        }

        // not(right) or not(carryin)
        if(right[h]!=lit_Undef && h>0 && c[h-1]!=lit_Undef) {
            ps.clear();
            ps.push(~right[h]); ps.push(~c[h-1]);
            addPBClause(ps);
        }
    }
}

void Solver::addTotalizer(const vec<Lit> &x, vec<Lit> &y){

	int n = x.size();
	if(n==0){
		y.clear();
		return;
	}
	if(n==1){
		x.copyTo(y);
		return;
	}

	vec2<int,vec<Lit> >  tree;
	tree.init(2*n-2);
	//Fill tree nodes with coefficients
	for(int i = 0; i < n; i++)
		tree[n-1+i].push(x[i]);

	vec<Lit> vl;
	for(int i = n-2; i >= 0; i--)
		addQuadraticMerge(tree[lchild(i)],tree[rchild(i)],tree[i]);

	tree[0].copyTo(y);
}

void Solver::addQuadraticMerge(const vec<Lit> &x1, const vec<Lit> &x2, vec<Lit> &y){
	y.clear();
	if(x1.size()==0)
		x2.copyTo(y);
	else if(x2.size()==0)
		x1.copyTo(y);
	else{
		vec<Lit> vl;
		y.growTo(x1.size() + x2.size());
		for(int i = 0; i < x1.size() + x2.size(); i++)
			y[i] = mkLit(newAuxiVarForPB());
		for(int i = 0; i < x1.size(); i++){
			vl.clear(); vl.push(~x1[i]); vl.push(y[i]);
            addPBClause(vl);
			vl.push();
			for(int j = 0; j < x2.size(); j++) {
				vl[1] = ~x2[j]; vl[2] = y[i + j + 1];
                addPBClause(vl);
			}
		}
		vl.clear();vl.growTo(2);
		for(int i = 0; i < x2.size(); i++) {
			vl[0] = ~x2[i];vl[1] = y[i];
            addPBClause(vl);
		}
	}
}

void Solver::addPBConstraintGPW(vec2<int,vec<int64_t> >& Q, vec2<int,vec<Lit> >& X, int64_t K){

	int n = Q.size();
	K+=1;//This encoding is for < K instead of <= K

	int64_t max = 0;
	for(int i = 0; i < Q.size(); ++i)
		for(int j = 0; j < Q[i].size(); ++j)
			if(Q[i][j] > max)
				max = Q[i][j];

	int64_t p = (int64_t)floor(log2(max));
	int64_t p2 = (int64_t) exp2(p);
	assert(K>=p2);
	int64_t m = K / p2;
	if(K%p2 != 0)
		m++;
	int64_t T = (m*p2) - K;

	vec2<int,vec<Lit>  >  B; //Buckets
	B.init(p);
	vec<Lit> vl(2);

	for(int k = 0; k <= p; k++){
		for(int i = 0; i < n; i++){
			bool used = false;
			bool created = false;
			Lit vk;
			for(int j = 0; j < Q[i].size(); j++){
				if(nthBit(Q[i][j],k)){
					if(!used){
						vk = X[i][j];
						used = true;
					}
					else{
						if(!created){
							Var aux = newAuxiVarForPB();
							vl[0]=~vk; vl[1]=mkLit(aux);
                            addPBClause(vl);
							vk = mkLit(aux);
							created=true;
						}
						vl[0]=~X[i][j]; vl[1]=vk;
                        addPBClause(vl);
					}
				}
			}
			if(used)
				B[k].push(vk);
		}
	}

	vec<Lit> S, Shalf;
	for(int i = 0; i <= p; i++){
		S.clear();
		vec<Lit> U;
		addTotalizer(B[i],U);
		if(i==0)
			U.copyTo(S);
		else
			addQuadraticMerge(U,Shalf,S);

		Shalf.clear();
		for(int j = nthBit(T,i) ? 0 : 1; j < S.size(); j+=2)
			Shalf.push(S[j]);
	}
	uncheckedEnqueue(~S[(int)m-1]);
}

void Solver::addPBConstraintMDD(vec2<int,vec<int64_t> >& Q, vec2<int,vec<Lit> >& X, int k) {
    MDDBuilder builder(Q,k);
    MDD * mdd = builder.getMDD();
    vec<Lit> asserted(mdd->id+1,lit_Undef);

    addPBConstraintMDD(mdd, X, asserted, true);
}

//trueNode means that is either the root node, or a node connected only by 'else' edges to the root
//the auxiliary variable of these node must be true, hence its negation can be removed from clauses
// I.e., trueNode is simulating unit propagation along the else path from the root to True-termial
Lit Solver::addPBConstraintMDD(MDD * mdd, vec2<int,vec<Lit> >& X, vec<Lit> & asserted, bool trueNode){

    //Terminals should never be reached
    assert(mdd->layer!=X.size()+1);

    Lit p=asserted[mdd->id];
    if(p==lit_Undef){
        if(!trueNode) { //if not root node, otherwise root must be true
            Var v = newAuxiVarForPB();
            p = mkLit(v);
            asserted[mdd->id] = p;
        }

        assert(mdd->elsechild!=MDD::MDDFalse()); //Otherwise, node collapsed
        if(mdd->elsechild!=MDD::MDDTrue()) {
            Lit p2 = addPBConstraintMDD(mdd->elsechild, X, asserted, trueNode);
            if(!trueNode) {
                vec<Lit> vp; vp.push(p2); vp.push(~p);
                addPBClause(vp);
            }
        }

        vec<Lit> & x = X[mdd->layer];
        for(int i = 0; i < x.size();i++){
            MDD * c = mdd->children[i];
            if(c!= mdd->elsechild && c!=MDD::MDDTrue()) //Avoid subsumed clauses
            {
                vec<Lit> vp;
                if(!trueNode)
                    vp.push(~p);
                vp.push(~x[i]);
                if(c!=MDD::MDDFalse()) {
                    Lit p2 = addPBConstraintMDD(c, X, asserted, false);
                    vp.push(p2);
                }
                assert(vp.size()>=2);
                //Otherwise, means that is both trueNode and has MDDfalse as child,
                // which can only happen when the weight of a literal is greater than K,
                // which should be filtered in preprocess
                addPBClause(vp);
            }
        }
    }
    return p;
}

Var Solver::newAuxiVarForPB() {
    // return newAuxiVar();
    Var v=newAuxiVar();
    // dynVarsForCardinality.push(v);
    activity_CHB[v] = 0;
    activity_VSIDS[v] = 0;
    // decision[v] = true;
    assigns[v] = l_Undef;
    assert(!auxiVar(v));
    setDecisionVar(v, true);
    // //  if (!order_heap_CHB.inHeap(v))
    //   order_heap_CHB.update(v);
    //   // if (!order_heap_VSIDS.inHeap(v))
    //   order_heap_VSIDS.update(v);
    return v;
}

// void Solver::cleanClausesForNewVars(vec<CRef>& cs) {
//   int i, j;
//   for (i = j = 0; i < cs.size(); i++){
//     CRef cr = cs[i];
//     Clause& c = ca[cr];
//     bool sat=false;
//     if(c.mark()!=1){
//       for (int ii = 0; ii < c.size(); ii++){
//         if (value(c[ii]) == l_True || dynVar(var(c[ii]))) {
// 	  sat = true;
// 	  break;
//         }
//       }
//       if (sat)
//         removeClause(cr);
//       // else {
//       // 	int li, lj;
//       // 	for (li = lj = 0; li < c.size(); li++){
//       // 	  Lit p=c[li];
//       // 	  if (value(p) != l_False){
//       // 	    c[lj++] = p;
//       // 	  }
//       // 	  else assert(li>1);
//       // 	}
//       // 	if (lj==2) {
//       // 	  detachClause(cr, true);
//       // 	  c.shrink(li - lj);
//       // 	  attachClause(cr);
//       // 	}
//       // 	else {
//       // 	  assert(lj>2);
//       // 	  c.shrink(li - lj);
//       // 	}
//       // 	cs[j++] = cr;
//       // }
//     }
//   }
//   cs.shrink(i - j);
// }

// void Solver::collectDynVars() {
//   cleanClausesForNewVars(learnts_core);
//   cleanClausesForNewVars(learnts_tier2);
//   cleanClausesForNewVars(learnts_local);
//   cleanClausesForNewVars(hardens);
//   checkGarbage();
//   dynVars.clear();
//   for(int i=nVars() - 1; i>=staticNbVars; i--) {
//     // if (seen[i])
//     //   seen[i] = 0;
//     // else
//       dynVars.push(i);
//   }
// }

// static bool switch_mode = false;
// #define switch_time 1800

// #ifdef _MSC_VER_Sleep
// void sleep(int time)
// {
//     Sleep(time * 1000);
//     switch_mode = true;
//     printf("switch_mode = true\n");
// }

// #else

// static void SIGALRM_switch(int signum) { switch_mode = true; }
// #endif

// NOTE: assumptions passed in member-variable 'assumptions'.
lbool Solver::solve_()
{
// #ifdef _MSC_VER_Sleep
//     std::thread t(sleep, switch_time);
//     t.detach();
// #else
//     signal(SIGALRM, SIGALRM_switch);
//     alarm(switch_time);
// #endif

    model.clear(); usedClauses.clear();
    conflict.clear();
    if (!ok) return l_False;

    solves++;

    max_learnts               = nClauses() * learntsize_factor;
    learntsize_adjust_confl   = learntsize_adjust_start_confl;
    learntsize_adjust_cnt     = (int)learntsize_adjust_confl;
    lbool   status            = l_Undef;

    if (verbosity >= 1){
        printf("c ============================[ Search Statistics ]==============================\n");
        printf("c | Conflicts |          ORIGINAL         |          LEARNT          | Progress |\n");
        printf("c |           |    Vars  Clauses Literals |    Limit  Clauses Lit/Cl |          |\n");
        printf("c ===============================================================================\n");
    }

    addHardClausesForSoftClauses();

    add_tmp.clear(); softConflictFlag=false; next_C_reduce = 0;
    UBconflictFlag=false; softConflictFlag=false; falseVar = var_Undef;
    LOOKAHEAD = 0; lk_propagations=0; nbLKsuccess=0;
    stepSizeLB = 0.4;  subconflicts = 0;
    totalPrunedLB=0; totalPrunedLB2=0; 	derivedCost=0; feasible=false;
    nbHardens=0; fixedByHardens=0;  nbSavedLits = 0;
    savedLOOKAHEAD=0; savednbLKsuccess=0; rootConflCost=0; laConflictCost=0;
	fixedCost=0; countedWeight=0; satisfiedWeight=0;//hardenBeginningIndex=0;
    //constraintRelaxed = false;

    infeasibleUB = 0;

    UB = totalWeight-solutionCost+1;
	if(initUB<INT64_MAX){
        if(solutionCost > initUB) {
            printf("c problem solved by preprocessing\n");
            return l_False;
        }
        else
		    UB=initUB-solutionCost+1;
	}
    WithNewUB = false;


    if (!simplifyOriginalClauses(clauses)){
#ifdef BIN_DRUP
        if (drup_file) binDRUP_flush(drup_file);
#endif
        return l_False;
    }

    allSoftLits.copyTo(softLitsPBorder);

	/*if (!findImplications()) {
		printf("c problem solved by preprocessing\n");
		return l_False;
	}*/

	if (!findConflictSoftLits()) {
		printf("c problem solved by preprocessing\n");
		return l_False;
	}

	if (!findAMOs()) {
		printf("c problem solved by preprocessing\n");
		return l_False;
	}

	/*
    if (!detectInitConflicts()) {
      printf("c problem solved by preprocessing2\n");
      return l_False;
    }*/

    trimSoftLiterals();

    int beginning = trail.size();
    falseLits.clear();
    //hardenLevel = INT32_MAX;

	int64_t inf=0;
	if(nSoftLits>0){
	//	assert(weights[var(softLitsWeightOrder.last())]>0);
	//	inf=weights[var(softLitsWeightOrder.last())]-1;
        assert(minWeight>0);
        inf=minWeight-1;
	}

    if (initLB >= solutionCost+fixedCostBySearch+derivedCost+relaxedCost) {
        infeasibleUB= initLB  -(solutionCost+fixedCostBySearch+derivedCost + relaxedCost);
        printf("c provided LB: %llu\n", infeasibleUB);
    }

	//infeasibleUB = lookaheadComputeInitLB();
	if(infeasibleUB>inf)
		inf=infeasibleUB;

	int64_t sup= objForSearch+1; //make sure UB=objForSearch+1 is tested
    int64_t providedUB = totalCost+1;
    countedWeight=0;
	satisfiedWeight=0;

    if (initUB <  INT64_MAX) {
        if (initUB >= solutionCost+fixedCostBySearch+derivedCost+relaxedCost) {
            providedUB = initUB - (solutionCost+fixedCostBySearch+derivedCost + relaxedCost) + 1;
            //	sup=UB; feasible=true;
            printf("c provided UB: %llu\n", providedUB);
        }
        else {
            printf("c local search UB proved optimum by preprocessing\n");
            return l_False;
        }
    }
    else
        printf("c no UB provided, search from scratch...\n");

#ifdef FLAG_UPDOWN
	UB=providedUB;
	printf("c Starting from TOP\n");
#else
    UB=inf+1;
	printf("c Starting from BOTTOM\n");
#endif
    printf("c start search at %llu\n",UB);
	int nbVSIDSphase=0, nbLRBphase=0;
    do {
        status            = l_Undef;
        add_tmp.clear(); softConflictFlag=false;
        UBconflictFlag=false; softConflictFlag=false; falseVar = var_Undef;
        fflush(stdout);


        VSIDS = true;
        int init = 10000;
        while (status == l_Undef && init > 0 && !feasible /* && !feasible && !switch_mode && withinBudget()*/)
            status = search(init);
        printf("c ends of initiationization by VSIDS at %llu conflicts with init %d\n\n",
               conflicts, init);
        //  if (!switch_mode)
        VSIDS = false;

        // Search:
        uint64_t phase_allotment=20000000;
        int curr_restarts = 0;
        for(; status == l_Undef ;) {

            //	uint64_t budget = phase_allotment;
            uint64_t savedUP = propagations;
            uint64_t savedConfl = conflicts;
            uint64_t savedRestarts = starts;

            fflush(stdout);

            while (status == l_Undef && propagations - savedUP < phase_allotment) {
                if (VSIDS) {
                    int weighted = INT32_MAX;
                    status = search(weighted);
                }
                else{
                    int nof_conflicts = luby(restart_inc, curr_restarts) * restart_first;
                    curr_restarts++;
                    status = search(nof_conflicts);
                }
            }
            if (VSIDS) {
                nbVSIDSphase++;
                printf("c VSIDS phase %d: conflicts %llu, phase %llu, starts %llu, UP %llu\n",
                       nbVSIDSphase, conflicts-savedConfl, phase_allotment,
                       starts-savedRestarts, propagations-savedUP);
            }
            else  {
                nbLRBphase++;
                printf("c LRB phase %d: conflicts %llu, phase %llu, starts %llu, UP %llu\n",
                       nbLRBphase, conflicts-savedConfl, phase_allotment,
                       starts-savedRestarts, propagations-savedUP);
            }

            // if (status != l_Undef /*|| !withinBudget()*/)
            //     break; //
            //Should break here for correctness in incremental SAT solving.

            VSIDS = !VSIDS;
            if (!VSIDS)
                phase_allotment *= 2;

	    if (status==l_Undef && feasible && equivLits.size()>prevEquivLitsNb && !eliminateEqLits()) {
	      status=l_False;
	    }
        }
        assert(status != l_Undef);
        float meanLB=0, dev=0, succRate=0;
        if (nbLKsuccess>savednbLKsuccess) {
            meanLB= (float)totalPrunedLB/(nbLKsuccess-savednbLKsuccess);
            dev = sqrt((float)totalPrunedLB2/(nbLKsuccess-savednbLKsuccess) - meanLB*meanLB);
        }
        if (LOOKAHEAD > savedLOOKAHEAD)
            succRate = (float) (nbLKsuccess-savednbLKsuccess)/(LOOKAHEAD-savedLOOKAHEAD);
        if (status == l_False) {
            printf("c UB=%llu fails, cnfls=%llu, hcnfls=%llu, lacnfls=%llu, lascnfls=%llu, core %d, tier2 %d, local %d, quasiC: %llu (fixed: %llu)\n",
                   UB, conflicts, conflicts-softConflicts, la_conflicts, la_softConflicts, learnts_core.size(), learnts_tier2.size(), learnts_local.size(), quasiSoftConflicts, fixedByQuasiConfl);
            printf("c prunedLB %4.2f, dev %4.2f, succRate %4.2f, nbSucc %llu, nbHardens %d (fixed %llu), lk: %llu, shorten: %llu, pureSo %d, nbFlyRd %d, nbFixedLH %llu\n",
                   meanLB, dev, succRate,
                   nbLKsuccess-savednbLKsuccess, nbHardens, fixedByHardens, LOOKAHEAD-savedLOOKAHEAD, nbSavedLits, pureSoftConfl, nbFlyReduced, nbFixedByLH);
            if (infeasibleUB < UB)
                infeasibleUB = UB;
            if (feasible) {
                sup = UB;
                break;
            }
            cancelUntilBeginning(beginning);
            next_C_reduce = 0;
            next_L_reduce = 0; next_T2_reduce=0; subconflicts = 0; curSimplify = 1; nbconfbeforesimplify=1000;
            totalPrunedLB=0; totalPrunedLB2=0; savedLOOKAHEAD = LOOKAHEAD; savednbLKsuccess=nbLKsuccess;
            inf = UB;

			if (UB<8) {
				if (2*UB < (inf + sup+1)/2)
					UB = 2*UB;
				else   UB = (inf + sup+1)/2;
			}
			else {
				if (3*UB/2 < (inf + sup+1)/2)
					UB = 3*UB/2;
				else
					UB = (inf + sup+1)/2;
			}
			if (UB > providedUB)
				UB = providedUB;

            removeLearntClauses();
            rebuildOrderHeap();
        }
        else if (status == l_True) {
            int nbFixeds = trail_lim.size() == 0 ? 0 : trail_lim[0];
            int nbFalses = falseLits_lim.size() == 0 ? 0 : falseLits_lim[0];
            printf("c UB=%llu succ, confls=%llu , hconfls=%llu,  laconfls=%llu, lasconfls=%llu with %d soft clauses unsat (%d at level 0) and %d fixed vars at level 0,  prunedLB %4.2f, dev %4.2f, succRate %4.2f, nbSucc %llu, shortened : %llu\n",
                   UB, conflicts, conflicts-softConflicts, la_conflicts, la_softConflicts, falseLits.size(), nbFalses, nbFixeds,
                   meanLB, dev, succRate, nbLKsuccess, nbSavedLits);
            //assert(UB > falseLits.size());
            checkSolution();
            feasible = true;
            // sup = falseLits.size();
            // UB = (inf + sup+1)/2;
            // cancelUntilBeginning(beginning);
            // next_C_reduce = 0;
            // next_L_reduce = 0; next_T2_reduce=0; subconflicts = 0; curSimplify = 1; nbconfbeforesimplify=1000;
            // removeLearntClauses();
            totalPrunedLB=0; totalPrunedLB2=0; WithNewUB=true; //curSimplify = 1; nbconfbeforesimplify=1000;
            savedLOOKAHEAD = LOOKAHEAD; savednbLKsuccess=nbLKsuccess;
            sup = countedWeight;
            cancelUntil(0);
            fixedCostBySearch += countedWeight; beginning = trail.size();
            for (int i=0; i < learnts_local.size(); i++)
                removeClause(learnts_local[i]);
            learnts_local.clear();
            for (int i=0; i < learnts_tier2.size(); i++)
                removeClause(learnts_tier2[i]);
            learnts_tier2.clear();
            watches.cleanAll();
            watches_bin.cleanAll();
            checkGarbage();

            sup -= countedWeight; //reduce the number of false lits at level 0
			if (inf > countedWeight)
                inf -= countedWeight;
            else inf=0;
            UB = (inf + sup+1)/2;
            falseLits.clear();
            countedWeight=0;
			satisfiedWeight=0;
            rebuildOrderHeap();
            //simplify();
        }
        else printf("c error UB %llu, inf %llu, sup %llu\n", UB, inf, sup);
    } while (UB > inf);

    if (verbosity >= 1)
        printf("c ===============================================================================\n");

#ifdef BIN_DRUP
    if (drup_file && status == l_False) binDRUP_flush(drup_file);
#endif

    // if (status == l_True){
    //     // Extend & copy model:
    //     model.growTo(nVars());
    //     for (int i = 0; i < nVars(); i++) model[i] = value(i);
    // }else if (status == l_False && conflict.size() == 0)
    //     ok = false;
    if (sup == objForSearch+1)
        printf("c no feasible solution, hardConflicts: %llu\n", conflicts - softConflicts);
    else
        printf("c initCost: %llu, fixedBySearch: %llu, optimal: %llu, maxsat: %llu, hardConflicts: %llu\n",
               solutionCost, fixedCostBySearch,
               solutionCost+sup+fixedCostBySearch+derivedCost + relaxedCost,
               objForSearch-sup + satCost, conflicts - softConflicts);
    printf("c nbLK: %llu, nbSuccLK: %llu(%4.2f%%), nbLKup: %llu(%4.2f%%), hardens %u (fixed %llu), dynVars %d, shorten: %llu\n",
           LOOKAHEAD, nbLKsuccess, 100.0*nbLKsuccess/LOOKAHEAD, lk_propagations,
           100.0*lk_propagations/propagations, nbHardens, fixedByHardens, nVars()-staticNbVars, nbSavedLits);

    // printf("v ");
    // for (int i = 0; i < nVars(); i++)
    //   if (model[i] == l_True)
    // 	printf("%d ", 2*i);
    //   else if (model[i] == l_False)
    // 	printf("%d ", 2*i+1);
    //   // if (model[i] != l_Undef)
    //   // 	printf("%s%s%d", (i==0)?"":" ", (model[i]==l_True)?"":"-", i+1);
    // printf(" 0\n");

    cancelUntil(0);

#ifndef NDEBUG
    for(int i=0; i < nSoftLits; ++i){
        assert(weights[i]==weightsBckp[i]);
    }
#endif
    
    if (feasible)
      optimal = solutionCost+sup+fixedCostBySearch+derivedCost + relaxedCost;

    return feasible ? l_True  : l_False;
}


//=================================================================================================
// Garbage Collection methods:

void Solver::relocAll(ClauseAllocator& to)
{
    // All watchers:
    //
    // for (int i = 0; i < watches.size(); i++)
    watches.cleanAll();
    watches_bin.cleanAll();
    for (int v = 0; v < nVars(); v++)
        for (int s = 0; s < 2; s++){
            Lit p = mkLit(v, s);
            // printf(" >>> RELOCING: %s%d\n", sign(p)?"-":"", var(p)+1);
            vec<Watcher>& ws = watches[p];
            for (int j = 0; j < ws.size(); j++)
                ca.reloc(ws[j].cref, to);
            vec<Watcher>& ws_bin = watches_bin[p];
            for (int j = 0; j < ws_bin.size(); j++)
                ca.reloc(ws_bin[j].cref, to);
        }

    // All reasons:
    //
    for (int i = 0; i < trail.size(); i++){
        Var v = var(trail[i]);

        if (reason(v) != CRef_Undef && (!auxiVar(v) || !hardened[v]) && (ca[reason(v)].reloced() || locked(ca[reason(v)])))
            ca.reloc(vardata[v].reason, to);
    }

    // All learnt:
    //
    for (int i = 0; i < learnts_core.size(); i++)
        ca.reloc(learnts_core[i], to);
    for (int i = 0; i < learnts_tier2.size(); i++)
        ca.reloc(learnts_tier2[i], to);
    for (int i = 0; i < learnts_local.size(); i++)
        ca.reloc(learnts_local[i], to);

    // All original:
    //
    int i, j;
    for (i = j = 0; i < clauses.size(); i++)
        if (ca[clauses[i]].mark() != 1){
            ca.reloc(clauses[i], to);
            clauses[j++] = clauses[i]; }
    clauses.shrink(i - j);

    // // All original used clauses
    // for (i = j = 0; i < usedClauses.size(); i++)
    //     if (ca[usedClauses[i]].mark() != 1){
    //         ca.reloc(usedClauses[i], to);
    //         usedClauses[j++] = usedClauses[i]; }
    // usedClauses.shrink(i - j);

    // //all soft watchers

    // softWatches.cleanAll();
    // for (int v = 0; v < nVars(); v++)
    //   for (int s = 0; s < 2; s++){
    // 	Lit p = mkLit(v, s);
    // 	// printf(" >>> RELOCING: %s%d\n", sign(p)?"-":"", var(p)+1);
    // 	vec<softWatcher>& ws = softWatches[p];
    // 	for (int j = 0; j < ws.size(); j++)
    // 	  ca.reloc(ws[j].cref, to);
    //   }

    for (i = j = 0; i < softClauses.size(); i++)
        if (ca[softClauses[i]].mark() != 1){
            ca.reloc(softClauses[i], to);
            softClauses[j++] = softClauses[i]; }
    softClauses.shrink(i - j);

    for (i = j = 0; i < hardSoftClauses.size(); i++)
        if (ca[hardSoftClauses[i]].mark() != 1){
            ca.reloc(hardSoftClauses[i], to);
            hardSoftClauses[j++] = hardSoftClauses[i]; }
    hardSoftClauses.shrink(i - j);

    for (i = j = 0; i < falseSoftClauses.size(); i++)
        if (ca[falseSoftClauses[i]].mark() != 1){
            ca.reloc(falseSoftClauses[i], to);
            falseSoftClauses[j++] = falseSoftClauses[i]; }
    falseSoftClauses.shrink(i - j);

    for(i=0; i<hardens.size(); i++)
        ca.reloc(hardens[i], to);

    for(i=0; i<nSoftLits; i++)
        if(hardened[var(allSoftLits[i])])
            ca.reloc(vardata[var(allSoftLits[i])].reason, to);


    for(i=0, j=0; i<softLearnts.size(); i++)
        if (ca[softLearnts[i]].mark() != 1){
            ca.reloc(softLearnts[i], to);
            softLearnts[j++] = softLearnts[i];
        }
    softLearnts.shrink(i - j);

    for(i=0, j=0; i<hardLearnts.size(); i++)
        if (ca[hardLearnts[i]].mark() != 1){
            ca.reloc(hardLearnts[i], to);
            hardLearnts[j++] = hardLearnts[i];
        }
    hardLearnts.shrink(i - j);

    for(i=0, j=0; i < PBC.size(); i++)
        if (ca[PBC[i]].mark() != 1){
            ca.reloc(PBC[i], to);
            PBC[j++] = PBC[i];
        }
    PBC.shrink(i - j);

    for(i=0, j=0; i<isetClauses.size(); i++)
        if (ca[isetClauses[i]].mark() != 1){
            ca.reloc(isetClauses[i], to);
            isetClauses[j++] = isetClauses[i];
        }
    isetClauses.shrink(i - j);

    // for(i=0; i<clausesLS.size(); i++) {
    //   assert(ca[clausesLS[i].cr].mark()!=1);
    //   ca.reloc(clausesLS[i].cr, to);
    // }

    ca.reloc(bwdsub_tmpunit, to);

    // printf("c **** garbage collection done ****\n");
}


void Solver::garbageCollect()
{
    // Initialize the next region to a size corresponding to the estimated utilization degree. This
    // is not precise but should avoid some unnecessary reallocations for the new region:
    ClauseAllocator to(ca.size() - ca.wasted());

    relocAll(to);
    // if (verbosity >= 2)
    // printf("c |  Garbage collection:   %12d bytes => %12d bytes             |\n",
    //        ca.size()*ClauseAllocator::Unit_Size, to.size()*ClauseAllocator::Unit_Size);
    to.moveTo(ca);
}


//=================================================================================================
// Writing CNF to DIMACS:
//
// FIXME: this needs to be rewritten completely.

static Var mapVar(Var x, vec<Var>& map, Var& max)
{
	if (map.size() <= x || map[x] == -1){
		map.growTo(x+1, -1);
		map[x] = max++;
	}
	return map[x];
}


void Solver::toDimacs(FILE* f, Clause& c, vec<Var>& map, Var& max)
{
	if (satisfied(c)) return;

	for (int i = 0; i < c.size(); i++)
		if (value(c[i]) != l_False)
			fprintf(f, "%s%d ", sign(c[i]) ? "-" : "", mapVar(var(c[i]), map, max)+1);
	fprintf(f, "0\n");
}


void Solver::toDimacs(const char *file, const vec<Lit>& assumps)
{
	FILE* f = fopen(file, "wr");
	if (f == NULL)
		fprintf(stderr, "could not open file %s\n", file), exit(1);
	toDimacs(f, assumps);
	fclose(f);
}


void Solver::toDimacs(FILE* f, const vec<Lit>& assumps)
{
	// Handle case when solver is in contradictory state:
	if (!ok){
		fprintf(f, "p cnf 1 2\n1 0\n-1 0\n");
		return; }

	vec<Var> map; Var max = 0;

	// Cannot use removeClauses here because it is not safe
	// to deallocate them at this point. Could be improved.
	int cnt = 0;
	for (int i = 0; i < clauses.size(); i++)
		if (!satisfied(ca[clauses[i]]))
			cnt++;

	for (int i = 0; i < clauses.size(); i++)
		if (!satisfied(ca[clauses[i]])){
			Clause& c = ca[clauses[i]];
			for (int j = 0; j < c.size(); j++)
				if (value(c[j]) != l_False)
					mapVar(var(c[j]), map, max);
		}

	// Assumptions are added as unit clauses:
	cnt += assumptions.size();

	fprintf(f, "p cnf %d %d\n", max, cnt);

	for (int i = 0; i < assumptions.size(); i++){
		assert(value(assumptions[i]) != l_False);
		fprintf(f, "%s%d 0\n", sign(assumptions[i]) ? "-" : "", mapVar(var(assumptions[i]), map, max)+1);
	}

	for (int i = 0; i < clauses.size(); i++)
		toDimacs(f, ca[clauses[i]], map, max);

	if (verbosity > 0)
		printf("c Wrote %d clauses with %d variables.\n", cnt, max);
}
