/*
 * Author: Christoph Jabs - christoph.jabs@helsinki.fi
 */

#ifndef _totalizer_hpp_INCLUDED
#define _totalizer_hpp_INCLUDED

#include <iostream>
#include <vector>

extern "C" {
#include "ipasir.h"
#include "ipamir.h"
}

using std::vector;

enum SolverType { MAXSAT_SOLVER, SAT_SOLVER };

// Implementation of the totalizer encoding for incremental use
// Limited implementation: does only support upper bounds and extending the
// upper value
class Totalizer {
private:
  uint32_t upper{};          // Maximum encoded right hand side
  vector<int32_t> outLits{}; // The set of output literals

  vector<int32_t> tmpBuffer{}; // Temporary buffer for building the totalizer

  void *solver; // The solver that the totalizer is in

  SolverType solverType{}; // The type of the solver that the totalizer is in

  vector<vector<int32_t>> treeLeft{};  // Left hand sides of the adders
  vector<vector<int32_t>> treeRight{}; // Right hand sides of the adders
  vector<vector<int32_t>> treeOut{};   // Outputs of the adders
  vector<uint32_t> treeUpper{};        // Maximum encoded value of the adders

  void toCnf(vector<int32_t> &,
             uint32_t &); // Encode variables in tmpBuffer to outputs
  void adder(vector<int32_t> &, vector<int32_t> &,
             vector<int32_t> &); // Encode adder
  inline void solverAdd(int32_t lit) {
    switch (solverType) {
    case MAXSAT_SOLVER:
      ipamir_add_hard(solver, lit);
      break;
    case SAT_SOLVER:
      ipasir_add(solver, lit);
      break;
    }
  }

public:
  Totalizer(void *, SolverType);
  void build(const vector<int32_t> &, uint32_t,
             uint32_t &);     // Build totalizer over inLits up to upper
  void updateUpper(uint32_t); // Update the maximum encoded value
  int32_t getOutLit(
      uint32_t bound) const { // Get the output literal corresponding to bound
    return outLits[bound];
  }
};

#endif