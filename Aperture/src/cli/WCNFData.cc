#include "WCNFData.h"

#include <limits>

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
WCNFData<TLit, TWeight>::WCNFData(const string& file_path)
    : reader_(file_path) {
  Reset();
  ParseWCNFFile();
}

template <ValidLiteral TLit, ValidWeight TWeight>
void WCNFData<TLit, TWeight>::Reset() {
  max_var = 0;
  weighted = false;
  num_soft_clauses = 0;
  num_hard_clauses = 0;
}

template <ValidLiteral TLit, ValidWeight TWeight>
void WCNFData<TLit, TWeight>::Clear() {
  Reset();
  hard_clauses.clear();
  hard_clauses.shrink_to_fit();
  hard_offsets.clear();
  hard_offsets.shrink_to_fit();
  soft_clauses.clear();
  soft_clauses.shrink_to_fit();
  soft_offsets.clear();
  soft_offsets.shrink_to_fit();
  soft_clauses_weights.clear();
  soft_clauses_weights.shrink_to_fit();
}

template <ValidLiteral TLit, ValidWeight TWeight>
void WCNFData<TLit, TWeight>::ParseWCNFFile() {
  if (*reader_ == EOF) {
    throw invalid_argument("Empty WCNF file.");
  }

  size_t file_size = reader_.GetFileSize();

  size_t est_literals = file_size / 25;
  size_t est_clauses = est_literals / 8;

  hard_clauses.reserve(est_literals);
  hard_offsets.reserve(est_clauses);
  hard_offsets.push_back(0);
  soft_clauses.reserve(est_literals / 10);
  soft_offsets.reserve(est_clauses / 10);
  soft_offsets.push_back(0);
  soft_clauses_weights.reserve(est_clauses / 10);

  vector<TLit> clits;

  auto TruncateSpaces = [&]() {
    while ((*reader_ >= 9 && *reader_ <= 13) || *reader_ == 32) ++reader_;
  };

  auto SkipLine = [&]() {
    while (*reader_ != '\n' && *reader_ != EOF) ++reader_;
    ++reader_;
  };

  auto IsEOL = [&]() { return *reader_ == '\n' || *reader_ == EOF; };

  auto IsDigit = [&]() { return *reader_ >= '0' && *reader_ <= '9'; };

  auto ParseLit = [&]() {
    TruncateSpaces();
    if (IsEOL()) return 0;

    bool neg = (*reader_ == '-');
    if (neg) ++reader_;

    if (!IsDigit()) return 0;

    // Parse literal
    TLit lit = 0;
    while (IsDigit()) lit = lit * 10 + (*reader_ - '0'), ++reader_;

    if (lit == 0) return 0;

    if (lit > max_var) {
      max_var = lit;
    }

    if (neg) {
      lit = -lit;
    }
    return lit;
  };

  while (*reader_ != EOF) {
    TruncateSpaces();

    if (*reader_ == '\n') {
      ++reader_;
      continue;
    }

    if (*reader_ == 'c' || *reader_ == 'p') {
      SkipLine();
      continue;
    }

    bool hard_clause = true;
    TWeight weight = 0;

    TruncateSpaces();
    if (*reader_ == 'h') {
      ++reader_;
      hard_clause = true;
    } else {
      hard_clause = false;
      // Parse weight
      while (IsDigit()) weight = weight * 10 + (*reader_ - '0'), ++reader_;

      if (weight > 1) {
        weighted = true;
      }
      soft_clauses_weights.push_back(weight);
    }

    // Parse clause
    while (!IsEOL()) {
      TLit lit = ParseLit();
      if (lit == 0) break;
      if (hard_clause) {
        hard_clauses.push_back(lit);
      } else {
        soft_clauses.push_back(lit);
      }
    }

    if (!hard_clause) {
      soft_clauses.push_back(0);
      soft_offsets.push_back(soft_clauses.size());
      num_soft_clauses++;
    } else {
      hard_offsets.push_back(hard_clauses.size());
      num_hard_clauses++;
    }

    SkipLine();
  }
}

template <ValidLiteral TLit, ValidWeight TWeight>
void WCNFData<TLit, TWeight>::SortSoftClausesByWeight() {
  std::vector<int> idx(num_soft_clauses);
  std::iota(idx.begin(), idx.end(), 0);
  std::sort(idx.begin(), idx.end(), [&](int a, int b) {
    return soft_clauses_weights[a] < soft_clauses_weights[b];
  });

  std::vector<TLit> new_clauses;
  std::vector<size_t> new_offsets = {0};
  std::vector<TWeight> new_weights;

  new_clauses.reserve(soft_clauses.size());
  new_offsets.reserve(soft_offsets.size());
  new_weights.reserve(soft_clauses_weights.size());

  for (int i : idx) {
    new_clauses.insert(new_clauses.end(),
                       soft_clauses.begin() + soft_offsets[i],
                       soft_clauses.begin() + soft_offsets[i + 1]);
    new_offsets.push_back(new_clauses.size());
    new_weights.push_back(soft_clauses_weights[i]);
  }

  soft_clauses = std::move(new_clauses);
  soft_offsets = std::move(new_offsets);
  soft_clauses_weights = std::move(new_weights);
}

template class Aperture::WCNFData<int32_t, uint64_t>;