/* This code is largely based on Genipamax from IPASIR
(https://github.com/biotomas/ipasir/tree/master/app/genipamax)
by Tomas Balyo, KIT, Karlsruhe. */
#include <vector>
#include <map>

#include "lib/EvalMaxSAT/src/EvalMaxSAT.h"
#include <cmath>
using namespace std;

// The linked SAT solver might be written in C
extern "C" {
#include "ipasir.h"
}

class IpamirSolver {
   std::map<int,int> literal_to_real_id;

public:
   IpamirSolver() : n_vars(0), maxSATnoAssumed(std::make_shared<EvalMaxSAT>()) {
   }

   void add_hard(int32_t lit) {
       if (lit == 0)
       {
           maxSATnoAssumed->addClause(clause);
           hard_clauses_total.push_back(clause);
           clause . clear();
       }
       else
       {
           bool value = lit > 0;
           add_literal_if_not_declared(lit);
           clause . push_back( value ? lit : -lit );
       }
   }

   void add_soft_lit(int32_t newLit, uint64_t w) {
       bool value = -newLit > 0;
       bool alreadyDeclared = add_literal_if_not_declared(newLit);

       // The weight is not the same. Doesn't matter if it's the first solve (saved_weight == 0). However, if it's not
       // the first solve, we have to reset the solver anyway
       if (alreadyDeclared && !firstSolve) {
           resetSolverWithoutAssumps = true;
       }
       else
           maxSATnoAssumed->setVarSoft(std::abs(newLit), value, w);

       soft_lits_total[value ? newLit : -newLit] = w;
   }

   void assume(int lit) {
       assumptions.push_back(lit);
   }

   void reinitialize_solver() {
       maxSATnoAssumed = std::make_shared<EvalMaxSAT>();

       for ( int i = 0; i < n_vars; i++ )
           maxSATnoAssumed -> newVar();

       for (const auto &hard_clause : hard_clauses_total) {
           maxSATnoAssumed->addClause(hard_clause);
       }

       for (auto tuple : soft_lits_total) {
           int32_t lit = std::get<0>(tuple);
           int64_t w = std::get<1>(tuple);
           maxSATnoAssumed->setVarSoft(std::abs(lit), (lit > 0), w);
       }
   }

   int32_t solve() {
       if (firstSolve)
           firstSolve = false;
       if (resetSolverWithoutAssumps){
           reinitialize_solver();
           resetSolverWithoutAssumps = false;
       }

       maxSATnoAssumed->solve();

       maxSATwithAssump = std::make_shared<EvalMaxSAT>(*maxSATnoAssumed);

       maxSATwithAssump->IS_ASSUME_SOLVER = true;

       maxSATnoAssumed->IN_ASSUM = true; maxSATnoAssumed->SOLVER_WITH_ASSUMS = maxSATwithAssump;

       for (int32_t lit : assumptions)
       {
           int real_lit = literal_to_real_id[std::abs(lit)];
           real_lit = lit < 0 ? -real_lit : real_lit;
           maxSATwithAssump->addClause({real_lit});
       }

       assumptions.clear();

       bool return_val = maxSATwithAssump->solve();

       maxSATnoAssumed->IN_ASSUM = false;

       if(return_val == 0){
           return 20;
       } else {
           objective_value = maxSATwithAssump->getCost();
           return 30;
       }

   }
   uint64_t val_obj() {
       return objective_value;
   }
   int32_t val_lit(int32_t lit)
   {
       if (!literal_to_real_id.count(lit))
       {
           return 0;
       }
       bool truth_val = maxSATwithAssump -> getValue( literal_to_real_id[std::abs( lit )] );
       return truth_val ? lit : -std::abs( lit );
   }

private:
   std::shared_ptr<EvalMaxSAT> maxSATnoAssumed;
   std::shared_ptr<EvalMaxSAT> maxSATwithAssump;
   int32_t n_vars;
   vector<int32_t> clause;

   vector<vector<int32_t>> hard_clauses_total;
   uint64_t objective_value;
   map<int32_t, int64_t> soft_lits_total;

   bool resetSolverWithoutAssumps = false;
   bool firstSolve = true;

   vector<int32_t> assumptions;
   map<int32_t,int32_t> assignment;

   inline bool literal_was_declared(int lit) {
       return literal_to_real_id.count(lit);
   }

   bool add_literal_if_not_declared(int& lit) {
       if (!literal_was_declared(abs(lit))) {
           n_vars++;
           int new_lit = maxSATnoAssumed -> newVar();
           literal_to_real_id[std::abs(lit)] = new_lit;
           lit = new_lit;
           return false;
       }
       else {
           lit = literal_to_real_id[std::abs(lit)];
           return true;
       }
   }
};

extern "C" {

#include "ipamir.h"

static IpamirSolver * import (void * s) { return (IpamirSolver *) s; }

const char * ipamir_signature () { return "EvalMaxSAT2022"; }
void * ipamir_init () { return new IpamirSolver();  }
void ipamir_release (void * s) { delete import(s); }
void ipamir_add_hard (void * s, int32_t l) { import(s)->add_hard(l); }
void ipamir_add_soft_lit (void * s, int32_t l, uint64_t w) { import(s)->add_soft_lit(l,w); }
void ipamir_assume (void * s, int32_t l) { import(s)->assume(l); }
int32_t ipamir_solve (void * s) { return import(s)->solve(); }
uint64_t ipamir_val_obj (void * s) { return import(s)->val_obj(); }
int32_t ipamir_val_lit (void * s, int32_t l) { return import(s)->val_lit(l); }
void ipamir_set_terminate (void * s, void * state, int (*terminate)(void * state)) {}

};
