#include "Totalizer.h"

#include <deque>

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
vector<TLit> Totalizer<TLit, TWeight>::EncodeTotalizer(
    Lits<TLit> lits, optional<TLit> selector,
    optional<uint64_t> rhs_simplification, bool leq_simplification) {
  if (lits.empty()) return {};
  const bool should_rhs_simplify = rhs_simplification.has_value();
  const bool should_add_selector = selector.has_value();
  const TLit selector_lit = should_add_selector ? selector.value() : 0;
  const uint64_t rhs_simp_limit =
      should_rhs_simplify ? rhs_simplification.value() + 1 : 0;

  auto AddClauseFunc = [&](vector<TLit>& clause) {
    if (should_add_selector) {
      clause.push_back(selector_lit);
    }
    this->AddClause_(clause);
  };

  auto CheckRhsSimplification = [&](uint64_t value) {
    return should_rhs_simplify ? min(value, rhs_simp_limit) : value;
  };

  auto Merge = [&](const vector<TLit>& left, const vector<TLit>& right) {
    uint64_t merged_max_size = left.size() + right.size();
    uint64_t merged_size = CheckRhsSimplification(merged_max_size);
    vector<TLit> merged;
    merged.reserve(merged_size);
    for (uint64_t i = 0; i < merged_size; i++) {
      merged.emplace_back(this->NewVar_());
    }
    return merged;
  };

  vector<TLit> clause;
  clause.reserve(3);
  auto AddParentClauses = [&](const vector<TLit>& left,
                              const vector<TLit>& right,
                              const vector<TLit>& parent) {
    size_t left_size = left.size();
    size_t right_size = right.size();
    size_t parent_size = parent.size();
    for (size_t a = 0; a <= left_size; a++) {
      for (size_t b = 0; b <= right_size; b++) {
        size_t sum = a + b;
        if (sum > 0 && sum <= parent_size) {
          clause.clear();
          if (a > 0) clause.push_back(-left[a - 1]);
          if (b > 0) clause.push_back(-right[b - 1]);
          clause.push_back(parent[sum - 1]);
          AddClauseFunc(clause);
        }
        if (sum < parent_size) {
          clause.clear();
          if (a < left_size) clause.push_back(left[a]);
          if (b < right_size) clause.push_back(right[b]);
          clause.push_back(-parent[sum]);
          AddClauseFunc(clause);
        }
      }
    }
  };

  auto AddParentClausesLEQ = [&](const vector<TLit>& left,
                                 const vector<TLit>& right,
                                 const vector<TLit>& parent) {
    size_t left_size = left.size();
    size_t right_size = right.size();
    for (size_t a = 0; a < left_size; a++) {
      for (size_t b = 0; b < right_size; b++) {
        size_t sum = a + b + 2;
        if (should_rhs_simplify) {
          if (a + 1 >= rhs_simp_limit || b + 1 >= rhs_simp_limit) {
            continue;
          }
          sum = min(sum, rhs_simp_limit);
        }
        clause.clear();
        clause.push_back(-left[a]);
        clause.push_back(-right[b]);
        clause.push_back(parent[sum - 1]);
        AddClauseFunc(clause);
      }
    }
    for (size_t a = 0; a < left_size; a++) {
      clause.clear();
      clause.push_back(-left[a]);
      clause.push_back(parent[CheckRhsSimplification(a + 1) - 1]);
      AddClauseFunc(clause);
    }
    for (size_t b = 0; b < right_size; b++) {
      clause.clear();
      clause.push_back(-right[b]);
      clause.push_back(parent[CheckRhsSimplification(b + 1) - 1]);
      AddClauseFunc(clause);
    }
  };

  deque<vector<TLit>> q;
  for (TLit lit : lits) {
    vector<TLit>& leaf_node = q.emplace_back();
    leaf_node.emplace_back(lit);
  }

  while (q.size() > 1) {
    vector<TLit> left = std::move(q.front());
    q.pop_front();
    vector<TLit> right = std::move(q.front());
    q.pop_front();
    vector<TLit> parent = Merge(left, right);
    leq_simplification ? AddParentClausesLEQ(left, right, parent)
                       : AddParentClauses(left, right, parent);
    q.push_back(std::move(parent));
  }
  vector<TLit> output = std::move(q.front());
  q.pop_front();

  return output;
}

template <ValidLiteral TLit, ValidWeight TWeight>
vector<pair<TWeight, TLit>> Totalizer<TLit, TWeight>::EncodeGenTotalizer(
    WLits<TLit, TWeight> wlits, optional<TLit> selector,
    optional<uint64_t> rhs_simplification) {
  if (wlits.empty()) return {};
  const bool should_rhs_simplify = rhs_simplification.has_value();
  const bool should_add_selector = selector.has_value();
  const TLit selector_lit = should_add_selector ? selector.value() : 0;
  const uint64_t rhs_simp_limit =
      should_rhs_simplify ? rhs_simplification.value() + 1 : 0;

  auto AddClauseFunc = [&](vector<TLit>& clause) {
    if (should_add_selector) {
      clause.push_back(selector_lit);
    }
    this->AddClause_(clause);
  };

  auto CheckRhsSimplification = [&](TWeight value) {
    return should_rhs_simplify ? min(value, rhs_simp_limit) : value;
  };

  vector<TLit> clause;
  clause.reserve(3);
  auto AddAndMerge = [&](const vector<pair<TWeight, TLit>>& left,
                         const vector<pair<TWeight, TLit>>& right) {
    // Find all possible weights and create variables for them
    size_t reserved_size =
        left.size() + right.size() + left.size() * right.size();
    unordered_map<TWeight, TLit> weight_to_lit;
    weight_to_lit.reserve(reserved_size);

    auto InsertWeight = [&](TWeight weight) {
      weight = CheckRhsSimplification(weight);
      auto [it, inserted] = weight_to_lit.try_emplace(weight, 0);
      if (inserted) {
        it->second = this->NewVar_();
      }
    };

    for (const auto& [l_weight, l_lit] : left) {
      InsertWeight(l_weight);
    }
    for (const auto& [r_weight, r_lit] : right) {
      InsertWeight(r_weight);
    }
    for (const auto& [l_weight, l_lit] : left) {
      for (const auto& [r_weight, r_lit] : right) {
        InsertWeight(l_weight + r_weight);
      }
    }

    // Add clauses
    for (const auto& [l_weight, l_lit] : left) {
      for (const auto& [r_weight, r_lit] : right) {
        TWeight p_weight = l_weight + r_weight;
        if (should_rhs_simplify) {
          if (l_weight >= rhs_simp_limit || r_weight >= rhs_simp_limit) {
            continue;  // The (-sw v pw') clauses are sufficient
          }
          p_weight = min(p_weight, rhs_simp_limit);
        }
        // (-qw1 v -rw2 v pw3)
        clause.clear();
        clause.push_back(-l_lit);
        clause.push_back(-r_lit);
        clause.push_back(weight_to_lit[p_weight]);
        AddClauseFunc(clause);
      }
    }
    for (const auto& [weight, lit] : left) {
      // (-sw v pw') where sw is from Q
      clause.clear();
      clause.push_back(-lit);
      clause.push_back(weight_to_lit[CheckRhsSimplification(weight)]);
      AddClauseFunc(clause);
    }
    for (const auto& [weight, lit] : right) {
      // (-sw v pw') where sw is from R
      clause.clear();
      clause.push_back(-lit);
      clause.push_back(weight_to_lit[CheckRhsSimplification(weight)]);
      AddClauseFunc(clause);
    }

    // Create a merged node of left and right
    vector<pair<TWeight, TLit>> merged;
    merged.reserve(weight_to_lit.size());
    for (const auto& [weight, lit] : weight_to_lit) {
      merged.emplace_back(weight, lit);
    }
    return merged;
  };

  deque<vector<pair<TWeight, TLit>>> q;
  vector<pair<TWeight, TLit>> wlits_vector(wlits.begin(), wlits.end());
  sort(wlits_vector.begin(), wlits_vector.end());
  for (const auto& [weight, lit] : wlits_vector) {
    auto& leaf_node = q.emplace_back();
    leaf_node.emplace_back(weight, lit);
  }

  while (q.size() > 1) {
    vector<pair<TWeight, TLit>> left = std::move(q.front());
    q.pop_front();
    vector<pair<TWeight, TLit>> right = std::move(q.front());
    q.pop_front();
    vector<pair<TWeight, TLit>> parent = AddAndMerge(left, right);
    q.push_back(std::move(parent));
  }
  vector<pair<TWeight, TLit>> output = std::move(q.front());
  q.pop_front();
  sort(output.begin(), output.end());

  return output;
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Totalizer<TLit, TWeight>::IsLeqTotExceedsThr(
    Lits<TLit> lits, optional<uint64_t> rhs_simplification,
    uint64_t clauses_threshold) {
  if (lits.empty()) return true;
  const bool should_rhs_simplify = rhs_simplification.has_value();
  const uint64_t rhs_simp_limit =
      should_rhs_simplify ? rhs_simplification.value() + 1 : 0;

  auto CheckRhsSimplification = [&](uint64_t value) {
    return should_rhs_simplify ? min(value, rhs_simp_limit) : value;
  };

  uint64_t clause_count = 0;
  auto CountParentClauses = [&](const vector<TLit>& left,
                                const vector<TLit>& right) {
    size_t left_size = left.size();
    size_t right_size = right.size();
    clause_count += left_size + right_size;
    if (clause_count > clauses_threshold) return;
    for (size_t a = 0; a < left_size; a++) {
      for (size_t b = 0; b < right_size; b++) {
        if (should_rhs_simplify &&
            (a + 1 >= rhs_simp_limit || b + 1 >= rhs_simp_limit)) {
          continue;
        }
        clause_count++;
      }
    }
  };

  deque<vector<TLit>> q;
  for (TLit lit : lits) {
    vector<TLit>& leaf_node = q.emplace_back();
    leaf_node.emplace_back(lit);
  }

  while (q.size() > 1) {
    vector<TLit> left = std::move(q.front());
    q.pop_front();
    vector<TLit> right = std::move(q.front());
    q.pop_front();
    CountParentClauses(left, right);
    if (clause_count > clauses_threshold) return false;
    uint64_t merged_max_size = left.size() + right.size();
    uint64_t merged_size = CheckRhsSimplification(merged_max_size);
    if (merged_size > clauses_threshold) return false;
    q.emplace_back(vector<TLit>(merged_size));
  }

  return clause_count <= clauses_threshold;
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Totalizer<TLit, TWeight>::IsLeqGenTotExceedsThr(
    WLits<TLit, TWeight> wlits, optional<uint64_t> rhs_simplification,
    uint64_t clauses_threshold) {
  if (wlits.empty()) return true;
  const bool should_rhs_simplify = rhs_simplification.has_value();
  const uint64_t rhs_simp_limit =
      should_rhs_simplify ? rhs_simplification.value() + 1 : 0;

  auto CheckRhsSimplification = [&](TWeight value) {
    return should_rhs_simplify ? min(value, rhs_simp_limit) : value;
  };

  uint64_t clause_count = 0;
  auto CountAndMerge = [&](const vector<pair<TWeight, TLit>>& left,
                           const vector<pair<TWeight, TLit>>& right,
                           size_t parent_size) {
    unordered_map<TWeight, TLit> weight_to_lit;
    weight_to_lit.reserve(parent_size);

    auto InsertWeight = [&](TWeight weight) {
      weight = CheckRhsSimplification(weight);
      weight_to_lit.try_emplace(weight, 0);
    };

    for (const auto& [l_weight, l_lit] : left) {
      InsertWeight(l_weight);
    }
    for (const auto& [r_weight, r_lit] : right) {
      InsertWeight(r_weight);
    }
    for (const auto& [l_weight, l_lit] : left) {
      for (const auto& [r_weight, r_lit] : right) {
        InsertWeight(l_weight + r_weight);
      }
    }

    // Count clauses
    clause_count += left.size() + right.size();
    if (clause_count > clauses_threshold) return vector<pair<TWeight, TLit>>();
    for (const auto& [l_weight, l_lit] : left) {
      for (const auto& [r_weight, r_lit] : right) {
        if (should_rhs_simplify &&
            (l_weight >= rhs_simp_limit || r_weight >= rhs_simp_limit)) {
          continue;
        }
        clause_count++;
      }
    }
    if (clause_count > clauses_threshold) return vector<pair<TWeight, TLit>>();

    // Create a merged node of left and right
    vector<pair<TWeight, TLit>> merged;
    merged.reserve(weight_to_lit.size());
    for (const auto& [weight, lit] : weight_to_lit) {
      merged.emplace_back(weight, lit);
    }
    return merged;
  };

  deque<vector<pair<TWeight, TLit>>> q;
  vector<pair<TWeight, TLit>> wlits_vector(wlits.begin(), wlits.end());
  sort(wlits_vector.begin(), wlits_vector.end());
  for (const auto& [weight, lit] : wlits_vector) {
    auto& leaf_node = q.emplace_back();
    leaf_node.emplace_back(weight, lit);
  }

  while (q.size() > 1) {
    vector<pair<TWeight, TLit>> left = std::move(q.front());
    q.pop_front();
    vector<pair<TWeight, TLit>> right = std::move(q.front());
    q.pop_front();
    size_t parent_size =
        left.size() + right.size() + left.size() * right.size();
    if (parent_size > clauses_threshold) {
      return false;
    }
    vector<pair<TWeight, TLit>> parent =
        CountAndMerge(left, right, parent_size);
    if (clause_count > clauses_threshold) return false;
    q.push_back(std::move(parent));
  }

  return clause_count <= clauses_threshold;
}

template class Aperture::Totalizer<int32_t, uint64_t>;