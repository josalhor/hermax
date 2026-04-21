/***********[Incremental.cc]
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
#include "maxhs/ifaces/Cplex.h"

using namespace MaxHS;
using namespace MaxHS_Iface;

using std::cout;

IncrementalSolver::IncrementalSolver(Wcnf *f) : MaxSolver {f} {}

void IncrementalSolver::search()
{
    if (input_assumptions.size() == 0)
        params.init_cores = false;
    if (!theWcnf->isUnsat() && params.init_cores) {
        vector<Lit> tmp = input_assumptions;
        input_assumptions.clear();
        bvars.clearAssumptions();
        params.dsjnt_phase = true;
        solve();
        if (params.verbosity > 0)
            cout << "c Core initialization CPU time: " << cpuTime() - globalStartTime << " s\n";
        doMin = true;
        m_sum_reduced_frac = 0.0;
        mtime = 0.0;
        mcalls = 0;
        params.init_cores = false;
        initialized = true;
        input_assumptions.clear();
        bvars.clearAssumptions();
        for (Lit l : tmp) {
            input_assumptions.push_back(l);
            bvars.addAssumption(l);
        }
    }
    if (disjoint_phase_done && params.dsjnt_once)
        params.dsjnt_phase = false;
    solve();
    doMin = true;
    m_sum_reduced_frac = 0.0;
    mtime = 0.0;
    mcalls = 0;
    if (!theWcnf->isUnsat())
        initialized = true;
    theWcnf->setUnsat(false);
    input_assumptions.clear();
    bvars.clearAssumptions();
    if (!unsat) model = theWcnf->rewriteModelToInput(UBmodel);
    else model.clear();
}

void IncrementalSolver::addHardClause(vector<Lit> & clause)
{
    vector<Lit> internal;
    bool sat = false;
    for (Lit lit : clause) {
        Lit l = theWcnf->internalLit(lit);
        if (var(l) == var_Undef) {
            if (var(theWcnf->equalLit(lit)) != var_Undef) {
                Lit scc_lit = theWcnf->equalLit(lit);
                if (theWcnf->hardUnit(~scc_lit)) {
                    continue;
                } else if (theWcnf->hardUnit(scc_lit)) {
                    sat = true;
                    break;
                }
                lit = scc_lit;
                l = theWcnf->internalLit(lit);
            } else if (theWcnf->hardUnit(~lit)) {
                continue;
            } else if (theWcnf->hardUnit(lit)) {
                sat = true;
                break;
            }
        }
        if (var(l) == var_Undef) {
            Var new_var = bvars.newOvar();
            l = mkLit(new_var, sign(lit));
            theWcnf->setInternalVar(new_var, var(lit));
        }
        internal.push_back(l);
    }
    if (sat) return;
    if (theWcnf->prepareClause(internal)) {
        if (theWcnf->addHardClause(internal)) {
            satsolver->addClause(internal);
            UBmodel.resize(bvars.n_vars(), l_Undef);
            sat = false;
            for (Lit l : internal) {
                if (UBmodel[var(l)] == (sign(l) ? l_False : l_True)) {
                    sat = true;
                    break;
                }
            }
            if (!sat) {
                haveUBModel = false;
                sat_wt = 0;
            }
            allClausesSeeded = false;
        }
    }
}

void IncrementalSolver::addSoftClause(vector<Lit> & clause, Weight w)
{
    vector<Lit> internal;
    bool sat = false;
    for (Lit lit : clause) {
        Lit l = theWcnf->internalLit(lit);
        if (var(l) == var_Undef) {
            if (var(theWcnf->equalLit(lit)) != var_Undef) {
                Lit scc_lit = theWcnf->equalLit(lit);
                if (theWcnf->hardUnit(~scc_lit)) {
                    continue;
                } else if (theWcnf->hardUnit(scc_lit)) {
                    sat = true;
                    break;
                }
                lit = scc_lit;
                l = theWcnf->internalLit(scc_lit);
            } else if (theWcnf->hardUnit(~lit)) {
                continue;
            } else if (theWcnf->hardUnit(lit)) {
                sat = true;
                break;
            }
        }
        if (var(l) == var_Undef) {
            Var new_var = bvars.newOvar();
            l = mkLit(new_var, sign(lit));
            theWcnf->setInternalVar(new_var, var(lit));
        }
        internal.push_back(l);
    }
    if (sat) return;
    if (theWcnf->prepareClause(internal)) {
        if (theWcnf->addSoftClause(internal, w)) {
            if (internal.size() == 1) {
                Lit l = internal[0];
                // cannot add duplicate unit softs -- change weight instead
                assert(!bvars.isBvar(l));
                if (sign(l)) {
                    haveUBModel = false;
                    sat_wt = 0;
                    bvars.setBvar(var(l));
                    configBvar(var(l), satsolver);
                    UBmodel.resize(bvars.n_vars(), l_Undef);
                    UBmodelSofts.push_back(l_False);
                    tmpModelSofts.push_back(l_False);
                    bLitOccur.resize(bvars.n_blits(), 0);
                    return;
                }
            }
            // otherwise we create new bvar
            haveUBModel = false;
            sat_wt = 0;
            Var new_bvar = bvars.newBvar();
            internal.push_back(mkLit(new_bvar));
            configBvar(new_bvar, satsolver);
            // bvars.printVars();
            satsolver->addClause(internal);
            UBmodel.resize(bvars.n_vars(), l_Undef);
            UBmodelSofts.push_back(l_False);
            tmpModelSofts.push_back(l_False);
            bLitOccur.resize(bvars.n_blits(), 0);
            allClausesSeeded = false;
        }
    }
}

void IncrementalSolver::addAssumption(Lit lit)
{
    Lit l = theWcnf->internalLit(lit);
    if (var(l) == var_Undef) {
        if (var(theWcnf->equalLit(lit)) != var_Undef) {
            Lit scc_lit = theWcnf->equalLit(lit);
            if (theWcnf->hardUnit(~scc_lit)) {
                theWcnf->setUnsat(true);
                return;
            } else if (theWcnf->hardUnit(scc_lit)) {
                return;
            }
            lit = scc_lit;
            l = theWcnf->internalLit(scc_lit);
        } else if (theWcnf->hardUnit(~lit)) {
            theWcnf->setUnsat(true);
            return;
        } else if (theWcnf->hardUnit(lit)) {
            return;
        }
    }
    if (var(l) == var_Undef) {
        Var new_var = bvars.newOvar();
        l = mkLit(new_var, sign(lit));
        theWcnf->setInternalVar(new_var, var(lit));
        UBmodel.resize(bvars.n_vars(), l_Undef);
    }
    if (!bvars.isAssumption(l)) {
        input_assumptions.push_back(l);
        bvars.addAssumption(l);
    }
}

void IncrementalSolver::hardenClause(int i)
{
    int index = theWcnf->softClauseIndex(i);
    if (index >= 0) {
        Lit blit = bvars.litOfCls(index);
        if (!bvars.isAssumption(~blit)) {
            input_assumptions.push_back(~blit);
            bvars.addAssumption(~blit);
        }
    } else if (index == -1) {
        theWcnf->setUnsat(true);
    }
}

void IncrementalSolver::ignoreClause(int i)
{
    int index = theWcnf->softClauseIndex(i);
    if (index >= 0) {
        Lit blit = bvars.litOfCls(index);
        if (!bvars.isAssumption(blit)) {
            input_assumptions.push_back(blit);
            bvars.addAssumption(blit);
        }
    }
}

void IncrementalSolver::changeWeight(int i, Weight w)
{
    int index = theWcnf->changeWeight(i, w);
    if (index >= 0) {
        cplex->update_weight(index);
        int contr_unit_index = theWcnf->contrUnit(index);
        if (contr_unit_index >= 0) {
            cplex->update_weight(contr_unit_index);
        }
    } else if (index == -1) {
        //cout << "c Clause " << i+1 << " is falsified!\n";
    } else if (index == -2) {
        //cout << "c Clause " << i+1 << " is satisfied!\n";
    }
}
