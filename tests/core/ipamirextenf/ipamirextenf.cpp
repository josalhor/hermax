//  Copyright (c) 2022 Andreas Niskanen, University of Helsinki
//
//  Permission is hereby granted, free of charge, to any person obtaining a 
//  copy of this software and associated documentation files (the "Software"), 
//  to deal in the Software without restriction, including without limitation 
//  the rights to use, copy, modify, merge, publish, distribute, sublicense, 
//  and/or sell copies of the Software, and to permit persons to whom the 
//  Software is furnished to do so, subject to the following conditions:
//
//  The above copyright notice and this permission notice shall be included in 
//  all copies or substantial portions of the Software.
//
//  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS 
//  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
//  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
//  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
//  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
//  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
//  DEALINGS IN THE SOFTWARE.

#include <cassert>
#include <fstream>
#include <iostream>
#include <algorithm>

using namespace std;

extern "C" {
#include "ipamir.h"
#include "ipasir.h"
}

#include "Instance.h"
#include "Encoding.h"

#include <iomanip>
#include <sstream>
#include <unordered_set>
#include <map>

static uint64_t fnv1a64(uint64_t x) {
    uint64_t h = 1469598103934665603ull;
    for (int i = 0; i < 8; ++i) {
        h ^= (x & 0xff);
        h *= 1099511628211ull;
        x >>= 8;
    }
    return h;
}
static uint64_t mix2(int a, int b) {
    uint64_t x = (uint64_t)(uint32_t)std::abs(a);
    x = (x << 32) ^ (uint64_t)(uint32_t)std::abs(b);
    return fnv1a64(x);
}
template <class V>
static uint64_t hash_hard_clauses(const V& hard) {
    uint64_t h = 1469598103934665603ull;
    for (auto const& cls : hard) {
        uint64_t ch = 1469598103934665603ull;
        for (int lit : cls) ch ^= fnv1a64((uint64_t)(int64_t)lit);
        h ^= ch; h *= 1099511628211ull;
    }
    return h;
}
template <class V>
static uint64_t hash_soft_literals(const V& soft) {
    uint64_t h = 1469598103934665603ull;
    for (auto const& p : soft) {
        uint64_t x = ((uint64_t)(int64_t)p.first) ^ (((uint64_t)p.second) << 1);
        h ^= fnv1a64(x); h *= 1099511628211ull;
    }
    return h;
}
// compute cost by asking solver for literal truth (TRUE => pay weight)
template <class Solver, class SoftVec>
static long long eval_soft_cost(Solver* s, const SoftVec& soft) {
    long long cost = 0;
    for (auto const& p : soft) {
        int lit = p.first; int w = p.second;
        int v = ipamir_val_lit(s, lit); // >0 means literal true
        if (v > 0) cost += w;
    }
    return cost;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        cout << "USAGE: ./ipamirextenf <input_file_name>\n\n";
        cout << "where <input_file_name> is an AF in APX format.\n\n";
        cout << "See ./inputs for example input files.\n";
        return 1;
    }

    ifstream input;
    input.open(argv[1]);

    if (!input.good()) {
        cout << "ERROR: Input file is not good.\n";
        return 1;
    }

    AF af;
    string line, arg, source, target;

    while (!input.eof()) {
        getline(input, line);
        line.erase(remove_if(line.begin(), line.end(), ::isspace), line.end());
        if (line.length() == 0 || line[0] == '/' || line[0] == '%') continue;
        if (line.length() < 6) cout << "WARNING: Cannot parse line: " << line << "\n";
        string op = line.substr(0,3);
        if (op == "arg") {
            if (line[3] == '(' && line.find(')') != string::npos) {
                arg = line.substr(4,line.find(')')-4);
                af.addArgument(arg);
            } else {
                cout << "WARNING: Cannot parse line: " << line << "\n";
            }
        } else if (op == "att") {
            if (line[3] == '(' && line.find(',') != string::npos && line.find(')') != string::npos) {
                source = line.substr(4,line.find(',')-4);
                target = line.substr(line.find(',')+1,line.find(')')-line.find(',')-1);
                af.addAttack(make_pair(source, target));
            } else {
                cout << "WARNING: Cannot parse line: " << line << "\n";
            }
        } else if (op == "enf" && line.find(')') != string::npos) {
            if (line[3] == '(') {
                arg = line.substr(4,line.find(')')-4);
                af.addEnforcement(arg);
            } else {
                cout << "WARNING: Cannot parse line: " << line << "\n";
            }
        }
    }

    cout << "c Number of arguments: " << af.args.size() << "\n";
    cout << "c Number of attacks:   " << af.atts.size() << "\n";
    cout << "c Number of targets:   " << af.enfs.size() << "\n";
    cout << "c Number of conflicts: " << af.numberOfConflicts() << "\n";

    DynamicAFEncoder encoder(af);
    encoder.generate_encoding();
    std::unordered_map<int, std::pair<int,int>> rev_att;
    for (auto const& kv : encoder.att_var) rev_att[kv.second] = kv.first;

    // Hard clause length histogram
    std::map<int,int> hist;
    for (auto const& cl : encoder.formula.hard_clauses) hist[(int)cl.size()]++;

    int soft_neg = 0, soft_pos = 0, neg_expected = 0, mismatch_cnt = 0;
    std::vector<std::pair<std::pair<int,int>, int>> mismatches;

    for (auto const& p : encoder.formula.soft_literals) {
        int lit = p.first;
        if (lit < 0) soft_neg++; else soft_pos++;
        auto it = rev_att.find(std::abs(lit));
        if (it == rev_att.end()) { mismatches.push_back({{-1,-1}, lit}); continue; }
        auto ij = it->second;
        bool exists = af.att_exists[ij];
        if (exists) {
            neg_expected++;
            if (lit >= 0) { mismatches.push_back({ij, lit}); mismatch_cnt++; }
        } else {
            if (lit <= 0) { mismatches.push_back({ij, lit}); mismatch_cnt++; }
        }
    }

    std::cout << "c DIAG hard_count " << encoder.formula.hard_clauses.size()
            << " soft_count " << encoder.formula.soft_literals.size() << "\n";
    std::cout << "c DIAG hard_len_hist ";
    int shown = 0; for (auto const& kv : hist) {
        if (shown++ >= 10) break;
        std::cout << "(" << kv.first << "," << kv.second << ") ";
    }
    std::cout << "\n";
    std::cout << "c DIAG soft_neg " << soft_neg << " soft_pos " << soft_pos << "\n";
    std::cout << "c DIAG soft_neg_expected " << neg_expected
            << " mismatch_cnt " << mismatch_cnt << "\n";
    for (size_t i = 0; i < std::min<size_t>(10, mismatches.size()); ++i) {
        auto ij = mismatches[i].first; int lit = mismatches[i].second;
        std::cout << "c DIAG soft_pol_mismatch (" << ij.first << "," << ij.second << ") lit " << lit << "\n";
    }
    // ==== DIAG FORMULA SUMMARY END ====

    void * maxsat_solver = ipamir_init();
    for (size_t i = 0; i < encoder.formula.hard_clauses.size(); i++) {
        //cout << "ipamir_add_hard\t";
        for (size_t j = 0; j < encoder.formula.hard_clauses[i].size(); j++) {
            //cout << encoder.formula.hard_clauses[i][j] << " ";
            ipamir_add_hard(maxsat_solver, encoder.formula.hard_clauses[i][j]);
        }
        //cout << "0\n";
        ipamir_add_hard(maxsat_solver, 0);
    }
    for (size_t i = 0; i < encoder.formula.soft_literals.size(); i++) {
        //cout << "ipamir_add_soft_lit\t" << encoder.formula.soft_literals[i].first << " 0\n";
        ipamir_add_soft_lit(maxsat_solver, encoder.formula.soft_literals[i].first, 1);
    }

    std::cout << "c DIAG added_hard " << encoder.formula.hard_clauses.size()
          << " added_soft " << encoder.formula.soft_literals.size() << "\n";

    while (true) {
        //cout << "ipamir_solve\n";
        int code = ipamir_solve(maxsat_solver);
        if (code != 30) {
            cout << "ERROR: ipamir_solve returned " << code << ". Terminating.\n";
            return code;
        }

        long long soft_cost = eval_soft_cost(maxsat_solver, encoder.formula.soft_literals);
        std::cout << "c DIAG model_soft_cost " << soft_cost << "\n";

        int soft_true_cnt = 0;
        int soft_true_printed = 0;
        for (auto const& p : encoder.formula.soft_literals) {
            int lit = p.first;
            int val = ipamir_val_lit(maxsat_solver, lit); // >0 means literal is TRUE
            if (val > 0) {
                ++soft_true_cnt;
                if (soft_true_printed < 10) {
                    auto it = rev_att.find(std::abs(lit));
                    if (it != rev_att.end()) {
                        auto ij = it->second;
                        std::cout << "c DIAG soft_true ("
                                << ij.first << "," << ij.second << "), "
                                << (lit > 0 ? "+1" : "-1") << "\n";
                        ++soft_true_printed;
                    }
                }
            }
        }
        std::cout << "c DIAG soft_true_cnt " << soft_true_cnt << "\n";

        AF candidate;
        for (int i = 0; i < af.args.size(); i++) {
            candidate.addArgument(af.args[i]);
        }
        for (int i = 0; i < af.args.size(); i++) {
            for (int j = 0; j < af.args.size(); j++) {
                if (!af.enforce[i] || !af.enforce[j]) {
                    //cout << "ipamir_val_lit\t" << encoder.att_var[make_pair(i,j)] << "\n";
                    if (ipamir_val_lit(maxsat_solver, encoder.att_var[make_pair(i,j)]) > 0) {
                        candidate.addAttack(make_pair(af.args[i], af.args[j]));
                    }
                }
            }
        }
        //candidate.print();
        // ==== DIAG CAND EDGES BEGIN ====
        std::vector<std::pair<int,int>> edges = candidate.atts;
        std::sort(edges.begin(), edges.end());
        uint64_t cand_hash = 1469598103934665603ull;
        for (auto const& e : edges) {
            uint64_t mh = mix2(e.first, e.second);
            cand_hash ^= mh; cand_hash *= 1099511628211ull;
        }
        std::cout << "c DIAG cand_attacks " << edges.size()
                << " cand_hash 0x" << std::hex << cand_hash << std::dec << "\n";
        for (size_t i = 0; i < std::min<size_t>(10, edges.size()); ++i) {
            std::cout << "c DIAG cand_edge (" << edges[i].first << "," << edges[i].second << ")\n";
        }
        // ==== DIAG CAND EDGES END ====

        StaticAFEncoder sat_encoder(candidate);
        sat_encoder.generate_encoding();

        void * sat_solver = ipasir_init();
        for (size_t i = 0; i < sat_encoder.formula.hard_clauses.size(); i++) {
            for (size_t j = 0; j < sat_encoder.formula.hard_clauses[i].size(); j++) {
                ipasir_add(sat_solver, sat_encoder.formula.hard_clauses[i][j]);
            }
            ipasir_add(sat_solver, 0);
        }
        
        for (int i = 0; i < af.args.size(); i++) {
            if (af.enforce[i]) {
                ipasir_add(sat_solver, sat_encoder.arg_accepted_var[i]);
                ipasir_add(sat_solver, 0); 
            }
        }
        int big_count = 0;
        vector<int> clause;
        for (int i = 0; i < af.args.size(); i++) {
            if (!af.enforce[i]) {
                ipasir_add(sat_solver, sat_encoder.arg_accepted_var[i]);
                big_count += 1;
            }
        }

        std::cout << "c DIAG big_clause_size " << big_count << "\n";
        ipasir_add(sat_solver, 0);

        code = ipasir_solve(sat_solver);
        if (code == 10) {
            vector<int> labeling(af.args.size(), 0);
            for (int i = 0; i < af.args.size(); i++) {
                if (ipasir_val(sat_solver, sat_encoder.arg_accepted_var[i]) > 0) {
                    labeling[i] = 1;
                } else if (ipasir_val(sat_solver, sat_encoder.arg_rejected_var[i]) > 0) {
                    labeling[i] = -1;
                }
            }
            //cout << "ipamir_add_hard\t";
            for (int i = 0; i < af.args.size(); i++) {
                for (int j = 0; j < af.args.size(); j++) {
                    if (candidate.att_exists[make_pair(i,j)]) {
                        if (labeling[i] == 1 && labeling[j] == -1) {
                            //cout << -encoder.att_var[make_pair(i,j)] << " ";
                            ipamir_add_hard(maxsat_solver, -encoder.att_var[make_pair(i,j)]);
                        }
                    } else {
                        if ((labeling[i] == 1 && labeling[j] == 1) || (labeling[i] == 0 && labeling[j] == 1)) {
                            if (!af.enforce[i] || !af.enforce[j]) {
                                //cout << encoder.att_var[make_pair(i,j)] << " ";
                                ipamir_add_hard(maxsat_solver, encoder.att_var[make_pair(i,j)]);
                            }
                        }
                    }
                }
            }
            //cout << " 0\n";
            ipamir_add_hard(maxsat_solver, 0);
        } else if (code == 20) {
            cout << "s OPTIMUM FOUND\n";
            cout << "o " << ipamir_val_obj(maxsat_solver) << "\n";
            candidate.print();
            return 0;
        } else {
            cout << "ERROR: ipasir_solve returned " << code << ". Terminating.\n";
            return code;
        }
    }

}
