/***********[ConditionalCores.cc]
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

#include "maxhs/core/ConditionalCores.h"

using namespace MaxHS;

Cores::Cores(Bvars & b) : core_database{new MaxHS_Iface::cadicalSolver{}}, bvars{b}
{}

vector<Lit> Cores::add_core(const vector<Lit> & core)
{
	core_database->addClause(core);
	//conditional_cores.push_back(core);
	vector<Lit> clean_core;
	for (Lit l : core)
		if (!bvars.isAssumption(~l))
			clean_core.push_back(l);
	return clean_core;
}

Packed_vecs<Lit> Cores::valid_cores(const vector<Lit> & assumptions)
{
	core_database->setGlobalAssumptions(assumptions);
    auto n_clauses = core_database->getNclauses();
	Packed_vecs<Lit> valid_cores;
	for (size_t i = 0; i < n_clauses; i++) {
        vector<Lit> core;
        bool is_learnt = core_database->get_ith_clause(core, i);
        if (!params.seed_learnts && is_learnt) continue;
        if (core.size() == 0) continue;
        bool is_valid = true;
        vector<Lit> valid_core;
		for (Lit l : core) {
			if (core_database->fixedValue(l) == l_True) {
				is_valid = false;
				break;
			} else if (core_database->fixedValue(l) == l_Undef) {
				valid_core.push_back(l);
			}
		}
		if (is_valid) valid_cores.addVec(valid_core);
        //valid_cores.addVec(core);
	}
	return valid_cores;
}