/***********[Main.cc]
Copyright (c) 2012-2013 Jessica Davies, Fahiem Bacchus
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

#include <errno.h>
#include <signal.h>
#include <iostream>
#include <fstream>
#include <sstream>
#include <random>

#ifdef GLUCOSE
#include "glucose/utils/Options.h"
#include "glucose/utils/System.h"
#else
#include "minisat/utils/Options.h"
#include "minisat/utils/System.h"
#endif

#include "maxhs/core/Incremental.h"
#include "maxhs/core/Wcnf.h"
#include "maxhs/utils/Params.h"

using std::cout;

#ifdef GLUCOSE
namespace Minisat = Glucose;
#endif
using namespace Minisat;

static MaxHS::MaxSolver* thesolver{};

static void SIGINT_exit(int signum) {
  if (thesolver) {
    thesolver->printStatsAndExit(signum, 1);
  } else {
    fflush(stdout);
    fflush(stderr);
    // Note that '_exit()' rather than 'exit()' has to be used.
    // The reason is that 'exit()' calls destructors and may cause deadlocks
    // if a malloc/free function happens to be running (these functions are
    // guarded by
    //  locks for multithreaded use).
    _exit(0);
  }
}

constexpr int majorVer{4};
constexpr int minorVer{0};
constexpr int update{0};

int main(int argc, char** argv) {
  try {
    setUsageHelp(
        "USAGE: %s [options] <input-file>\n  where input may be either in "
        "plain or gzipped DIMACS.\n");

    IntOption cpu_lim("A: General MaxHS", "cpu-lim",
                      "Limit on CPU time allowed in seconds.\n", INT32_MAX,
                      IntRange(0, INT32_MAX));
    IntOption mem_lim("A: General MaxHS", "mem-lim",
                      "Limit on memory usage in megabytes.\n", INT32_MAX,
                      IntRange(0, INT32_MAX));
    BoolOption version("A: General MaxHS", "version",
                       "Print version number and exit", false);

    parseOptions(argc, argv, true);
    params.readOptions();
    if (version) {
      cout << "MaxHS " << majorVer << "." << minorVer << "." << update << "\n";
      return (0);
    }
    cout << "c MaxHS " << majorVer << "." << minorVer << "." << update << "\n";
    cout << "c Instance: " << argv[argc - 1] << "\n";
    if (params.printOptions) {
      cout << "c Parameter Settings\n";
      cout << "c ============================================\n";
      printOptionSettings("c ", cout);
      cout << "c ============================================\n";
      cout << "c\n";
    }

    signal(SIGINT, SIGINT_exit);
    signal(SIGXCPU, SIGINT_exit);
    signal(SIGSEGV, SIGINT_exit);
    signal(SIGTERM, SIGINT_exit);
    signal(SIGABRT, SIGINT_exit);

    if (cpu_lim != INT32_MAX) {
      rlimit rl;
      getrlimit(RLIMIT_CPU, &rl);
      if (rl.rlim_max == RLIM_INFINITY || (rlim_t)cpu_lim < rl.rlim_max) {
        rl.rlim_cur = cpu_lim;
        if (setrlimit(RLIMIT_CPU, &rl) == -1)
          cout << "c WARNING! Could not set resource limit: CPU-time.\n";
      }
    }

    if (mem_lim != INT32_MAX) {
      rlim_t new_mem_lim = (rlim_t)mem_lim * 1024 * 1024;
      rlimit rl;
      getrlimit(RLIMIT_AS, &rl);
      if (rl.rlim_max == RLIM_INFINITY || new_mem_lim < rl.rlim_max) {
        rl.rlim_cur = new_mem_lim;
        if (setrlimit(RLIMIT_AS, &rl) == -1)
          cout << "c WARNING! Could not set resource limit: Virtual memory.\n";
      }
    }

    if (argc < 2) {
      cout << "c ERROR: no input file specfied:\n"
              "USAGE: %s [options] <input-file> <index-file>\n  where input may be either "
              "in plain or gzipped DIMACS.\n";
      exit(0);
    }

    params.mx_find_mxes = 0;
    params.preprocess = 0;

    double start_time = cpuTime();

    Wcnf theFormula{};
    if (!theFormula.inputDimacs(argv[1])) return 1;

    MaxHS::IncrementalSolver S(&theFormula);
    thesolver = &S;

    std::ifstream afile;
    afile.open(argv[2]);
    std::string line;
    int count = 0;
    int i;
    while (std::getline(afile, line)) {
      ++count;
      cout << "c ITERATION " << count << std::endl;
      std::istringstream iss(line);
      while (iss >> i) {
        S.hardenClause(i-1);
      }
      cout << "c CPU time before solving: " << cpuTime() - start_time << " s\n";
      S.search();
      cout << "c CPU time after solving:  " << cpuTime() - start_time << " s\n";
      cout << "\n";
    }

  } catch (const std::bad_alloc&) {
    cout << "c Memory Exceeded\n";
    thesolver->printStatsAndExit(100, 1);
  } catch (...) {
    cout << "c Unknown exception probably memory.\n";
    thesolver->printStatsAndExit(200, 1);
  }
  fflush(stdout);
  fflush(stderr);
  return 0;
}
