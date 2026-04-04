/****************************************************************************************[Dimacs.h]
Copyright (c) 2003-2006, Niklas Een, Niklas Sorensson
Copyright (c) 2007-2010, Niklas Sorensson

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

#ifndef Minisat_Dimacs_h
#define Minisat_Dimacs_h

#include <stdio.h>

#include "utils/ParseUtils.h"
#include "core/SolverTypes.h"

namespace Minisat {

//=================================================================================================
// DIMACS Parser:

    template<class B, class Solver>
    static void readClause(B& in, Solver& S, vec<Lit>& lits, int64_t &weight) {
        int     parsed_lit, var;
        lits.clear();
        if (S.instanceType!=0) weight=parseUint64(in);
        else weight=1;
        for (;;){
            parsed_lit = parseInt(in);
            if (parsed_lit == 0) break;
            var = abs(parsed_lit)-1;
            while (var >= S.nVars()) S.newVar();
            lits.push( (parsed_lit > 0) ? mkLit(var) : ~mkLit(var) );
        }
    }

    template<class B, class Solver>
    static void readClause_new(B& in, Solver& S, vec<Lit>& lits) {
        int     parsed_lit, var;
        lits.clear();
        for (;;){
            parsed_lit = parseInt(in);
            if (parsed_lit == 0) break;
            var = abs(parsed_lit)-1;
            while (var >= S.nVars()) S.newVar();
            lits.push( (parsed_lit > 0) ? mkLit(var) : ~mkLit(var) );
        }
    }

//Format pre-2022
    template<class B, class Solver>
    static void parse_DIMACS_old(B& in, Solver& S) {
        vec<Lit> lits;
        int vars    = 0;
        int clauses = 0;
        int cnt     = 0;

        assert(*in=='p');
        if (eagerMatch(in, "p cnf")){
            vars    = parseInt(in);
            clauses = parseInt(in);
            S.hardWeight=0;
            S.instanceType=0;
            S.nbOriVars=vars;
            S.totalWeight = 0;
        }
        else if (eagerMatch(in, "wcnf")){
            vars    = parseInt(in);
            clauses = parseInt(in);
            while (*in == 32) ++in;
            if (*in == '\n')
                S.hardWeight=0;
            else
                S.hardWeight=parseUint64(in);
            S.instanceType=1;
            S.nbOriVars=vars;
            S.nbOrignalVars=vars;
            S.UB = S.hardWeight;
            S.totalWeight = 0;
        }
        else{
            printf("PARSE ERROR! Unexpected char: %c\n", *in), exit(3);
        }

        for (;;){
            skipWhitespace(in);
            if (*in == EOF) break;
            else if (*in == 'p'){

            } else if (*in == 'c' || *in == 'p')
                skipLine(in);
            else{
                cnt++;
                int64_t weight;
                readClause(in, S, lits, weight);
                assert(weight>0);
                S.addClause_(lits, weight);
                if (S.hardWeight==0 || weight < S.hardWeight) // if this is a soft clause
                    S.totalWeight+=weight;       // if hardWeight==0, all clauses are soft
            }
        }
        if (vars != S.nVars())
            fprintf(stderr, "WARNING! DIMACS header mismatch: wrong number of variables.\n");
        if (cnt  != clauses)
            fprintf(stderr, "WARNING! DIMACS header mismatch: wrong number of clauses.\n");
    }


//Format post-2022
//Line p wcnf x y z is not prent
//Hard clauses start with h
    template<class B, class Solver>
    static void parse_DIMACS_new(B& in, Solver& S) {
        vec<Lit> lits;
        int vars = 0;
        int clauses = 0;
        int cnt = 0;
        S.hardWeight = INT64_MAX;
        S.instanceType = 1;
        S.totalWeight = 0;

        for (;;) {
            skipWhitespace(in);
            if (*in == EOF) break;
            else if (*in == 'c')
                skipLine(in);
            else {
                cnt++;
                int64_t weight;
                if (*in == 'h') {
                    weight = INT64_MAX;
                    ++in;
                    skipWhitespace(in);
                } else {
                    weight = parseUint64(in);
                    S.totalWeight+=weight;
                }
                readClause_new(in, S, lits);
                assert(weight > 0);
                S.addClause_(lits, weight);
            }
        }
        S.nbOriVars = S.nVars();
        S.nbOrignalVars = S.nVars();
    }



// Inserts problem into solver.
//
    template<class Solver>
    static void parse_DIMACS(gzFile input_stream, Solver& S) {
        StreamBuffer in(input_stream);
        for (;;) {
            skipWhitespace(in);
            if (*in == EOF) break;
            else if (*in == 'p') {
                parse_DIMACS_old(in, S);
                break;
            } else if (*in == 'h' || *in == '-' || (*in >= '0' && *in <= '9')) {
                parse_DIMACS_new(in, S);
                break;
            }
            else if (*in == 'c')
                skipLine(in);

        }
    }

//=================================================================================================

    template<class B, class Solver>
    static void simple_readClause(B& in, Solver& S, vec<Lit>& lits) {
        int     parsed_lit, var;
        lits.clear();
        for (;;){
            parsed_lit = parseInt(in);
            if (parsed_lit == 0) break;
            var = abs(parsed_lit)-1;
            lits.push( (parsed_lit > 0) ? mkLit(var) : ~mkLit(var) );
        }
    }

    template<class B, class Solver>
    static void check_solution_DIMACS_main(B& in, Solver& S) {
        int vars    = 0;
        int clauses = 0;
        int cnt     = 0, unsatcnt=0;
        int64_t cost=0;
        for (;;){
            skipWhitespace(in);
            if (*in == EOF) break;
            else if (*in == 'p'){
                if (eagerMatch(in, "p cnf")){
                    vars    = parseInt(in);
                    clauses = parseInt(in);
                    S.hardWeight=0;
                    S.instanceType=0;
                }
                else if (eagerMatch(in, "wcnf")){
                    vars    = parseInt(in);
                    clauses = parseInt(in);
                    while (*in == 32) ++in;
                    if (*in == '\n')
                        S.hardWeight=0;
                    else
                        S.hardWeight=parseUint64(in);
                    S.instanceType=1;
                } else{
                    printf("c PARSE ERROR! Unexpected char: %c\n", *in), exit(3);
                }
            } else if (*in == 'c' || *in == 'p')
                skipLine(in);
            else{
                cnt++;
                int parsed_lit, var;
                bool ok=false; uint64_t weight;
		vec<Lit> lits;
                if (S.instanceType!=0) weight=parseUint64(in);
                else weight=1;
		lits.clear();
                for(;;) {
                    parsed_lit = parseInt(in);
                    if (parsed_lit == 0) break; //{printf("\n"); break;}
                    var = abs(parsed_lit)-1;
		    lits.push( (parsed_lit > 0) ? mkLit(var) : ~mkLit(var) );
                    // printf("%d ", parsed_lit);
                    if ((parsed_lit>0 && S.model[var]==l_True) ||
                        (parsed_lit<0 && S.model[var]==l_False))
                        ok=true;
                }
                if (!ok) {
                    if (S.instanceType==0) cost += weight;
                    else if (S.hardWeight>0 && weight >= S.hardWeight) {
                        printf("c hard clause %d is not satisfied\n", cnt); unsatcnt++;
			printf("c ");
			for(int i=0; i<lits.size(); i++)
			  printf("%d ", toInt(lits[i]));
			printf("\n");
                    }
                    else cost += weight;
                }
            }
        }
        if (cnt  != clauses)
            printf("c WARNING! DIMACS header mismatch: wrong number of clauses.%d %d\n", cnt, clauses);
        else if (unsatcnt==0) {
            if (cost==S.optimal)
                printf("c solution checked against the original DIMACS file with correct cost %lld over the total cost %llu\n", cost, S.totalWeight);
            else {
                printf("c solution checked against the original DIMACS file with wrong cost\n");
                printf("c real cost : %lld, solution cost : %lld\n", cost, S.optimal);
		assert(cost==S.optimal);
            }
        }
        else {
	  printf("c solution infeasible with %d unsat hard clauses\n", unsatcnt);
	  assert(unsatcnt==0);
	}
    }

    /* template<class B, class Solver> */
    /* static void check_solution_DIMACS_main(B& in, Solver& S) { */
    /*     vec<Lit> lits; */
    /*     int vars    = 0; */
    /*     int clauses = 0; */
    /*     int cnt     = 0, unsatcnt=0; */
    /*     int64_t cost=0; */
    /*     for (;;){ */
    /*         skipWhitespace(in); */
    /*         if (*in == EOF) break; */
    /*         else if (*in == 'p'){ */
    /*             if (eagerMatch(in, "p cnf")){ */
    /*                 vars    = parseInt(in); */
    /*                 clauses = parseInt(in); */
    /*                 S.hardWeight=0; */
    /*                 S.instanceType=0; */
    /*             } */
    /*             else if (eagerMatch(in, "wcnf")){ */
    /*                 vars    = parseInt(in); */
    /*                 clauses = parseInt(in); */
    /*                 while (*in == 32) ++in; */
    /*                 if (*in == '\n') */
    /*                     S.hardWeight=0; */
    /*                 else */
    /*                     S.hardWeight=parseUint64(in); */
    /*                 S.instanceType=1; */
    /*             } else{ */
    /*                 printf("c PARSE ERROR! Unexpected char: %c\n", *in), exit(3); */
    /*             } */
    /*         } else if (*in == 'c' || *in == 'p') */
    /*             skipLine(in); */
    /*         else{ */
    /*             cnt++; */
    /*             int parsed_lit, var; */
    /*             bool ok=false; uint64_t weight; */
    /*             if (S.instanceType!=0) weight=parseUint64(in); */
    /*             else weight=1; */
    /*             for(;;) { */
    /*                 parsed_lit = parseInt(in); */
    /*                 if (parsed_lit == 0) break; //{printf("\n"); break;} */
    /*                 var = abs(parsed_lit)-1; */
    /*                 // printf("%d ", parsed_lit); */
    /*                 if ((parsed_lit>0 && S.model[var]==l_True) || */
    /*                     (parsed_lit<0 && S.model[var]==l_False)) */
    /*                     ok=true; */
    /*             } */
    /*             if (!ok) { */
    /*                 if (S.instanceType==0) cost += weight; */
    /*                 else if (S.hardWeight>0 && weight >= S.hardWeight) { */
    /*                     printf("c hard clause %d is not satisfied\n", cnt); unsatcnt++; */
    /*                 } */
    /*                 else cost += weight; */
    /*             } */
    /*         } */
    /*     } */
    /*     if (cnt  != clauses) */
    /*         printf("c WARNING! DIMACS header mismatch: wrong number of clauses.%d %d\n", cnt, clauses); */
    /*     else if (unsatcnt==0) { */
    /*         if (cost==S.solutionCost) */
    /*             printf("c solution checked against the original DIMACS file with correct cost %u over the total cost %u\n", cost, S.totalSoftWeight); */
    /*         else { */
    /*             printf("c solution checked against the original DIMACS file with wrong cost\n"); */
    /*             printf("c real cost : %u, solution cost : %u\n", cost, S.solutionCost); */
    /*         } */
    /*     } */
    /*     else printf("c solution infeasible with %d unsat hard clauses\n", unsatcnt); */
    /* } */

    template<class Solver>
    static void check_solution_DIMACS(gzFile input_stream, Solver& S) {
        StreamBuffer in(input_stream);
        check_solution_DIMACS_main(in, S); }

//=================================================================================================
}

#endif
