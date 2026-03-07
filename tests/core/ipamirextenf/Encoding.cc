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

#include "Encoding.h"

using namespace std;

DynamicAFEncoder::DynamicAFEncoder(AF & af) : instance(af), count(0)
{
    for (int i = 0; i < instance.args.size(); i++) {
        for (int j = 0; j < instance.args.size(); j++) {
            if (!instance.enforce[i] || !instance.enforce[j]) {
                att_var[std::make_pair(i,j)] = ++count;
            }
        }
    }
    for (int i = 0; i < instance.args.size(); i++) {
        if (!instance.enforce[i]) {
            for (int j = 0; j < instance.args.size(); j++) {
                if (!instance.enforce[j]) {
                    no_counter_var[std::make_pair(i,j)] = ++count;
                }
            }
        }
    }
}

void DynamicAFEncoder::generate_encoding()
{
    // admissibility
    for (int i = 0; i < instance.args.size(); i++) {
        if (instance.enforce[i]) {
            for (int j = 0; j < instance.args.size(); j++) {
                if (!instance.enforce[j]) {
                    vector<int> clause = { -att_var[make_pair(j,i)] };
                    for (int k = 0; k < instance.args.size(); k++) {
                        if (instance.enforce[k]) {
                            clause.push_back(att_var[make_pair(k,j)]);
                        }
                    }
                    formula.addHardClause(clause);
                }
            }
        }
    }
    // define no counter
    for (int i = 0; i < instance.args.size(); i++) {
        if (!instance.enforce[i]) {
            for (int j = 0; j < instance.args.size(); j++) {
                if (!instance.enforce[j]) {
                    vector<int> clause = { no_counter_var[make_pair(i,j)], -att_var[make_pair(i,j)] };
                    formula.addHardClause(-no_counter_var[make_pair(i,j)], att_var[make_pair(i,j)]);
                    for (int k = 0; k < instance.args.size(); k++) {
                        if (instance.enforce[k]) {
                            clause.push_back(att_var[make_pair(k,i)]);
                            formula.addHardClause(-no_counter_var[make_pair(i,j)], -att_var[make_pair(k,i)]);
                        }
                    }
                    formula.addHardClause(clause);
                }
            }
        }
    }
    // completeness
    for (int i = 0; i < instance.args.size(); i++) {
        if (!instance.enforce[i]) {
            vector<int> clause;
            for (int j = 0; j < instance.args.size(); j++) {
                if (instance.enforce[j]) {
                    clause.push_back(att_var[make_pair(j,i)]);
                } else {
                    clause.push_back(no_counter_var[make_pair(j,i)]);
                }
            }
            formula.addHardClause(clause);
        }
    }
    // minimize changes
    for (int i = 0; i < instance.args.size(); i++) {
        for (int j = 0; j < instance.args.size(); j++) {
            if (!instance.enforce[i] || !instance.enforce[j]) {
                if (instance.att_exists[make_pair(i,j)]) {
                    formula.addSoftLiteral(-att_var[make_pair(i,j)], 1);
                } else {
                    formula.addSoftLiteral(att_var[make_pair(i,j)], 1);
                }
            }
        }
    }
}

StaticAFEncoder::StaticAFEncoder(AF & af) : instance(af), count(0)
{
    for (int i = 0; i < instance.args.size(); i++) {
        arg_accepted_var[i] = ++count;
    }
    for (int i = 0; i < instance.args.size(); i++) {
        arg_rejected_var[i] = ++count;
    }
}

void StaticAFEncoder::generate_encoding()
{
    // conflict-freeness
    for (int i = 0; i < instance.args.size(); i++) {
        for (int j = 0; j < instance.attackers[i].size(); j++) {
            formula.addHardClause(-arg_accepted_var[i], -arg_accepted_var[instance.attackers[i][j]]);
        }
    }
    // define rejected
    for (int i = 0; i < instance.args.size(); i++) {
        vector<int> clause = { -arg_rejected_var[i] };
        for (int j = 0; j < instance.attackers[i].size(); j++) {
            clause.push_back(arg_accepted_var[instance.attackers[i][j]]);
            formula.addHardClause(arg_rejected_var[i], -arg_accepted_var[instance.attackers[i][j]]);
        }
        formula.addHardClause(clause);
    }
    // completeness
    for (int i = 0; i < instance.args.size(); i++) {
        vector<int> clause = { arg_accepted_var[i] };
        for (int j = 0; j < instance.attackers[i].size(); j++) {
            clause.push_back(-arg_rejected_var[instance.attackers[i][j]]);
            formula.addHardClause(-arg_accepted_var[i], arg_rejected_var[instance.attackers[i][j]]);
        }
    }
}
