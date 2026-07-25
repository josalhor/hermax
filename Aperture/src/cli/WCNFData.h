#pragma once

#include <algorithm>
#include <cstdint>
#include <memory>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

#include "../ATypes.h"
#include "CNFReader.h"

namespace Aperture {

template <ValidLiteral TLit, ValidWeight TWeight>
struct WCNFData {
  std::vector<TLit> hard_clauses;
  std::vector<size_t> hard_offsets;
  std::vector<TLit> soft_clauses;
  std::vector<size_t> soft_offsets;
  std::vector<TWeight> soft_clauses_weights;

  TLit max_var;
  bool weighted;
  int num_hard_clauses;
  int num_soft_clauses;

  WCNFData(const std::string& file_path);
  void Reset();
  void Clear();

  void SortSoftClausesByWeight();

 private:
  CNFReader reader_;

  void ParseWCNFFile();
};
};  // namespace Aperture