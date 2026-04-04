/*****************************************************************************************[Main.cc]
Copyright (c) 2003-2006, Niklas Een, Niklas Sorensson
Copyright (c) 2007,      Niklas Sorensson
 
Copyright (c) 2017, Mao Luo, Chu-Min LI, Fan Xiao: implementing a learnt clause minimisation approach
 Reference: M. Luo, C.-M. Li, F. Xiao, F. Manya, and Z. L. , “An effective learnt clause minimization approach for cdcl sat solvers,” in IJCAI-2017, 2017, pp.703-711.
 
Maple_CM, Based on Maple_LCM --Copyright (c) 2018, Chu-Min LI, Mao Luo, Fan Xiao: implementing a clause minimisation approach.

 
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

#include <errno.h>

#include <signal.h>
#include <zlib.h>
#include <sys/resource.h>

#include "utils/System.h"
#include "utils/ParseUtils.h"
#include "utils/Options.h"
#include "core/Dimacs.h"
#include "simp/SimpSolver.h"

#ifdef FLAG_MAXHS
#include "mhsiface/MHSIface.h"
#endif

#ifdef FLAG_LS
#include "satlike3.0/LSIface.h"
#endif

using namespace Minisat;

//=================================================================================================


#ifdef _MSC_VER
void printStats(Solver& solver)
{
	double cpu_time = cpuTime();
	double mem_used = 0;//memUsedPeak();
	printf("c restarts              : %-12lld (%-12lld conflicts in avg)\n", solver.starts, (solver.starts>0 ? solver.conflicts / solver.starts : 0));
	printf("c conflicts             : %-12lld   (%.0f /sec)\n", solver.conflicts, solver.conflicts / cpu_time);
	printf("c decisions             : %-12lld   (%4.2f %% random) (%.0f /sec)\n", solver.decisions, (float)solver.rnd_decisions * 100 / (float)solver.decisions, solver.decisions / cpu_time);
	printf("c propagations          : %-12lld   (%.0f /sec)\n", solver.propagations, solver.propagations / cpu_time);

	printf("c conflict literals     : %-12lld   (%4.2f %% deleted)\n", solver.tot_literals, (solver.max_literals - solver.tot_literals) * 100 / (double)solver.max_literals);
	if (mem_used != 0) printf("Memory used           : %.2f MB\n", mem_used);
	printf("c CPU time              : %g s\n", cpu_time);
	// simplify
	printf("c nbSimplifyAll         : %d\n", solver.nbSimplifyAll);
	printf("c s_propagations        : %-12lld\n", solver.s_propagations);
	printf("c s_cost_ratio          : %4.2f%%\n", solver.s_propagations * 100 / (double)solver.propagations);

}
#else

void printStats(Solver& solver)
{
    double cpu_time = cpuTime();
    double mem_used = memUsedPeak();
    printf("c restarts              : %" PRIu64"\n", solver.starts);
    printf("c conflicts             : %-12" PRIu64"   (%.0f /sec)\n", solver.conflicts, solver.conflicts / cpu_time);
    printf("c decisions             : %-12" PRIu64"   (%4.2f %% random) (%.0f /sec)\n", solver.decisions, (float)solver.rnd_decisions * 100 / (float)solver.decisions, solver.decisions / cpu_time);
    printf("c propagations          : %-12" PRIu64"   (%.0f /sec)\n", solver.propagations, solver.propagations / cpu_time);
    printf("c conflict literals     : %-12" PRIu64"   (%4.2f %% deleted)\n", solver.tot_literals, (solver.max_literals - solver.tot_literals) * 100 / (double)solver.max_literals);
    if (mem_used != 0) printf("c Memory used           : %.2f MB\n", mem_used);
    printf("c CPU time              : %g s\n", cpu_time);
    // simplify
    printf("c nbSimplifyAll         : %lld\n", solver.nbSimplifyAll);
    printf("c s_propagations        : %-12" PRIu64"\n", solver.s_propagations);
    printf("c s_cost_ratio          : %4.2f%%\n", solver.s_propagations * 100 / (double)solver.propagations);
    printf("c LA cost without inference: %lld\n",solver.nonInferenceCost);
    printf("c LA cost update: %lld\n",solver.updateCost);

}
#endif


static Solver* solver;
// Terminate by notifying the solver and back out gracefully. This is mainly to have a test-case
// for this feature of the Solver as it may take longer than an immediate call to '_exit()'.
static void SIGINT_interrupt(int signum) { solver->interrupt(); }

// Note that '_exit()' rather than 'exit()' has to be used. The reason is that 'exit()' calls
// destructors and may cause deadlocks if a malloc/free function happens to be running (these
// functions are guarded by locks for multithreaded use).
static void SIGINT_exit(int signum) {
    printf("\n"); printf("c *** INTERRUPTED ***\n");
    printf("s UNKNOWN\n");
    if (solver->verbosity > 0){
        printStats(*solver);
        printf("\n"); printf("c *** INTERRUPTED ***\n"); }
    _exit(1); }


//=================================================================================================
// Main:

int main(int argc, char** argv)
{
    try {
        setUsageHelp("USAGE: %s [options] <input-file> \n\n  where input may be either in plain or gzipped DIMACS.\n");
        printf("c This is WMaxCDCL.\n");

#if defined(__linux__)
        fpu_control_t oldcw, newcw;
        _FPU_GETCW(oldcw); newcw = (oldcw & ~_FPU_EXTENDED) | _FPU_DOUBLE; _FPU_SETCW(newcw);
        printf("c WARNING: for repeatability, setting FPU to use double precision\n");
#endif
        // Extra options:
        //
        IntOption    verb   ("MAIN", "verb",   "Verbosity level (0=silent, 1=some, 2=more).", 1, IntRange(0, 2));
        BoolOption   pre    ("MAIN", "pre",    "Completely turn on/off any preprocessing.", true);
        //StringOption dimacs ("MAIN", "dimacs", "If given, stop after preprocessing and write the result to this file.");
        IntOption    cpu_lim("MAIN", "cpu-lim","Limit on CPU time allowed in seconds.\n", INT32_MAX, IntRange(0, INT32_MAX));
        IntOption    mem_lim("MAIN", "mem-lim","Limit on memory usage in megabytes.\n", INT32_MAX, IntRange(0, INT32_MAX));
        //BoolOption   drup   ("MAIN", "drup",   "Generate DRUP UNSAT proof.", false);
       // StringOption drup_file("MAIN", "drup-file", "DRUP UNSAT proof ouput file.", "");

        parseOptions(argc, argv, true);

        SimpSolver  S;
        double      initial_time = cpuTime();

        if (!pre) S.eliminate(true);

        S.parsing = true;
        S.verbosity = verb;
       /* if (drup || strlen(drup_file)){
            S.drup_file = strlen(drup_file) ? fopen(drup_file, "wb") : stdout;
            if (S.drup_file == NULL){
                S.drup_file = stdout;
                printf("c Error opening %s for write.\n", (const char*) drup_file); }
            printf("c DRUP proof generation: %s\n", S.drup_file == stdout ? "stdout" : drup_file);
        }*/

        solver = &S;
        // Use signal handlers that forcibly quit until the solver will be able to respond to
        // interrupts:
        signal(SIGINT, SIGINT_exit);
        signal(SIGXCPU,SIGINT_exit);

        // Set limit on CPU-time:
        if (cpu_lim != INT32_MAX){
            rlimit rl;
            getrlimit(RLIMIT_CPU, &rl);
            if (rl.rlim_max == RLIM_INFINITY || (rlim_t)cpu_lim < rl.rlim_max){
                rl.rlim_cur = cpu_lim;
                if (setrlimit(RLIMIT_CPU, &rl) == -1)
                    printf("c WARNING! Could not set resource limit: CPU-time.\n");
            } }

        // Set limit on virtual memory:
        if (mem_lim != INT32_MAX){
            rlim_t new_mem_lim = (rlim_t)mem_lim * 1024*1024;
            rlimit rl;
            getrlimit(RLIMIT_AS, &rl);
            if (rl.rlim_max == RLIM_INFINITY || new_mem_lim < rl.rlim_max){
                rl.rlim_cur = new_mem_lim;
                if (setrlimit(RLIMIT_AS, &rl) == -1)
                    printf("c WARNING! Could not set resource limit: Virtual memory.\n");
            } }

        if (argc == 1) {
            printf("c Reading from standard input... Use '--help' for help.\n");
        }

        gzFile in = (argc == 1) ? gzdopen(0, "rb") : gzopen(argv[1], "rb");
        if (in == NULL)
            printf("c ERROR! Could not open file: %s\n", argc == 1 ? "<stdin>" : argv[1]), exit(1);


        S.initUB = INT64_MAX;
        S.initLB = 0;

        int bestsol = 0; //0: no solution found, 1: MHS, 2: LS, 3: maxcdcl, 4: inputUB

        if (argc >= 3) {
            bestsol=4;
            int64_t init = parseInt64_csrt(argv[2]);
			assert(init <= INT64_MAX);
			S.initUB = init;
            printf("o %lld\n",S.initUB);
        }

#ifdef FLAG_MAXHS
        //Complete search LB/UB
        MHSIface mhs;
		mhs.solve(argv[1]);
        if(!mhs.error && mhs.UB < S.initUB) {
            S.initUB = mhs.UB;
            printf("o %lld\n",S.initUB);
            bestsol=1;
        }
        if(mhs.LB>=0){
            S.initLB = mhs.LB;
        }
        if(S.verbosity>0) {
            printf("c MHS finished at %f\n",cpuTime());
            printf("c MHS LB UB: %lld %lld\n", mhs.LB, mhs.UB);
        }

        if(S.initUB==S.initLB){
            printf("s OPTIMUM FOUND\n");
            mhs.printSol();
            if (S.verbosity > 0) {
                printStats(S);
                printf("\n");
            }
            exit(0);
        }
        assert(S.initUB>S.initLB);
#endif

#ifdef FLAG_LS
        //Local search UB
        LSIface ls;
        ls.solve(argv[1]);
        if(ls.UB < S.initUB){
            S.initUB = ls.UB;
            printf("o %lld\n",S.initUB);
            bestsol=2;
        }
        if(S.verbosity>0) {
            printf("c LS finished at %f\n",cpuTime());
            printf("c LS UB: %lld\n", ls.UB);
        }
        if(S.initUB==S.initLB){
            printf("s OPTIMUM FOUND\n");
            ls.printSol();
            if (S.verbosity > 0) {
                printStats(S);
                printf("\n");
            }
            exit(0);
        }
        assert(S.initUB>S.initLB);
#endif


        printf("c initial UB: %lld\n", S.initUB);
        printf("c initial LB: %lld\n", S.initLB);

        //FILE *res = (argc >= 4) ? fopen(argv[4], "wb") : NULL;
		FILE *res = NULL;

        lbool ret;
        if(S.initUB<INT64_MAX)
            S.initUB--;

        parse_DIMACS(in, S);
        gzclose(in);

        if (S.verbosity > 0){
            printf("c ============================[ Problem Statistics ]=============================\n");
            printf("c |                                                                             |\n"); }

        if (S.verbosity > 0) {
            printf("c |  Number of variables:  %12d                                         |\n", S.nVars());
            printf("c |  Number of clauses:    %12d                                         |\n", S.nClauses());
        }

        double parsed_time = cpuTime();
        if (S.verbosity > 0)
            printf("c |  Parse time:           %12.2f s                                       |\n",
                   parsed_time - initial_time);

        // Change to signal-handlers that will only notify the solver and allow it to terminate
        // voluntarily:
        //signal(SIGINT, SIGINT_interrupt);
        //signal(SIGXCPU,SIGINT_interrupt);

        S.parsing = false;
        S.setFrozenVars();
        S.eliminate(true);
        double simplified_time = cpuTime();
        if (S.verbosity > 0) {
            printf("c |  Simplification time:  %12.2f s                                       |\n",
                   simplified_time - parsed_time);
            printf("c |                                                                             |\n");
        }

        if (!S.okay()) {

                /*if (res != NULL) fprintf(res, "UNSAT\n"), fclose(res);
                if (S.verbosity > 0) {
                    printf("c ===============================================================================\n");
                    printf("c Solved by simplification\n");
                    printStats(S);
                    printf("\n");
                }
                printf("s UNSATISFIABLE\n");
                if (S.drup_file) {
#ifdef BIN_DRUP
                    S.binDRUP_flush(S.drup_file);
                    fputc('a', S.drup_file);
                    fputc(0, S.drup_file);
#else
                    fprintf(S.drup_file, "0\n");
#endif
                }
                if (S.drup_file && S.drup_file != stdout) fclose(S.drup_file);
                exit(20);*/

                if (S.verbosity > 0) {
                    printf("c ===============================================================================\n");
                    printf("c Solved by simplification\n");
                    printStats(S);
                    printf("\n");
                }
                ret=l_False;
        }
        else {
           /* if (dimacs) {
                if (S.verbosity > 0)
                    printf("c ==============================[ Writing DIMACS ]===============================\n");
                S.toDimacs((const char *) dimacs);
                if (S.verbosity > 0)
                    printStats(S);
                exit(0);
            }*/

            vec<Lit> dummy;
            ret = S.solveLimited(dummy);
            if(S.feasible)
                bestsol=3;
            if (S.verbosity > 0) {
                printStats(S);
                printf("\n");
            }
        }

        printf(bestsol>0 ?  "s OPTIMUM FOUND\n" : "s UNSATISFIABLE\n");
#ifdef FLAG_MAXHS
        if(bestsol==1)
            mhs.printSol();
#endif
#ifdef FLAG_LS
        if(bestsol==2)
            ls.printSol();
#endif
        if(bestsol==3){
            printf("v ");
            for (int i = 0; i < S.nbOrignalVars; i++) {
                printf(S.model[i]==l_True ? "1" : "0");
            }
            printf("\n");
        }
        else if(bestsol==4)
            printf("c Could not improve the input UB. UB-1 is proved unsatisfiable\n");


//         if (S.drup_file && ret == l_False){
// #ifdef BIN_DRUP
//             fputc('a', S.drup_file); fputc(0, S.drup_file);
// #else
//             fprintf(S.drup_file, "0\n");
// #endif
//         }
//         if (S.drup_file && S.drup_file != stdout) fclose(S.drup_file);

        if (res != NULL){
            if (ret == l_True){
                fprintf(res, "SAT\n");
                for (int i = 0; i < S.nVars(); i++)
                    if (S.model[i] != l_Undef)
                        fprintf(res, "%s%s%d", (i==0)?"":" ", (S.model[i]==l_True)?"":"-", i+1);
                fprintf(res, " 0\n");
            }else if (ret == l_False)
                fprintf(res, "UNSAT\n");
            else
                fprintf(res, "INDET\n");
            fclose(res);
        }

#ifndef NDEBUG
	gzFile myin = (argc == 1) ? gzdopen(0, "rb") : gzopen(argv[1], "rb");
	check_solution_DIMACS(myin, S);
#endif

#ifdef NDEBUG
        //exit(ret == l_True ? 10 : ret == l_False ? 20 : 0);     // (faster than "return", which will invoke the destructor for 'Solver')
        exit(0);
#else
        //return (ret == l_True ? 10 : ret == l_False ? 20 : 0);
        return 0;
#endif
    } catch (OutOfMemoryException&){
        printf("c ===============================================================================\n");
        printf("c Out of memory\n");
        printf("s UNKNOWN\n");
        exit(0);
    }
}
