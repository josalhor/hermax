/*
 * Author: Christoph Jabs - christoph.jabs@helsinki.fi
 */

#include <cassert>
#include <fstream>
#include <iostream>
#include <vector>

#include "totalizer.hpp"

using std::cout;
using std::fstream;
using std::string;
using std::vector;

extern "C" {
#include "ipamir.h"
#include "ipasir.h"
}

// An application for using modified WDIMACS files with two objectives as input
// The files are expected to be in the following format:
// Lines starting with 'h' are considered (hard) clauses.
// Lines starting with '1' are considered to be part of the first objective.
// (e.g. '1 <weight> <lit> 0'). Lines starting with '2' are considered to be
// part of the second objective (e.g. '2 <weight> <lit> 0')
bool initialize_solvers(void *incSolver, void *decSolver, uint32_t &nVars,
                        vector<int32_t> &increasing,
                        vector<int32_t> &decreasing, string filename) {
  uint32_t nClauses{};
  string line;
  vector<string> toks{};
  fstream file;
  file.open(filename, fstream::in);
  increasing.clear();
  decreasing.clear();

  while (getline(file, line)) {
    if (line[0] == 'c')
      continue;
    size_t pos = 0;
    toks.clear();
    while ((pos = line.find(" ")) != string::npos) {
      toks.push_back(line.substr(0, pos));
      line.erase(0, pos + 1);
    }
    toks.push_back(line);
    assert(toks.size() >= 1);
    if (toks[0] == "h") {
      // Parse clause
      assert(toks.back() == "0");
      int32_t l{};
      for (uint32_t i = 1; i < toks.size(); i++) {
        l = std::stoi(toks[i]);
        if (static_cast<uint32_t>(l > 0 ? l : -l) > nVars)
          nVars = static_cast<uint32_t>(l > 0 ? l : -l);
        ipamir_add_hard(incSolver, l);
        ipasir_add(decSolver, l);
      }
      nClauses++;
      continue;
    }
    if (toks[0] == "1") {
      // Parse increasing objective
      assert(toks.size() == 4);
      uint64_t w = std::stoi(toks[1]);
      int32_t l = std::stoi(toks[2]);
      if (static_cast<uint32_t>(l > 0 ? l : -l) > nVars)
        nVars = static_cast<uint32_t>(l > 0 ? l : -l);
      for (uint32_t i = 0; i < w; i++)
        increasing.push_back(l);
      ipamir_add_soft_lit(incSolver, l, w);
      continue;
    }
    if (toks[0] == "2") {
      // Parse decreasing objective
      assert(toks.size() == 4);
      uint64_t w = std::stoi(toks[1]);
      int32_t l = std::stoi(toks[2]);
      if (static_cast<uint32_t>(l > 0 ? l : -l) > nVars)
        nVars = static_cast<uint32_t>(l > 0 ? l : -l);
      for (uint32_t i = 0; i < w; i++)
        decreasing.push_back(l);
      continue;
    }
    cout << "c ERROR: Encountered unexpected line\n";
    return false;
  }

  return true;
}

bool bioptsat(void *incSolver, void *decSolver, uint32_t nVars,
              const vector<int32_t> &increasing,
              const vector<int32_t> &decreasing) {
  int32_t res;
  uint64_t incBound, decBound{};
  Totalizer *
      incTot{}, // For bounding the increasing objective in the SAT (dec) solver
      *decBoundTot{}, // For bounding the decreasing objective in the MaxSAT
                      // (inc) solver
      *decOptTot{}; // For optimizing the decreasing objective in the SAT (dec)
                    // solver
  uint32_t nIncSolverVars = nVars;
  uint32_t nDecSolverVars = nVars;

  while (true) {
    // Increasing objective
    res = ipamir_solve(incSolver);
    switch (res) {
    case 20:
      cout << "c INFO: there are no more pareto-optimal solutions (incSolver "
              "call UNSAT)\n";
      if (incTot)
        delete incTot;
      if (decBoundTot)
        delete decBoundTot;
      if (decOptTot)
        delete decOptTot;
      return true;

    case 30:
      incBound = ipamir_val_obj(incSolver);
      break;

    default:
      cout << "c ERROR: increasing objective call should always get UNSAT or "
              "OPTIMAL\n";
      if (incTot)
        delete incTot;
      if (decBoundTot)
        delete decBoundTot;
      if (decOptTot)
        delete decOptTot;
      return false;
    }

    decBound = 0;
    for (auto const &l : decreasing)
      if (ipamir_val_lit(incSolver, l) == l)
        decBound++;

    if (decBound <= 0) {
      // Print pareto-optimal solution
      cout << "c SOLUTION: pareto-optimal solution found for objective values "
              "inc="
           << incBound << ", and dec=" << decBound << "\n";

      cout << "c INFO: there are no more pareto-optimal solutions (dec=0)\n";
      if (incTot)
        delete incTot;
      if (decBoundTot)
        delete decBoundTot;
      if (decOptTot)
        delete decOptTot;
      return true;
    }

    if (decOptTot == nullptr) {
      decOptTot = new Totalizer(decSolver, SAT_SOLVER);
      decOptTot->build(decreasing, decBound, nDecSolverVars);
    }
    ipasir_add(decSolver, -decOptTot->getOutLit(decBound - 1));
    ipasir_add(decSolver, 0);

    if (incTot == nullptr) {
      // Build incTot if doesn't exist
      incTot = new Totalizer(decSolver, SAT_SOLVER);
      incTot->build(increasing, incBound, nDecSolverVars);
    } else {
      // Extend incTot to current bound
      incTot->updateUpper(incBound);
    }
    if (incBound < increasing.size())
      ipasir_assume(decSolver, -incTot->getOutLit(incBound));

    // SAT-UNSAT search for decreasing objective
    while (ipasir_solve(decSolver) == 10) {
#ifndef NDEBUG
      // Check if increasing objective value still fits
      uint64_t incVal{};
      for (auto l : increasing)
        if (ipasir_val(decSolver, l) == l)
          incVal++;
      assert(incVal == incBound);
#endif

      // Get new bound
      while (decBound > 0 &&
             ipasir_val(decSolver, -decOptTot->getOutLit(decBound - 1)) ==
                 -decOptTot->getOutLit(decBound - 1))
        decBound--;
      // Break if bound is 0
      if (decBound <= 0)
        break;
      // Tighten bound
      ipasir_add(decSolver, -decOptTot->getOutLit(decBound - 1));
      ipasir_add(decSolver, 0);
      if (incBound < increasing.size())
        ipasir_assume(decSolver, -incTot->getOutLit(incBound));
    }

    // Print pareto-optimal solution
    cout
        << "c SOLUTION: pareto-optimal solution found for objective values inc="
        << incBound << ", and dec=" << decBound << "\n";

    if (decBound <= 0) {
      cout << "c INFO: there are no more pareto-optimal solutions (dec=0)\n";
      if (incTot)
        delete incTot;
      if (decBoundTot)
        delete decBoundTot;
      if (decOptTot)
        delete decOptTot;
      return true;
    }

    if (decBoundTot == nullptr) {
      // Build decBoundTot if doesn't exist
      decBoundTot = new Totalizer(incSolver, MAXSAT_SOLVER);
      decBoundTot->build(decreasing, decBound, nIncSolverVars);
    }
    ipamir_add_hard(incSolver, -decBoundTot->getOutLit(decBound - 1));
    ipamir_add_hard(incSolver, 0);
  }
}

int main(int argc, char **argv) {
  if (argc < 2) {
    cout << "USAGE: ./ipamirbioptsat <input_file_name>\n\n";
    cout << "where <input_file_name> is a DIMACS bicnf instance as specified in the "
            "benchmark description.\n\n";
    cout << "See ./inputs for example input files.\n";
    return 1;
  }

  uint32_t nVars{};
  vector<int32_t> increasing{}, decreasing{};

  void *incSolver = ipamir_init();
  void *decSolver = ipasir_init();

  cout << "c Solving with solver: " << ipamir_signature() << "\n";
  cout << "c (SAT solver for application: " << ipasir_signature() << ")\n";

  if (!initialize_solvers(incSolver, decSolver, nVars, increasing, decreasing,
                          argv[1])) {
    cout << "c ERROR: error while initializing, terminating!\n";
    return 1;
  }

  if (!bioptsat(incSolver, decSolver, nVars, increasing, decreasing)) {
    cout << "c ERROR: error while solving; terminating!\n";
    return 1;
  }

  ipamir_release(incSolver);
  ipasir_release(decSolver);
}