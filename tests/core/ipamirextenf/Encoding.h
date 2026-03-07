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

#ifndef AF_ENCODING_H
#define AF_ENCODING_H

#include <vector>
#include <unordered_map>

#include "Instance.h"

struct MaxSATFormula {

    std::vector<std::vector<int>> hard_clauses;
    std::vector<std::pair<int, uint64_t>> soft_literals;

    void addHardClause(int x) { hard_clauses.push_back( {x} ); }
    void addHardClause(int x, int y) { hard_clauses.push_back( {x, y} ); }
    void addHardClause(int x, int y, int z) { hard_clauses.push_back( {x, y, z} ); }
    void addHardClause(int x, int y, int z, int w) { hard_clauses.push_back( {x, y, z, w} ); }
    void addHardClause(std::vector<int> & clause) { hard_clauses.push_back(clause); }
    void addSoftLiteral(int l, uint64_t w) { soft_literals.push_back(std::make_pair(l, w)); }

};

class DynamicAFEncoder {

public:
    DynamicAFEncoder(AF & af);
    uint32_t n_vars() { return count; }
    void generate_encoding();
    MaxSATFormula formula;
    std::unordered_map<std::pair<int,int>,int> att_var;

private:
    AF instance;
    int count;
    std::unordered_map<std::pair<int,int>,int> no_counter_var;

};

class StaticAFEncoder {

public:
    StaticAFEncoder(AF & af);
    uint32_t n_vars() { return count; }
    void generate_encoding();
    MaxSATFormula formula;
    std::unordered_map<int,int> arg_accepted_var;
    std::unordered_map<int,int> arg_rejected_var;

private:
    AF instance;
    int count;

};

#endif
