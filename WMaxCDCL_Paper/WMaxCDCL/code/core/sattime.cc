#include "mtl/Sort.h"
#include "core/Solver.h"
#include "utils/System.h"
#include "float.h"
#include <chrono>

using namespace Minisat;

// sattime functions

#define noRedundant -7
#define redundant -77
#define newRedundant -777
#define oldRedundant -7777

#define FALSE 0
#define TRUE 1


#define ARMNUM 20
#define LAMBDA 1
#define GAMMA 0.9
#define D_WINDOW 20

inline bool Solver::litSatisfiedLS(Lit l) {
  return sign(l) != assignsLS[var(l)];
}

// use the nbTrue and lastSatVar slots for redundant clause detecting
// If the new clause is redundant, then return newRedundant, else return
// the number of redundant old clauses
int Solver::mark_redundant_clause(int cIndex, vec<int>& involved) {
	int i, j, count=0;
	// initialize involved count of each clause to 0
	for(i=0; i<involved.size(); i++)
		clausesLS[involved[i]].setNbTrue(0);
	involved.shrink_(involved.size());
	CRef cr=clauses[cIndex];
	ClauseLS& cls=clausesLS[cIndex];
	Clause& c = ca[cr];
	for(j=0; j<c.size(); j++) {
		// inClauses[c[j]] is a list of no of clauses containing c[j]
		vec<CRefLS>& ks=inClauses[c[j]];
		for(int k=0; k<ks.size(); k++) {
			ClauseLS& kcls=clausesLS[ks[k]];
			if (kcls.lastSatVar() != redundant) {
				if (kcls.nbTrue()==0)
					involved.push(ks[k]);
				kcls.setNbTrue(kcls.nbTrue()+1);
				if (kcls.nbTrue()==ca[kcls.cr].size()) {
					cls.setLastSatVar(redundant);
					return newRedundant;
				}
				if (j==c.size()-1 && kcls.nbTrue()==c.size()) {
					kcls.setLastSatVar(redundant);
					count++;
					//  return oldRedundant;
				}
			}
		}
	}
	return count;
}

bool Solver::cleanClause(CRef cr) {
  if (removed(cr))
    return false;
  bool sat=false, false_lit=false; //pboVar=false;
  Clause& c=ca[cr];
  for (int i = 0; i < c.size(); i++){
    if (level(var(c[i])) == 0) {
      if (value(c[i]) == l_True){
	sat = true;
	break;
      }
      else if (value(c[i]) == l_False){
	false_lit = true;
      }
    }
    // else if (var(c[i]) >= staticNbVars)
    // 	pboVar=true;
  }
  if (sat){
    removeClause(cr);
    return false;
  }
  else{
    if (false_lit){
      int li, lj;
      for (li = lj = 0; li < c.size(); li++){
	if (level(var(c[li])) > 0 || value(c[li]) != l_False){
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
      c.calcAbstraction();
    }
    return true;
  }
  // if (pboVar)
  //   return false;
  // else return true;
}

void Solver::attachClauseForSattime(CRef cr) {
	CRefLS i = clausesLS.size();
	clausesLS.push(ClauseLS(cr));
	ClauseLS& cls=clausesLS.last();
	cls.setNbTrue(0); cls.setCriVar(0); cls.setLastSatVar(-1);
	cls.setMostRecent(-1); cls.setUnSATindex(-1);
	Clause& c = ca[cr];
	int  szGT0=0;
	for(int j=0; j<c.size(); j++) {
	  //	if (level(var(c[j])) > 0) {
	  inClauses[c[j]].push(i);
	  //		szGT0++;
	  //	}
	}
	//	cls.setGt0size(szGT0);
}

void Solver::clearInClausesLists() {
	int i;
	for(i=0; i<staticNbVars; i++) {
		Lit p=mkLit(i, false);
		inClauses[p].shrink_(inClauses[p].size());
		inClauses[~p].shrink_(inClauses[~p].size());
	}
}

bool Solver::satisfiedAtLevel0(CRef cr){
	Clause & c = ca[cr];
	for(int i=0; i < c.size(); i++)
		if(value(c[i])==l_True && level(var(c[i]))==0)
			return true;
	return false;
}

void Solver::attachClausesForSattime(vec<CRef> & clauses) {
  int i, j;
  for(i=0, j=0; i<clauses.size(); i++) {
    CRef cr = clauses[i];
    if(cleanClause(cr)) {
      attachClauseForSattime(cr);
      clauses[j++] = cr;
    }
  }
  clauses.shrink(i-j);
}

void Solver::clause_value() {
	int i, j, nb, cri;
	for (i=0; i<clausesLS.size(); i++) {
		ClauseLS& cls=clausesLS[i];
		Clause& c=ca[cls.cr];
		nb=0; cri=0;
		for(j=0; j<c.size(); j++)
			if (sign(c[j]) == !assignsLS[var(c[j])]) {
				nb++; cri+=var(c[j]);
			}
		cls.setNbTrue(nb); cls.setCriVar(cri);
		if (nb==0) {
			cls.setUnSATindex(unSAT.size());
			unSAT.push(i);
		}
	}
}

void Solver::getNeibors(int v) {
	int i, j;
	counter++;
	// in minisat, literal is positive with "false" in mkLit
	// to make the positive literal represented by even number
	Lit p=mkLit(v, false);
	vec<CRefLS>& poscs=inClauses[p];
	for(i=0; i<poscs.size(); i++) {
		Clause& c=ca[clausesLS[poscs[i]].cr];
		for(j=0; j<c.size(); j++) {
			if (v!=var(c[j]) && seen2[var(c[j])] !=counter) {
				seen2[var(c[j])]=counter;
				neibors[v].push(var(c[j]));
			}
		}
	}
	Lit q=mkLit(v, true);
	vec<CRefLS>& negcs=inClauses[q];
	for(i=0; i<negcs.size(); i++) {
		Clause& c=ca[clausesLS[negcs[i]].cr];
		for(j=0; j<c.size(); j++) {
			if (v!=var(c[j]) && seen2[var(c[j])] !=counter) {
				seen2[var(c[j])]=counter;
				neibors[v].push(var(c[j]));
			}
		}
	}
}

void Solver::getNeibors() {
	for(Var i=0; i<staticNbVars; i++)
		if (level(i) > 0)
			getNeibors(i);
}

// // p is in each clause in cs
// int Solver::getGradient(Lit& p, vec<CRef>& cs) {
//   int i, nb;
//   nb=0;
//   if (assignsSL[var(p)]!=sign(p))
//     for(i=0; i<cs.size(); i++) {
//       Clause& c=ca[cs[i]];
//       if (c.nbTrue()==1)
// 	nb++;
//     }
//   else
//     for(i=0; i<cs.size(); i++) {
//       Clause& c=ca[cs[i]];
//       if (c.nbTrue()==0)
// 	nb++;
//     }
//   return nb;
// }

int Solver::getVarScore(int v) {

	int nbP, nbnonP, i;
	Lit p=mkLit(v, !assignsLS[v]);
	vec<CRefLS>& cs1=inClauses[p]; nbP=0;
	for(i=0; i<cs1.size(); i++) {
		ClauseLS& cls=clausesLS[cs1[i]];
		if (cls.nbTrue()==1)
			nbP++; // nb of clauses satisfied only by p
	}
	vec<CRefLS>& cs2=inClauses[~p]; nbnonP=0;
	for(i=0; i<cs2.size(); i++) {
		ClauseLS& cls=clausesLS[cs2[i]];
		if (cls.nbTrue()==0)
			nbnonP++;//nb of clauses that would become satisfied if p is flipped
	}
	return nbnonP-nbP;
}

int Solver::random_integer(int max)
{
	unsigned long int RAND;
	RAND=rand();
	return RAND % max;
}

void Solver::modify_seed() {
	int seed;
	if (SEED_FLAG) {
		srand(SEED); SEED=SEED+17;
		if (SEED==0) SEED=17;
	}
	else {
		auto now = std::chrono::high_resolution_clock::now().time_since_epoch();
		auto micros = std::chrono::duration_cast<std::chrono::microseconds>(now).count();
		seed = static_cast<int>(micros & 0x7fffffff);
		srand(seed);
	}
}

void Solver::initialize() {
	int i, j, nb, cri;
	bool satAt0;

	modify_seed();
	decrVars.clear();
	unSAT.clear();
	unsatSV.clear();
	// compute (and set) the number of satisfied lits, crivar,
	//and collect unsat clauses
	for (i=0; i<clausesLS.size(); i++) {
		ClauseLS& cls=clausesLS[i];
		Clause& c=ca[cls.cr];
		nb=0; cri=0; satAt0=false;
		for(j=0; j<c.size(); j++) {
		  //	if (level(var(c[j])) > 0 && value(c[j]) == l_True) {
		  if (value(c[j]) == l_Undef && sign(c[j]) == polarity[var(c[j])]) {
				nb++;
				cri += var(c[j]);
			}
			// else if(value(c[j]) == l_True) {
			// 	satAt0=true;
			// }
		}
		assert(!satAt0);
		cls.setNbTrue(nb);
		cls.setCriVar(cri);
		if (nb == 0) {
			cls.setUnSATindex(unSAT.size());
			unSAT.push(i);
		}
	}
	// compute the score of each var and collect decVars
	cost = countedWeight;
	for(i=0; i<staticNbVars; i++) {
	  //	if(level(i)>0) {
	  if(value(i) == l_Undef) {
	    //	assert(value(i) != l_Undef);
			flip_time[i] = 0;
			tmp_score[i] = 0;
			assignsLS[i] = !polarity[i]; //assigns[i] == l_True;
			score[i]= getVarScore(i);

			int totalC = inClauses[mkLit(i, false)].size() + inClauses[mkLit(i, true)].size();
			assert(-totalC<=score[i] && score[i] <= totalC);
			if (auxiVar(i)) {
				if (assignsLS[i] == sign(softLits[i])) {
					unsatSVidx[i] = unsatSV.size();
					unsatSV.push(i);
					cost += weights[var(softLits[i])];
				} else
					unsatSVidx[i] = -1;
				//	arm_n_picks[i]=0;
				//	Vsoft[i]=1;
			}
			if (score[i]>0 && (!auxiVar(i) || softScore(i) > 0))
				decrVars.push(i);
		}
		// if (auxiVar(i) &&
		//     ((value(i) == l_Undef && sign(softLits[i]) == assignsLS[i]) ||
		//      (value(i) != l_Undef && value(softLits[i]) == l_False)))
		//   cost += weights[var(softLits[i])];
	}
}

int Solver::diversifyForUneven(CRefLS crls, Var best_v) {
	int flip_index, i, nb;
	CRef cr = clausesLS[crls].cr;
	Clause& c=ca[cr];
	int gt0size = clausesLS[crls].gt0size();
	//	flip_index=random_integer(gt0size-1); nb=0;
	flip_index=random_integer(c.size()-1); nb=0;
	for(i=0; i<c.size(); i++) {
		if (best_v != var(c[i])) {
			if (nb==flip_index)
				return var(c[i]);
			else nb++;
		}
	}
	assert(0);
	return best_v;   // not useful, just for avoiding compiling warning
}

inline bool Solver::betterThan(Var v0, Var v1) {
  int nb0, nb1;
  int64_t softNb0, softNb1;
  nb0 = score[v0];   nb1 = score[v1]; softNb0 = softScore(v0); softNb1 = softScore(v1); 
  return ((nb0 > nb1) ||
	  ((nb0 == nb1) && (softNb0 > softNb1)) ||
	  ((nb0 == nb1) && (softNb0 == softNb1) &&
	   (flip_time[v0] < flip_time[v1])));
}
    
int Solver::my_get_var_to_flip_in_clause(CRefLS crls) {
  int v, best_v, second_best_v, flip_index, i, v0, v1;
	int max_nb, second_max;
	int64_t maxSoftNb, secondMaxSoftNb;
	ClauseLS& cls=clausesLS[crls];
	Clause& c=ca[cls.cr];
	if (random_integer(100)<LNOISE) {
		flip_index=random_integer(c.size());
		// while(level(var(c[flip_index]))==0)
		// 	flip_index=(flip_index+1)%c.size();
		return var(c[flip_index]);
	}
	assert(c.size() > 1);
	v0 = var(c[0]); v1 = var(c[1]);
	if (betterThan(v0, v1)) {
	  best_v = v0; max_nb = score[v0]; maxSoftNb = softScore(v0);
	  second_best_v = v1; second_max = score[v1]; secondMaxSoftNb = softScore(v1);
	}
	else {
	  best_v = v1; max_nb = score[v1]; maxSoftNb = softScore(v1);
	  second_best_v = v0; second_max = score[v0]; secondMaxSoftNb = softScore(v0);
	}
	for(i=2; i<c.size(); i++) {
	  v=var(c[i]);
	  if (betterThan(v, best_v)) {
	    second_best_v = best_v; second_max = max_nb; secondMaxSoftNb = maxSoftNb;
	    best_v = v; max_nb = score[v]; maxSoftNb = softScore(v);
	  }
	  else if (betterThan(v, second_best_v)) {
	     second_best_v = v; second_max =  score[v]; secondMaxSoftNb = softScore(v);
	  }
	}
	assert(best_v!=var_Undef);
	if (second_best_v !=var_Undef && tabu_sattime[best_v]==TRUE && best_v==cls.lastSatVar()) {
		if (random_integer(100)<NOISE/10)
			return diversifyForUneven(crls, best_v);
		else if (random_integer(100)<NOISE)
			return second_best_v;
		else return best_v;
	}
	else return best_v;
}

int Solver::my_choose_var_by_random_walk() {
	CRefLS crls; int index;
	index=random_integer(unSAT.size());
	crls=unSAT[index];
	return my_get_var_to_flip_in_clause(crls);
}

void Solver::cleanDecVars(vec<Var>& vs) {
  int i, j;
  Var v;
  for (i=0; i<vs.size(); i++) {
    v=vs[i];
    if (score[v] < 0 || (score[v] == 0 && softScore(v) <= 0)) {
      break;
    }
  }
  if (i<vs.size()) {
    for (j=i+1; j<vs.size(); j++) {
      v=vs[j];
      if (score[v] > 0 || (score[v] == 0 && softScore(v) > 0)) {
	vs[i++]=v;
      }
    }
    vs.shrink(j-i);
  }
}

int Solver::choose_best_decreasing_var(vec<Var>& vs) {
	int ft;
	Var v, chosen_v;
	chosen_v=vs[0]; ft=flip_time[chosen_v];
	for (int i = 1; i < vs.size(); i++) {
		v=vs[i];
		if (flip_time[v]<ft) {
			ft=flip_time[v]; chosen_v=v;
		}
	}
	return chosen_v;
}


Var Solver::cleanDecVarsAndReturnBest(vec<Var> &vs) {
  int i, j, ft;
  Var v, chosen_v;
  chosen_v=var_Undef;
  ft=INT_MAX;
  
  for (i=0,j=0; i<vs.size(); i++) {
    v=vs[i];
    if (score[v] > 0 ) { //|| (score[v] == 0 && softScore(v) > 0)) {
      vs[j++]=v;
    //   if ((chosen_v == var_Undef) || (score[v] > score[chosen_v]) ||
    // 	  ((score[v] == score[chosen_v]) && (softScore(v) > softScore(chosen_v))) ||
    // 	  ((score[v] == score[chosen_v]) && (softScore(v) == softScore(chosen_v)) &&
    // 	   (flip_time[v] < flip_time[chosen_v])))
    // 	chosen_v=v;
      if (flip_time[v]<ft) {
      	ft=flip_time[v]; chosen_v=v;
      }
    }
  }
  vs.shrink(i-j);
  return chosen_v;
}

int Solver::choose_decVar() {
	//cleanDecVars(decrVars);
	//if (decrVars.size()>0)
	//	return choose_best_decreasing_var(decrVars);
	//return var_Undef;

	return cleanDecVarsAndReturnBest(decrVars);
}

#define invPhi 10
#define invTheta 5

void Solver::initNoise() {
	lastAdaptFlip=0;
	lastBest = unSAT.size();
	NOISE=20; LNOISE=2;
	AdaptLength=clausesLS.size() / invTheta;
}

void Solver::adaptNoveltyNoise(int flip) {

	if ((flip - lastAdaptFlip) > AdaptLength) {
		NOISE += (int) ((100 - NOISE) / invPhi);
		LNOISE= (int) NOISE/10;
		lastAdaptFlip = flip;
		lastBest = unSAT.size();
	}
	else if (unSAT.size() < lastBest) {
		NOISE -= (int) (NOISE /(2*invPhi));
		LNOISE= (int) NOISE/10;
		lastAdaptFlip = flip;
		lastBest = unSAT.size();
	}
}

void Solver::my_satisfy_clauses(Var v, vec<CRefLS>& cs) {
	assert(level(v)>0);
	Var neibor_v;
	int i, j;
	for(i=0; i<cs.size(); i++) {
		ClauseLS& cls=clausesLS[cs[i]];
		Clause& c=ca[cls.cr];
		cls.setNbTrue(cls.nbTrue()+1);
		switch(cls.nbTrue()) {
			case 1: {
				cls.setLastSatVar(v);
				int index=cls.unSATindex();
				CRefLS lastCls=unSAT[index]=unSAT.last();
				unSAT.pop();
				clausesLS[lastCls].setUnSATindex(index);
				for(j=0; j<c.size(); j++) {
					neibor_v=var(c[j]);
					if (neibor_v != v) {
						assert(assignsLS[neibor_v]==sign(c[j]));
						tabu_sattime[neibor_v]=FALSE;
						tmp_score[neibor_v]--;
					}
				}
				cls.setCriVar(v);
				break; }
			case 2: {
				tmp_score[cls.criVar()]++;
				cls.setCriVar(cls.criVar()+v);
				break;}
			default: cls.setCriVar(cls.criVar()+v);
		}
	}
}

void Solver::my_unsatisfy_clauses(Var v, vec<CRefLS>& cs) {
	assert(level(v)>0);
	Var neibor_v;
	int i, j;
	for(i=0; i<cs.size(); i++) {
		ClauseLS& cls=clausesLS[cs[i]];
		Clause& c=ca[cls.cr];
		cls.setNbTrue(cls.nbTrue()-1); cls.setCriVar(cls.criVar()-v);
		switch(cls.nbTrue()) {
			case 0:
				cls.setMostRecent(v);
				cls.setUnSATindex(unSAT.size());
				unSAT.push(cs[i]);
				for(j=0; j<c.size(); j++) {
					neibor_v=var(c[j]);
					if (neibor_v != v ) {
						assert(assignsLS[neibor_v]==sign(c[j]));
						tabu_sattime[neibor_v]=FALSE;
						tmp_score[neibor_v]++;
					}
				}
				break;
			case 1:
				tmp_score[cls.criVar()]--;
				break;
		}
	}
}

void Solver::check_implied_clauses(Var v) {
	int i;
	Lit p=mkLit(v, !assignsLS[v]);
	assert(level(v)>0);

	my_satisfy_clauses(v, inClauses[p]);
	my_unsatisfy_clauses(v, inClauses[~p]);
	vec<Var>& vs=neibors[v];
	tabu_sattime[v]=TRUE;
	for(i=0; i<vs.size(); i++) {
	  Var neibor_v=vs[i];
	  if(level(neibor_v)>0) {
	    //If it wasn't in decrVars and after that it will be, add it
	    if (score[neibor_v] <= 0 && score[neibor_v] + tmp_score[neibor_v] > 0 && (!auxiVar(neibor_v) || softScore(neibor_v) > 0))
	    // if ((score[neibor_v] <= 0 && score[neibor_v] + tmp_score[neibor_v] > 0) ||
	    // 	(auxiVar(neibor_v) && score[neibor_v] < 0 && score[neibor_v] + tmp_score[neibor_v] >= 0))
	      decrVars.push(neibor_v);
	    score[neibor_v] += tmp_score[neibor_v];
	    int totalC = inClauses[mkLit(neibor_v, false)].size() + inClauses[mkLit(neibor_v, true)].size();
	    assert(-totalC<=score[neibor_v] && score[neibor_v] <= totalC);
	    tmp_score[neibor_v] = 0;
	  }
	}
	if(auxiVar(v)){
	  //	if(assignsLS[v] != sign(softLits[v])) {
	  if (litSatisfiedLS(softLits[v])) {
			//Soft lit from false to true
			assert(unsatSVidx[v] >= 0 && unsatSVidx[v] < unsatSV.size());
			unsatSVidx[unsatSV.last()]=unsatSVidx[v];
			unsatSV[unsatSVidx[v]]=unsatSV.last();
			unsatSVidx[v]=-1;
			unsatSV.pop();
			cost-=weights[v];
		}
		else{
			//Soft lit from true to false
			unsatSVidx[v]=unsatSV.size();
			unsatSV.push(v);
			cost+=weights[v];
		}
	}
}

// void Solver::removeClauseForSattime(CRef cr) {
//   Clause& c=ca[cr];

//   for(int i=0; i<c.size(); i++)
//     inClauses.smudge(c[i]);
// }



Var Solver::choose_arm(int Nsolutions) {
	Var vBest = var_Undef;
	assert(unsatSV.size() > 0);
	double Ubest = -DBL_MAX;
	if(unsatSV.size() <= ARMNUM){
		for (int i = 0; i < unsatSV.size(); i++) {
			Var v = unsatSV[i];
			double Ui = Vsoft[v] + LAMBDA * sqrt(log(Nsolutions) / (double)(arm_n_picks[v] + 1));
			if(Ui > Ubest){
				Ubest=Ui;
				vBest=v;
			}
		}
	}
	else {
		for (int i = 0; i < ARMNUM; i++) {
			int idx = random_integer(unsatSV.size());
			Var v = unsatSV[idx];
			double Ui = Vsoft[v] + LAMBDA * sqrt(log(Nsolutions) / (double)(arm_n_picks[v] + 1));
			if(Ui > Ubest){
				Ubest=Ui;
				vBest=v;
			}
		}
	}
	arm_n_picks[vBest]++;
	return vBest;
}

int64_t Solver::softScore(int v){
  return auxiVar(v) ? (assignsLS[v] == sign(softLits[v]) ? weights[v] : -weights[v]) : 0;
}


void Solver::updateDelayedReward(vec<Var> &lastArms, int64_t lastLocal, int64_t currentLocal) {
	int  d = lastArms.size();
	double r = (lastLocal - currentLocal) / (double)(lastLocal - UB +1);
	for (int i = 1; i <= d; i++) {
		Var vv = lastArms[i-1];
		Vsoft[vv] += pow(GAMMA, d - i) * r;
		if(lastArms.size()==D_WINDOW && i > 1)
			lastArms[i - 2] = vv;
	}
}

void Solver::removeClauseFromOccur(CRef dr, bool strict) {
  Clause& d=ca[dr];
  if (strict)
    for(int i=0; i<d.size(); i++) {
      remove(occurIn[var(d[i])], dr);
      // if (!d.learnt())
      // 	updateElimHeap(var(d[i]));
    }
  else 
    for(int i=0; i<d.size(); i++) {
      occurIn.smudge(var(d[i]));
      // if (!d.learnt())
      // 	updateElimHeap(var(d[i]));
    }
}

void Solver::collectClauses(vec<CRef>& clauseSet, int learntType) {
  int i, j;
  // if (starts == 12)
  //   printf("sdfsqd ");
  for(i=0, j=0; i<clauseSet.size(); i++)
    if (cleanClause(clauseSet[i])) {
      CRef cr = clauseSet[i];
      Clause& c=ca[cr];
      if (c.learnt() && c.mark() != learntType)
	continue;
      for(int k=0; k<c.size(); k++)
	occurIn[var(c[k])].push(cr);
      clauseSet[j++] = cr;
      c.calcAbstraction();
      // subsumptionQueue.insert(cr);
      subsumptionQueue.push(cr);
    }
  clauseSet.shrink(i-j);
}

bool Solver::simpleStrengthenClause(CRef cr, Lit l) {
  Clause& c = ca[cr];
  assert(decisionLevel() == 0);

  // FIX: this is too inefficient but would be nice to have (properly implemented)
  // if (!find(subsumptionQueue, &c))
  // subsumptionQueue.insert(cr);
  subsumptionQueue.push(cr);
  
  if (c.size() == 2){
    removeClause(cr);  removeClauseFromOccur(cr);
    c.strengthen(l);
  }else{
    if (drup_file){
#ifdef BIN_DRUP
      binDRUP('d', c, drup_file);
#else
      fprintf(drup_file, "d ");
      for (int i = 0; i < c.size(); i++)
	fprintf(drup_file, "%i ", (var(c[i]) + 1) * (-2 * sign(c[i]) + 1));
      fprintf(drup_file, "0\n");
#endif
    }
    detachClause(cr, true);
    c.strengthen(l);
    attachClause(cr);
    remove(occurIn[var(l)], cr);
  }
  return c.size() == 1 ? enqueue(c[0]) && propagate() == CRef_Undef : true;
}

bool Solver::subsumeClauses(CRef cr, int& subsumed, int& deleted_literals) {
  Clause& c  = ca[cr];
  assert(c.size() > 1 || value(c[0]) == l_True);// Unit-clauses should have been propagated before this point.
  // Find best variable to scan:
  Var best = var(c[0]);
  for (int i = 1; i < c.size(); i++)
    if (occurIn[var(c[i])].size() < occurIn[best].size())
      best = var(c[i]);
  
  // Search all candidates:
  vec<CRef>& _cs = occurIn.lookup(best);
  CRef*       cs = (CRef*)_cs;
  for (int j = 0; j < _cs.size(); j++) {
    assert(!removed(cr));
    CRef dr=cs[j];
    if (dr != cr && !removed(dr)){
      Clause& d=ca[dr];
      Lit l = c.subsumes(d);
      if (l == lit_Undef) {
	if (c.learnt() && !d.learnt()) {
	  if (c.size() < d.size()) {
	    detachClause(dr, true); removeClauseFromOccur(dr, true);
	    for(int k=0; k<c.size(); k++) {
	      d[k] = c[k];
	      vec<CRef>& cls=occurIn[var(d[k])];
	      int m;
	      for(m=0; m<cls.size(); m++)
		if (cls[m] == cr) {
		  cls[m]=dr; break;
		}
	      assert(m<cls.size());
	    }
	    d.shrink(d.size() - c.size());
	    d.setAbs(c.abstraction());
	    d.setSimplified(c.simplified());
	    d.set_lbd(c.lbd());
	    d.setLastPoint(c.lastPoint());
	    attachClause(dr);
	  }
	  else removeClauseFromOccur(cr);
	  subsumed++; removeClause(cr); subsumptionQueue.push(dr); 
	  return true;
	}
	else {
	  subsumed++, removeClause(dr); removeClauseFromOccur(dr);
	}
	// if (c.learnt() && !d.learnt()) {
	//   c.promote();
	//   clauses.push(cr);
	// }
	// subsumed++, removeClause(dr); removeClauseFromOccur(dr);
      }
      else if (l != lit_Error){
	deleted_literals++;
	if (!simpleStrengthenClause(dr, ~l))
	  return false;
	// Did current candidate get deleted from cs? Then check candidate at index j again:
	if (var(l) == best)
	  j--;
      }
    }
  }
  return true;
}

bool Solver::backwardSubsume() {
  int savedTrail=trail.size(), mySavedTrail=trail.size(), savedOriginal;
  int cnt = 0, subsumed = 0, deleted_literals = 0, nbSubsumes=0;

  subsumptionQueue.clear();
  occurIn.init(staticNbVars);
  for(int i=0; i<staticNbVars; i++)
    occurIn[i].clear();

  printf("c original clauses %d, learnts_core %d, learnts_tier2 %d, learnts_local %d\n",
	 clauses.size(), learnts_core.size(), learnts_tier2.size(), learnts_local.size());
  collectClauses(clauses);
  collectClauses(learnts_core, CORE);
  collectClauses(learnts_tier2, TIER2);
  //  collectClauses(learnts_local, LOCAL);
  savedOriginal = clauses.size();

  int initQueueSize=subsumptionQueue.size();
  assert(decisionLevel() == 0);
  while (subsumptionQueue.size() > 0 || savedTrail < trail.size()) {
    // Check top-level assignments by creating a dummy clause and placing it in the queue:
    if (subsumptionQueue.size() == 0 && savedTrail < trail.size()){
      Lit l = trail[savedTrail++];
      ca[bwdsub_tmpunit][0] = l;
      ca[bwdsub_tmpunit].calcAbstraction();
      //subsumptionQueue.insert(bwdsub_tmpunit);
      subsumptionQueue.push(bwdsub_tmpunit);}

    for(int i=0; i<subsumptionQueue.size(); i++) {

      CRef    cr = subsumptionQueue[i]; //subsumptionQueue.peek(); subsumptionQueue.pop();
      if (removed(cr)) continue;
      nbSubsumes++;
      if (!subsumeClauses(cr, subsumed, deleted_literals)) {
	printf("c a conflict is found during backwardSubsumptionCheck\n");
	occurIn.cleanAll();
	return false;
      }
      
      // if (cnt++ % 1000 == 0) {
      // 	printf("c subsumption left: %10d (%5d subsumed, %5d deleted literals, %5d fixed vars)\n", subsumptionQueue.size(), subsumed, deleted_literals, trail.size() - mySavedTrail);
      // 	mySavedTrail=trail.size();
      // }

      if (i==initQueueSize) {
	printf("c initQueue %d, %d subsumed, %d deleted literals, %d fixed vars\n", initQueueSize, subsumed, deleted_literals, trail.size() - mySavedTrail);
	//	mySavedTrail=trail.size();
	initQueueSize=subsumptionQueue.size();
	printf("c subsumption queue grows to %d\n", initQueueSize);
	int j, k;
	for(j=0, k=i+1; k<subsumptionQueue.size(); k++)
	  subsumptionQueue[j++] = subsumptionQueue[k];
	subsumptionQueue.shrink(k-j);
	i=-1;
      }
      
    }
    subsumptionQueue.clear();
  }
  printf("c %d subsumptions, %5d subsumed, %5d deleted literals, %5d fixed vars\n", nbSubsumes, subsumed, deleted_literals, trail.size() - mySavedTrail);
  occurIn.cleanAll();

  // if (savedOriginal < clauses.size()) {
  //   // a learnt clause was promoted into original by subsumption resolution
  //   purgeLearnts(learnts_core);
  //   purgeLearnts(learnts_tier2);
  // }
    
    return true;
}

void Solver::purgeLearnts(vec<CRef>& learnts) {
  int j, k;
  for(j=0, k=0; j<learnts.size(); j++) {
    CRef cr=learnts[j];
    if (ca[cr].learnt() && !removed(cr))
      learnts[k++] = cr;
  }
  learnts.shrink(j-k);
}

void Solver::checkSolutionLS() {
#ifndef NDEBUG

	int64_t weight=0;
	for(int i=0; i<nSoftLits; i++){
		if (value(allSoftLits[i]) == l_False) {
			weight+=weightsBckp[var(allSoftLits[i])];
		}
	}

	if (weight != countedWeight) {
		printf("c **** error in weight, real weight: %lld, recorded weight: %lld****\n",
			   weight, countedWeight);
	}
	assert(weight == countedWeight);

	// printf("c there are %d hard clauses\n", clauses.size());
	for(int i=0; i<clausesLS.size(); i++) {
	  Clause& c=ca[clausesLS[i].cr];
	  int j;
	  for(j=0; j<c.size(); j++)
	    if (litSatisfiedLS(c[j])) //(sign(c[j]) == polarity[var(c[j])])
	      break;
	  if (j==c.size()) {
	    // if (!satisfied(ca[clausesLS[i].cr])) {
	    printf("c clause %d non-satisfied: ", clauses[i]);
	    Clause &c = ca[clauses[i]];
	    for (int k = 0; k < c.size(); k++)
	      printf(" %d ", toInt(c[k]));
	    printf("\n");
	  }
	}
#endif
}

#define MAXTRIES 1
#define MAXSTEPS 100000000

bool Solver::sattime(int maxsteps) {
	int i, j;
	Var var_to_flip, v;
	int nImprovements = 0;
	static int nSolutions=0;
	vec<Var> lastArms;
	int64_t lastLocal, currentLocal=UB;
	unSAT.clear();
	double beginSattime=cpuTime();

	if (!backwardSubsume() || !eliminateEqLits_(prevEquivLitsNb))
	  return false;
	
	clausesLS.clear();
	for(int i = 0; i < staticNbVars; i++){
		neibors[i].clear();
		inClauses[mkLit(i, false)].clear();
		inClauses[mkLit(i, true)].clear();
	}

	attachClausesForSattime(clauses);
	attachClausesForSattime(learnts_core);
	attachClausesForSattime(learnts_tier2);

	getNeibors();
	double endSattimePreproc = cpuTime();
	double preprocTime=endSattimePreproc-beginSattime;

	for (i=0;i<MAXTRIES;i++) {
		// compute (and set) the number of satisfied lits, crivar,
		//and collect unsat clauses
		// compute the score of each var and collect decVars
		initialize();
		initNoise();
		assert(unSAT.size()==0);
		assert(UB==cost);
		int tenthSteps = maxsteps/100;
		for (j=0;j<maxsteps;j++) {
			if (j==tenthSteps) {
				double tenthTime=cpuTime()-endSattimePreproc;
				if (tenthTime > 5)
					maxsteps=(int)((500.0/tenthTime)*tenthSteps);
			}
			if (unSAT.size()==0) {
				++nSolutions;
				lastLocal=currentLocal;
				currentLocal=cost; //countedWeight;
				if(cost < UB){
					++nImprovements;
					UB=cost;
					for(v=0;v<staticNbVars;v++)
					  if (assigns[v]==l_Undef)
					    polarity[v] = !assignsLS[v];
					  //	if(level(v)>0)
					//		assigns[v]=assignsLS[v]?l_True:l_False;
					printf("c Solution improved by LS: %lld in flip %d\n",UB, j);
					printf("o %lld\n",solutionCost+UB+fixedCostBySearch+derivedCost);
					checkSolutionLS();
				}
				//All soft literals are true, the solution cannot be further improved
				if(unsatSV.size()==0){
				  //assert(cost==0);
				  return true; //nImprovements>0;
				}

				//Try to improve the solution with multi-armed bandid strategy
				if(nSolutions>1)
					updateDelayedReward(lastArms, lastLocal, currentLocal);
				var_to_flip=choose_arm(nSolutions);
				if(lastArms.size()<D_WINDOW)
					lastArms.push(var_to_flip);
				else //In this case the lastArms has been shifted to left when updating delayed reward
					lastArms.last()=var_to_flip;
			}
			else
				var_to_flip=choose_decVar();

			if (var_to_flip==var_Undef) {
			  assert(decrVars.size()==0);
				assert(unSAT.size()>0);
				var_to_flip=my_choose_var_by_random_walk();
				assert(var_to_flip!=var_Undef);
			}
			assert(level(var_to_flip)>0);
			assignsLS[var_to_flip]=!assignsLS[var_to_flip];
			check_implied_clauses(var_to_flip);
			flip_time[var_to_flip]=j;
			adaptNoveltyNoise(j);
			score[var_to_flip]=-score[var_to_flip];
			int totalC = inClauses[mkLit(var_to_flip, false)].size() + inClauses[mkLit(var_to_flip, true)].size();
			assert(-totalC<=score[var_to_flip] && score[var_to_flip] <= totalC);
		}
	}
	double totalTime=cpuTime()-beginSattime;
	printf("c sattime  preproc time: %12.2fs, total time: %12.2fs, flips: %d, \n", preprocTime, totalTime, j);
	return true; //nImprovements>0;
}

