/***********[SumManager.cc]
Copyright (c) 2019, Jeremias Berg, Fahiem Bacchus

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

#include "SumManager.h"
#include "SortNet.h"

#include <stdlib.h>
#include <algorithm>
#include <iostream>
#include <iterator>
#include <utility>
#include "maxhs/ifaces/muser.h"
#include "maxhs/utils/Params.h"
#include "maxhs/utils/io.h"

#ifdef GLUCOSE
#include "glucose/utils/System.h"
#else
#include "minisat/utils/System.h"
#endif

using std::map;
using std::vector;

using MaxHS::MaxSolver;
using MaxHS_Iface::Muser;
using MaxHS_Iface::SatSolver;

constexpr int debug__{0};

SumManager::SumManager(Bvars& b, MaxSolver* maxhs, Muser* m,
                                   SatSolver* s)
    : bvars{b}, maxsolver{maxhs}, muser{m}, satsolver{s}, core_structure{bvars}
{}

void SumManager::add_core(const vector<Lit>& cnst) {
  // requires that cnst only contain core bvars (true ===> soft clause is
  // falsified) or summation output (true ===> some number of soft clauses are
  // falsified)
  if (!params.abstract) return;
  if (cnst.size() > static_cast<size_t>(params.abstract_max_core_size)) {
    log(debug__ ? 0 : 2, "c adding large core to graph (size = ", cnst.size(),
        ") taking smaller set");
    // could select a random subset using std::sample (c++17)
    // but for now just grab the first k elements
    potential_cores.addVec(vector<Lit>(
        cnst.begin(), cnst.begin() + params.abstract_max_core_size));
  } else
    potential_cores.addVec(cnst);
}

void SumManager::start_timer(double timebound) {
  time_bound = cpuTime() + timebound;
}

double SumManager::time_remaining() { return time_bound - cpuTime(); }
bool SumManager::timeout() { return cpuTime() >= time_bound; }

void SumManager::compute_abstraction(double timebound, bool full) {
  log(debug__ ? 0 : 1, "c Abstraction: computing an abstraction with ",
      potential_cores.size(), " new cores");
  start_timer(timebound);
  size_t n_edges{0};
  vector<Lit> core;
  double ave_size = potential_cores.size()
                        ? static_cast<double>(potential_cores.total_size()) /
                              potential_cores.size()
                        : 0;
  if (ave_size > params.abstract_max_ave_size) {
    log(debug__ ? 0 : 1, "c Abstraction: cores too large");
    potential_cores.clear();
    // comment out next statement if we still want to try to do some
    // abstraction.
    // return
  }
  for (auto cnst : potential_cores) {
    // cout << "Core size: " << cnst.size() << endl;
    core.clear();
    for (Lit l : cnst) {
      if (isSoutput(l))
        core.push_back(output_to_firstinput(l));
      else if (bvars.isCore(l) || bvars.isDvar(l))
        core.push_back(l);
    }
    if (core.size() == 0) {
      log(debug__ ? 0 : 2,
          "c Abstraction: after processing empty core, orig size = ",
          cnst.size());
      continue;
    }
    for (size_t i = 0; i < core.size(); i++)
      for (size_t j = i + 1; j < core.size(); j++)
        if (isSameWt(core[i], core[j])) {
          core_structure.addEdge(core[i], core[j], 1.0);
          ++n_edges;
        }
  }
  potential_cores.clear();
  log(debug__ ? 0 : 1, "c Abstraction: added ", n_edges, " new edges.");
  abstract_cores(full);
  maxsolver->updateLB(computeSumLB());
}

void SumManager::abstract_cores(bool full) {
  vector<vector<Var>> clusters;
  int iter{0};
  bool last_iter{false};
  int sums_built{};
  bool do_final_exhaust{false};
  int combine_type{};
  constexpr int same_wt_type = 1;
  constexpr int small_type = 2;

  while (true) {
    auto mod_increase = core_structure.extractCommunities(clusters);
    if (mod_increase <= 0) {
      if (full) {
        do_final_exhaust = true;
        combine_type = same_wt_type;
      }
      if (iter == 0 || computeTotSumVars() < 1024) {
        do_final_exhaust = true;
        combine_type = small_type;
      }
      if (combine_type == same_wt_type) {
        log(debug__ ? 0 : 1, "c Abstraction: combining same wt clusters");
        combine_same_wt_clusters(clusters);
        if (!clusters.empty()) last_iter = true;
      }
      if (combine_type == small_type && clusters.size() > 1) {
        combine_small_clusters(clusters);
        if (!clusters.empty()) last_iter = true;
      }
      if (!last_iter) break;
    }
    ++iter;
    int n_sums{0};
    log(debug__ ? 0 : 1, "c Abstraction: Cluster Iter ", iter, ". ",
        clusters.size(), " clusters (mod ", fix4_fmt(mod_increase), ")");
    if (params.verbosity > 1) {
      int n_vars_in_clusters{0};
      for (auto& cluster : clusters) n_vars_in_clusters += cluster.size();
      log(debug__ ? 0 : 2,
          "c Abstraction: Nvars in cluster  = ", n_vars_in_clusters,
          " nvars in graph = ", core_structure.get_n_vars());
    }
    for (auto& cluster : clusters) {
      log(debug__ ? 0 : 2, "c Abstraction: processing cluster of size ",
          cluster.size());
      if (cluster.size() < static_cast<size_t>(params.abstract_min_size))
        continue;
      SRef t = build_sum(cluster);
      if (maxsolver->check_termination()) return;
      if (t != NullSRef) {
        ++sums_built;
        ++n_sums;
        log(debug__ ? 0 : 2, "c Abstraction: ", n_sums, ". built sum ",
            t->getSize(), " inputs, ", t->getOutTrue(), " true");
        sums_list.push_back(t);
        update_maps(t, sums_list.size() - 1);
      }
    }
    if (last_iter) break;
  }
  if (do_final_exhaust) {
    exhaust_top_level();
  }
  report_on_summations();
}

bool SumManager::all_summations_exhausted() const {
  for (auto& t : sums_list)
    if (t->isTopLevel() && !t->isExhausted()) return false;
  return true;
}

void SumManager::exhaust_top_level() {
  double timelimit{};
  ++tl_exhaust_calls;
  if (tl_exhaust_calls == 1) timelimit = 60;
  if (tl_exhaust_calls == 2) timelimit = 120;
  if (tl_exhaust_calls >= 3) timelimit = 180;
  int i_n{}, t_n{};
  log(debug__ ? 0 : 1,
      "c Abstraction: top_level exhaust with pre exhaust timelimit ",
      time_fmt(timelimit), "s.");
  for (auto& t : sums_list) {
    if (!t->isTopLevel()) continue;
    if (t->isExhausted()) continue;
    vector<SRef> leaves_last{get_subSums(t)};
    for (auto rit{leaves_last.rbegin()}; rit != leaves_last.rend(); ++rit) {
      exhaustSum(*rit, timelimit);
      ++i_n;
    }
    ++t_n;
  }
  log(debug__ ? 0 : 1, "c Abstraction: top_level exhaust ", t_n,
      " top level exhausts attempted. ", i_n, " low level exhausts attempted.");
}

void SumManager::remove_invalid_summations() {
  for (auto t : sums_list) {
    bool changed = false;
    Weight w = 0;
    for (auto l : t->getInputs()) {
      if (t->getWeight() != bvars.wt(l)) {
        changed = true;
        w = bvars.wt(l);
        break;
      }
    }
    bool remove = !allSameWt(t->getInputs());
    if (changed && !remove) {
      t->setWeight(w);
    } else if (remove) {
      for (auto l : t->getInputs()) {
        input_var_to_sref[toInt(var(l))] = NullSRef;
        input_var_to_sidx[toInt(var(l))] = -1;
      }
      for (auto l : t->getOutputs()) {
        output_var_to_sref[toInt(var(l))] = NullSRef;
        output_var_to_sout_index[toInt(var(l))] = -1;
      }
    }
  }
  int old_idx = 0;
  int new_idx = 0;
  vector<int> remap(sums_list.size(), -1);
  auto it = sums_list.begin();
  while (it != sums_list.end()) {
    SRef t = *it;
    bool remove = false;
    for (auto l : t->getInputs()) {
      if (input_var_to_sidx[toInt(var(l))] < 0) {
        remove = true;
        break;
      }
    }
    if (remove) {
      it = sums_list.erase(it);
      for (auto l : t->getInputs()) {
        input_var_to_sref[toInt(var(l))] = NullSRef;
        input_var_to_sidx[toInt(var(l))] = -1;
      }
      for (auto l : t->getOutputs()) {
        output_var_to_sref[toInt(var(l))] = NullSRef;
        output_var_to_sout_index[toInt(var(l))] = -1;
      }
      remap[old_idx++] = -1;
    } else {
      remap[old_idx++] = new_idx++;
      ++it;
    }
  }
  for (size_t i = 0; i < input_var_to_sidx.size(); i++) {
    if (input_var_to_sidx[i] >= 0) {
      input_var_to_sidx[i] = remap[input_var_to_sidx[i]];
    }
  }
  core_structure.remove_invalid_nodes_and_edges();
}

vector<SRef> SumManager::get_subSums(SRef t) {
  // return sequence of un-exhausted subsummations of t.
  // ordered by bottom level first.
  vector<SRef> result;
  if (!t->isExhausted()) result.push_back(t);
  size_t i{0};
  while (i < result.size()) {
    auto tr = result[i++];
    if (tr->leftS != NullSRef && !tr->leftS->isExhausted())
      result.push_back(tr->leftS);
    if (tr->rightS != NullSRef && !tr->rightS->isExhausted())
      result.push_back(tr->rightS);
  }
  return result;
}

void SumManager::unset_all_exhaust_flags() {
  for (auto& t : sums_list) {
    if (!t->isTopLevel()) continue;
    if (t->isExhausted()) t->unsetExhausted();
  }
}

void SumManager::report_on_summations() {
  if (!params.verbosity) return;
  int n_tl{}, sum_tl{}, ntrue_tl{}, nexhausted{};
  for (auto& t : sums_list) {
    if (!t->isTopLevel()) continue;
    n_tl++;
    sum_tl += t->getSize();
    ntrue_tl += t->getOutTrue();
    if (t->isExhausted()) ++nexhausted;
  }
  log(debug__ ? 0 : 1, "c Abstraction: ", n_tl, " summations over ", sum_tl,
      " soft clauses with ", ntrue_tl, " true outputs, and ", nexhausted,
      " exhausted. Summation lower bound wt = ", computeSumLB());
}

void SumManager::combine_small_clusters(vector<vector<Var>>& clusters) {
  vector<vector<Var>> all_combines;
  vector<Var> combine;
  size_t small{};
  ++small_clusters_calls;
  if (small_clusters_calls == 1) small = 256;
  if (small_clusters_calls == 2) small = 512;
  if (small_clusters_calls >= 3) small = 1024;
  log(debug__ ? 0 : 1, "c Abstraction: combining ", clusters.size(),
      " clusters of size ", small);
  if (params.verbosity > 1)
    for (size_t i = 0; i < clusters.size(); i++)
      log(debug__ ? 0 : 2, "c ", i, ". ", clusters[i].size());
  for (auto i = clusters.begin(); i != clusters.end(); ++i) {
    if (i->empty()) continue;
    bool keep = false;
    log(debug__ ? 0 : 2, "c examining cluster #", i - clusters.begin(),
        " of size ", i->size());
    if (i->size() < small) {
      combine.push_back(i->front());
      for (auto j = i + 1; j != clusters.end(); j++) {
        if (!j->empty() && isSameWt((*i)[0], (*j)[0]) &&
            (j->size() + i->size()) <= small) {
          log(debug__ ? 0 : 2, "c combining with cluster #",
              j - clusters.begin(), " of size ", j->size());
          for (auto& v : *j) i->push_back(v);
          combine.push_back(j->front());
          j->clear();
          keep = true;
        }
      }
    }
    if (!keep)
      i->clear();
    else
      all_combines.push_back(std::move(combine));
    combine.clear();
  }

  log(debug__ ? 0 : 2, "c final clusters before erase ", clusters);
  clusters.erase(std::remove_if(clusters.begin(), clusters.end(),
                                [&](vector<Var>& c) { return c.empty(); }),
                 clusters.end());
  log(debug__ ? 0 : 2, "c final clusters after erase ", clusters);
  if (!all_combines.empty()) core_structure.combine_nodes(all_combines);
}

void SumManager::combine_same_wt_clusters(vector<vector<Var>>& clusters) {
  vector<Var> combine;
  vector<vector<Var>> all_combines;
  for (auto i = clusters.begin(); i != clusters.end(); ++i) {
    if (i->empty()) continue;
    bool keep = false;
    combine.push_back(i->front());
    for (auto j = i + 1; j != clusters.end(); j++) {
      if (!j->empty() && isSameWt((*i)[0], (*j)[0])) {
        for (auto& v : *j) i->push_back(v);
        j->clear();
        keep = true;
      }
    }
    if (!keep)
      i->clear();
    else
      all_combines.push_back(std::move(combine));
    combine.clear();
  }
  clusters.erase(std::remove_if(clusters.begin(), clusters.end(),
                                [&](vector<Var>& c) { return c.empty(); }),
                 clusters.end());
  if (!all_combines.empty()) core_structure.combine_nodes(all_combines);
}

SRef SumManager::build_sum(const vector<Var>& cluster) {
  // cout << "TEST: build_sum called with cluster size " <<
  // cluster.size()
  //     << "\n";
  // every var in cluster should be a bvar
  assert(std::find_if(cluster.begin(), cluster.end(), [&](Var v) {
           return !bvars.isBvar(v);
         }) == cluster.end());
  vector<Lit> inputs;  // convert variable cluster to core literals.
  for (auto v : cluster) inputs.push_back(bvars.coreLit(v));
  // every lit should have the same weight.
  assert(allSameWt(inputs));
  inputs.erase(std::remove_if(inputs.begin(), inputs.end(),
                              [&](Lit l) {
                                return (satsolver->fixedValue(l, false) != l_Undef);
                              }),
               inputs.end());
  if (inputs.size() <= 1) {
    return NullSRef;
  }
  return build_sum_1(inputs);
}

lbool SumManager::sat_solve_update_assumps(vector<Lit>& assumps,
                                                 vector<Lit>& conflict) {
  // sat solve and remove conflict (if found from assumptions)
  conflict.clear();
  if (timeout()) return l_Undef;
  /*vector<Lit> sat_assumps = maxsolver->getInputAssumptions();
  sat_assumps.insert(sat_assumps.end(), assumps.begin(), assumps.end());*/
  vector<Lit> sat_assumps = assumps;
  lbool sat_result;
  if (params.cpu_per_exhaust < 0)
    sat_result = satsolver->solve(sat_assumps, conflict);
  else if (params.cpu_per_exhaust > 0)
    sat_result =
        satsolver->solveBudget(sat_assumps, conflict, params.cpu_per_exhaust);
  else
    sat_result = l_Undef;

  if (sat_result == l_False) {
    auto orig_size = conflict.size();
    if (params.min_type == 1 && conflict.size() > 2) {
      if (params.mus_cpu_lim > 0) {
        muser->musBudget(conflict, params.mus_cpu_lim);
      } else {
        muser->mus(conflict);
      }
    }
    if (conflict.size() <= 2 || conflict.size() < orig_size)
      satsolver->addClause(conflict);
    std::sort(conflict.begin(), conflict.end());
    auto e = std::remove_if(assumps.begin(), assumps.end(), [&](Lit l) {
      return (satsolver->fixedValue(l, false) != l_Undef ||
              std::binary_search(conflict.begin(), conflict.end(), ~l));
    });
    assumps.erase(e, assumps.end());
  } else if (sat_result == l_True) {
    if (params.init_cores) maxsolver->updateUB();
  }
  return sat_result;
}

SRef SumManager::build_sum_1(const vector<Lit>& inputs) {
  vector<Lit> assumps;
  vector<Lit> conflict;
  vector<SOut> inprocess_souts;  // contains all active sub-sums that
                                 // remain to be joined into other
                                 // sums.
  for (auto l : inputs) {
    if (!isSinput(l))
      assumps.push_back(~l);
    else {
      auto l_tr = get_ilit_sref(l);
      if (std::find_if(inprocess_souts.begin(), inprocess_souts.end(),
                       [&](SOut& sout) { return sout.sr == l_tr; }) ==
          inprocess_souts.end()) {
        auto l_tr_ntrue = l_tr->getOutTrue();
        if (static_cast<size_t>(l_tr_ntrue) < l_tr->getOutputs().size()) {
          auto l_out_lit = l_tr->getOutputs()[l_tr_ntrue];
          inprocess_souts.push_back({l_out_lit, l_tr});
          assumps.push_back(~l_out_lit);
        }
      }
    }
  }
  if (assumps.size() <= 1) {
    return NullSRef;
  }

  // an invariant in this loop is that every active sub-sum
  // (i.e. sub-sum not yet absorbed into another sum) has a
  // negated output lit in assumps, and every original literal not yet
  // absorbed into a sum has its negation in assumps.
  // When all original lits and sub-sums have been absorbed into
  // a sum, assumps will become empty.
  SOut t0;
  while (!assumps.empty()) {
    lbool sat_result = sat_solve_update_assumps(assumps, conflict);
    if (maxsolver->check_termination()) return NullSRef;

    if (sat_result == l_False) {
      /*conflict.erase(std::remove_if(conflict.begin(), conflict.end(),
                                    [&](Lit l){ return bvars.isAssumption(~l); }),
                     conflict.end());*/
      log(debug__ ? 0 : 3,
          "c build_sum_1 found conflict. Size = ", conflict.size());
      log(debug__ ? 0 : 3, "c build_sum_1. assumps = ", assumps,
          " conflict = ", conflict);
      if (conflict.empty()) {
        cout << "c ERROR, build_sum found empty conflict\n";
        return NullSRef;
      }
      /*for (Lit l : conflict) {
        if (bvars.isAssumption(~l)) {
          cout << "c Assumption literal in conflict: not building sum\n";
          return NullSRef;
        }
      }*/

      // constuct single sum from the conflict original lits
      // and sub-sum outputs
      t0 = sum_from_conflict(conflict, inprocess_souts);
      if (maxsolver->check_termination()) return NullSRef;
      log(debug__ ? 0 : 3, "c Sum from conflict = ", t0);
      if (t0.sr != NullSRef && !assumps.empty()) {
        inprocess_souts.push_back(t0);
        assumps.push_back(~t0.out_lit);
        log(debug__ ? 0 : 3,
            "c added to build_sum_1: assumps = ", assumps);
      }

    } else {  // remaining assumptions are satisfiable
      assert(!assumps.empty());
      conflict.clear();
      for (auto l : assumps) {
        if (satsolver->fixedValue(l, false) == l_Undef) conflict.push_back(~l);
      }
      assumps.clear();
      t0 = sum_from_conflict(conflict, inprocess_souts);
      if (maxsolver->check_termination()) return NullSRef;
    }
  }
  return t0.sr;
}

SOut SumManager::sum_from_conflict(const vector<Lit>& conflict,
                                               vector<SOut>& inprocess_souts) {
  // Build a sum from the lits in conflict (some of which might be
  // output lits from active sub-sum in inprocess_souts.
  assert(!conflict.empty());
  vector<Lit> conf_orig_lits;
  vector<SOut> conf_souts;

  // 1. split conflict
  for (auto l : conflict) {
    auto it = std::find_if(inprocess_souts.begin(), inprocess_souts.end(),
                           [&](SOut t) { return t.out_lit == l; });
    if (it != inprocess_souts.end()) {
      // move the found sub sum from inprocess to conf This
      // sub-sum will be joined into the final sum
      // generated by the conflict so it is no longer going to be
      // active
      conf_souts.push_back(*it);
      *it = inprocess_souts.back();
      inprocess_souts.pop_back();
    } else
      conf_orig_lits.push_back(l);
  }

  // 2. build and exhaust a sum over the orig lits
  if (conflict.size() == 1) {
    if (conf_orig_lits.size() == 1) return SOut{};
  }
  if (!conf_orig_lits.empty()) {
    SOut t0 = make_and_exhaust_base_sum(conf_orig_lits);
    if (maxsolver->check_termination()) return SOut{};
    if (t0.sr != NullSRef) conf_souts.push_back(t0);
  }
  // 3. join and exhaust the sum over the orig lits
  //    and all other sub-sums found in the conflict.
  //    Return a SOut structure from this sum
  return join_and_exhaust_sum(conf_souts);
}

/*TEST*/
void SumManager::test() {
  auto vars{bvars.getvars()};
  SRef t = build_sum(vars);
  if (t != NullSRef) {
    sums_list.push_back(t);
    update_maps(t, sums_list.size() - 1);
    const vector<Lit>& iLits = t->getInputs();
    const vector<Lit>& oLits = t->getOutputs();
    for (auto l : iLits)
      if (!bvars.isCore(l)) {
        cout << "ERROR input to final sum is not a core\n";
        exit(1);
      }
    for (auto l : oLits)
      if (!isSoutput(l)) {
        cout << "ERROR output to final sum is not SOut\n";
        exit(1);
      }
  }
}
/*TEST*/

SOut SumManager::make_and_exhaust_base_sum(
    const vector<Lit>& conf_orig_lits) {
  // build a sum over this set of lits, then exhaust it.
  // if is_clause, this set of lits are a clause so their sum must
  // have its first output set to true.
  assert(!conf_orig_lits.empty());
  assert(allSameWt(conf_orig_lits));
  Weight wt{get_weight_of_lit(conf_orig_lits[0])};
  auto t0 = SortNet::makeSortNet(*this, conf_orig_lits, wt);
  int lb = exhaustSum(t0, params.cpu_per_exhaust);
  if (lb >= static_cast<int>(t0->getSize()))
    return SOut{};
  else
    return SOut{t0->getOutputs()[lb], t0};
}

SOut SumManager::join_and_exhaust_sum(vector<SOut>& conf_souts) {
  // join these sums into one sum. 
  if (conf_souts.empty()) return SOut{};
  SRef t0{NullSRef};
  for (size_t i = 0; i < conf_souts.size(); i++) {
    size_t lb{0};
    if (t0 == NullSRef) {
      t0 = conf_souts[i].sr;
      lb = exhaustSum(t0, params.cpu_per_exhaust);
    } else {
      t0 = SortNet::makeSortNet(*this, t0, conf_souts[i].sr);
      lb = exhaustSum(t0, params.cpu_per_exhaust);
      if (maxsolver->check_termination()) return SOut{};
    }
    if (lb >= t0->getSize()) t0 = NullSRef;
  }
  if (t0 == NullSRef)
    return SOut{};
  else {
    int nTrue{t0->getOutTrue()};
    return SOut{t0->getOutputs()[nTrue], t0};
  }
}

int SumManager::exhaustSum(SRef sum, double timelimit) {
  setValuedOuts(sum);
  int lb = sum->getOutTrue();
  auto prev_lb = lb;
  if (sum->isExhausted()) return lb;
  auto t = time_remaining();
  /*vector<Lit> sat_assumps = maxsolver->getInputAssumptions();
  sat_assumps.push_back(lit_Undef);*/
  vector<Lit> sat_assumps = {lit_Undef};
  if (t > 0) {
    if (timelimit > t) timelimit = t;
    const vector<Lit>& oLits = sum->getOutputs();
    while (lb < static_cast<int>(oLits.size())) {
      sat_assumps[0] = ~oLits[lb];
      vector<Lit> conflict;
      lbool res;
      if (timelimit < 0)
        res = satsolver->solve(sat_assumps, conflict);
      else if (timelimit > 0)
        res = satsolver->solveBudget(sat_assumps, conflict, timelimit);
      else
        res = l_Undef;
      if (res == l_False) {
        satsolver->addClause(oLits[lb]);
        ++lb;
      } else {  
        if (res == l_True) {
          log(debug__ ? 0 : 2, "c exhaustSum exhausted sum ", sum,
              " lb = ", lb);
          sum->setExhausted();
          if (params.init_cores) maxsolver->updateUB();
        }
        break;
      }
    }
  }
  sum->setNOutTrue(lb);
  if (prev_lb < lb)
    log(debug__ ? 0 : 2, "c exhaustSum found ", lb - prev_lb,
        " addition true outputs");
  return lb;
}

void SumManager::addClausesToSolvers(const vector<vector<Lit>> cnf) {
  for (const auto& clause : cnf) {
    satsolver->addClause(clause);
  }
}

void SumManager::update_maps(SRef t, size_t tidx) {
  // t is a new top level sum
  resizeMaps();
  t->setTopLevel();

  auto iLits = t->getInputs();
  auto oLits = t->getOutputs();

  for (Lit l : iLits) {
    assert(bvars.isBvar(l));
    if (input_var_to_sref[toInt(var(l))] != -1)
      input_var_to_sref[toInt(var(l))]->unsetTopLevel();
    input_var_to_sref[toInt(var(l))] = t;
    input_var_to_sidx[toInt(var(l))] = tidx;
  }

  for (size_t j = 0; j < oLits.size(); j++) {
    Lit o = oLits[j];
    output_var_to_sref[toInt(var(o))] = t;
    output_var_to_sout_index[toInt(var(o))] = j;
  }
}

Lit SumManager::getNextOLit(Lit l) {
  assert(isSoutput(l));
  SRef sum = get_olit_sref(l);
  int nextOutputIdx = get_olit_index(l) + 1;
  if (nextOutputIdx >= static_cast<int>(sum->getOutputs().size()))
    return lit_Undef;
  else {
    return sum->getOutputs()[nextOutputIdx];
  }
}

void SumManager::resizeMaps() {
  size_t sz = bvars.n_vars();
  if (input_var_to_sref.size() < sz) {
    input_var_to_sref.resize(sz, NullSRef);
    input_var_to_sidx.resize(sz, -1);
    output_var_to_sref.resize(sz, NullSRef);
    output_var_to_sout_index.resize(sz, -1);
  }
}

void SumManager::setValuedOuts(SRef t) {
  // update the ouputs of t to their forced values.
  int lrfalse{0}, lrtrue{0}, tfalse{0}, ttrue{0};
  SRef r{t->getRight()};
  SRef l{t->getLeft()};

  if (r != NullSRef) {
    setValuedOuts(r);
    lrtrue += r->getOutTrue();
    lrfalse += r->getOutFalse();
  }
  if (l != NullSRef) {
    setValuedOuts(l);
    lrtrue += l->getOutTrue();
    lrfalse += l->getOutFalse();
  }
  ttrue = t->getOutTrue();
  tfalse = t->getOutFalse();
  ttrue = lrtrue > ttrue ? lrtrue : ttrue;
  tfalse = lrfalse > tfalse ? lrfalse : tfalse;

  ttrue = t->getOutTrue();
  tfalse = t->getOutFalse();

  /*vector<Lit> assumps = maxsolver->getInputAssumptions();
  vector<Lit> negated;
  for (Lit l : assumps)
    negated.push_back(~l);*/

  const vector<Lit>& oLits = t->getOutputs();
  int ntrue{0};
  for (; ntrue < ttrue; ++ntrue) {
    if (satsolver->fixedValue(oLits[ntrue], false) != l_True)
      satsolver->addClause(oLits[ntrue]);
  }
  for (; ntrue < static_cast<int>(oLits.size()); ntrue++) {
    if (satsolver->fixedValue(oLits[ntrue], false) != l_True) break;
  }
  t->setNOutTrue(ntrue);

  int nfalse{0};
  auto last{oLits.size() - 1};
  for (; nfalse < tfalse; nfalse++) {
    if (satsolver->fixedValue(oLits[last - nfalse], false) != l_False)
      satsolver->addClause(~oLits[last - nfalse]);
  }
  for (; nfalse < static_cast<int>(oLits.size()); nfalse++) {
    if (satsolver->fixedValue(oLits[last - nfalse], false) != l_False) break;
  }
  t->setNOutFalse(nfalse);

  assert(checkOutputs(t));
}

Weight SumManager::computeSumLB() {
  Weight w{};
  for (auto t : sums_list)
    if (t->isTopLevel()) w += t->getOutTrue() * t->getWeight();
  return w;
}

int SumManager::computeTotSumVars() {
  int szsum{};
  for (auto& t : sums_list)
    if (t->isTopLevel()) szsum += t->getSize();
  return szsum;
}

bool SumManager::allSumsExhausted() {
  for (auto& t : sums_list)
    if (t->isTopLevel() && !t->isExhausted()) return false;
  return true;
}

vector<int> SumManager::get_top_level_sidxes() const {
  vector<int> sidxs;
  for (size_t i = 0; i < sums_list.size(); ++i)
    if (sums_list[i]->isTopLevel()) sidxs.push_back(i);
  return sidxs;
}

bool SumManager::checkOutputs(SRef t) {
  // outputs should be true first undef next false last.
  auto oLits{t->getOutputs()};
  int type{-1}, nxt_type{-1};
  for (int i = 0; i < static_cast<int>(oLits.size()); i++) {
    auto val = satsolver->fixedValue(oLits[0], false);
    if (val == l_True)
      nxt_type = 0;
    else if (val == l_Undef)
      nxt_type = 1;
    else if (val == l_False)
      nxt_type = 3;
    if (nxt_type < type) return false;
    type = nxt_type;
  }
  return true;
}
