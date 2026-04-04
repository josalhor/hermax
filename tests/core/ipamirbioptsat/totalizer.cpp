/*
 * Author: Christoph Jabs - christoph.jabs@helsinki.fi
 */

#include "totalizer.hpp"

#include <cassert>
#include <cmath>

Totalizer::Totalizer(void *solver, SolverType solverType)
    : solver(solver), solverType(solverType) {}

void Totalizer::build(const vector<int32_t> &inLits, uint32_t _upper,
                      uint32_t &nVars) {
  outLits.clear();

  upper = _upper;
  if (upper > inLits.size())
    upper = inLits.size();

  // Corner case (single literal)
  if (inLits.size() == 1) {
    outLits.push_back(inLits[0]);
    return;
  }

  // Create out literals
  for (uint32_t i = 0; i < inLits.size(); i++) {
    outLits.push_back(++nVars);
  }

  tmpBuffer = inLits;

  toCnf(outLits, nVars);
  assert(tmpBuffer.size() == 0);
}

void Totalizer::toCnf(vector<int32_t> &lits, uint32_t &nVars) {
  vector<int32_t> left{};
  vector<int32_t> right{};

  assert(lits.size() > 1);
  uint32_t split = floor(lits.size() / 2);

  for (uint32_t i = 0; i < lits.size(); i++) {
    if (i < split) {
      // left branch
      if (split == 1) {
        assert(tmpBuffer.size() > 0);
        left.push_back(tmpBuffer.back());
        tmpBuffer.pop_back();
      } else {
        left.push_back(++nVars);
      }
    } else {
      // right branch
      if (lits.size() - split == 1) {
        assert(tmpBuffer.size() > 0);
        right.push_back(tmpBuffer.back());
        tmpBuffer.pop_back();
      } else {
        right.push_back(++nVars);
      }
    }
  }

  if (left.size() > 1)
    toCnf(left, nVars);
  if (right.size() > 1)
    toCnf(right, nVars);
  adder(left, right, lits);
}

void Totalizer::adder(vector<int32_t> &left, vector<int32_t> &right,
                      vector<int32_t> &output) {
  assert(output.size() == left.size() + right.size());

  // Save tree for iterative extension
  treeLeft.push_back(left);
  treeRight.push_back(right);
  treeOut.push_back(output);
  treeUpper.push_back(upper);

  // Encode adder
  for (uint32_t i = 0; i <= left.size(); i++) {
    for (uint32_t j = 0; j <= right.size(); j++) {
      if (i + j > upper + 1)
        continue;

      if (j != 0)
        solverAdd(-right[j - 1]);
      if (i != 0)
        solverAdd(-left[i - 1]);
      if (i != 0 || j != 0) {
        solverAdd(output[i + j - 1]);
        solverAdd(0);
      }
    }
  }
}

void Totalizer::updateUpper(uint32_t _upper) {
  if (_upper <= upper)
    return;
  upper = _upper;
  if (upper > outLits.size())
    upper = outLits.size();

  for (uint32_t z = 0; z < treeUpper.size(); z++) {
    // Encode additional adder clauses
    for (uint32_t i = 0; i <= treeLeft[z].size(); i++) {
      for (uint32_t j = 0; j <= treeRight[z].size(); j++) {
        if (i + j > upper + 1 || i + j <= treeUpper[z] + 1)
          continue;

        if (j != 0)
          solverAdd(-treeRight[z][j - 1]);
        if (i != 0)
          solverAdd(-treeLeft[z][i - 1]);
        if (i != 0 || j != 0) {
          solverAdd(treeOut[z][i + j - 1]);
          solverAdd(0);
        }
      }
    }
    treeUpper[z] = upper;
  }
}