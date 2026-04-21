/***********[IpamirMaxHS.cc]
Copyright (c) 2021-2022 Andreas Niskanen

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
***********/

#include "maxhs/core/Incremental.h"
#include "maxhs/core/Wcnf.h"
#include "maxhs/utils/Params.h"

#include "minisat/utils/Options.h"
#include "minisat/utils/System.h"

using namespace std;
using namespace Minisat;
using namespace MaxHS;

static MaxSolver* thesolver{};

class IpamirMaxHS {

public:
  IpamirMaxHS() : calls(0), soft_lits(0) {
    params.readOptions();
    params.mx_find_mxes = 0;
    params.preprocess = 0;
    params.verbosity = 0;
    params.sverbosity = 0;
    params.mverbosity = 0;
    params.conditional_cores = 1;
    params.init_cores = 1;
    params.dsjnt_once = 1;
    formula = new Wcnf();
    solver = nullptr; // do not initialize yet!
  }
  ~IpamirMaxHS() { delete formula; delete solver; }
  void add_hard(int32_t lit) {
    if (lit) clause.push_back(import(lit));
    else {
      if (calls)
        solver->addHardClause(clause);
      else
        formula->addHardClause(clause);
      clause.clear();
    }
  }
  void add_soft_lit(int32_t lit, uint64_t w) {
    Lit l = import(lit); vector<Lit> soft_clause = { ~l };
    if (soft_lit_index.size() <= static_cast<size_t>(toInt(l)))
        soft_lit_index.resize(toInt(l)+1, -1);
    if (calls) {
      if (soft_lit_index[toInt(l)] == -1) {
        solver->addSoftClause(soft_clause, static_cast<Weight>(w));
        soft_lit_index[toInt(l)] = soft_lits++;
      } else {
        solver->changeWeight(soft_lit_index[toInt(l)], static_cast<Weight>(w));
      }
    } else {
      if (soft_lit_index[toInt(l)] == -1) {
        formula->addSoftClause(soft_clause, static_cast<Weight>(w));
        soft_lit_index[toInt(l)] = soft_lits++;
      } else {
        formula->changeWeight(soft_lit_index[toInt(l)], static_cast<Weight>(w));
      }
    }
  }
  void assume(int32_t lit) {
    if (calls)
      solver->addAssumption(import(lit));
    else
      assumptions.push_back(import(lit));
  }
  int32_t solve() {
    if (calls == 0) {
      //formula->computeWtInfo();
      //formula->printFormulaStats();
      formula->simplify();
      solver = new IncrementalSolver(formula);
      thesolver = solver;
      for (Lit l : assumptions)
        solver->addAssumption(l);
      assumptions.clear();
    }
    calls++;
    solver->search();
    if (!solver->haveModel() && !solver->isUnsat()) return 0;
    if (solver->isUnsat()) return 20;
    model = solver->getModel();
    if (!solver->isSolved()) return 10;
    return 30;
  }
  uint64_t val_obj() {
    if (calls && solver->haveModel())
      return static_cast<uint64_t>(solver->UB() + solver->getWcnf()->baseCost());
    else return numeric_limits<uint64_t>::max();
  }
  int32_t val_lit(int32_t lit) {
    if (!calls || !solver->haveModel()) return 0;
    lbool res = (lit > 0) ? model[abs(lit)-1] : model[abs(lit)-1].neg();
    return (res == l_True) ? lit : -lit;
  }

private:
  Wcnf * formula;
  IncrementalSolver * solver;
  vector<Lit> clause;
  vector<Lit> assumptions;
  uint64_t calls;
  int32_t soft_lits;
  vector<int32_t> soft_lit_index;
  vector<lbool> model;
  Lit import (int32_t lit) {
    return mkLit(Var(abs(lit)-1), (lit < 0));
  }
};

extern "C" {

#include "ipamir/ipamir.h"

static IpamirMaxHS * import (void * s) { return (IpamirMaxHS *) s; }

const char * ipamir_signature () { return "MaxHS"; }
void * ipamir_init () { return new IpamirMaxHS(); }
void ipamir_release (void * s) { delete import(s); }
void ipamir_add_hard (void * s, int32_t l) { import(s)->add_hard(l); }
void ipamir_add_soft_lit (void * s, int32_t l, uint64_t w) { import(s)->add_soft_lit(l,w); }
void ipamir_assume (void * s, int32_t l) { import(s)->assume(l); }
int32_t ipamir_solve (void * s) { return import(s)->solve(); }
uint64_t ipamir_val_obj (void * s) { return import(s)->val_obj(); }
int32_t ipamir_val_lit (void * s, int32_t l) { return import(s)->val_lit(l); }
void ipamir_set_terminate (void * s, void * state, int (*terminate)(void * state)) {}

};
