#include "../Aperture.h"

using namespace std;
using namespace Aperture;

template <ValidLiteral TLit, ValidWeight TWeight>
vector<TLit> Solver<TLit, TWeight>::GetTotalizer(
    Lits<TLit> lits, TLit selector, optional<uint64_t> rhs_simplification) {
  if (should_dump_) logger_.DumpTotalizer(lits, selector, rhs_simplification);

  if (!ValidLits(lits) || lit_abs<TLit>(selector) > MaxVar()) {
    throw invalid_argument(
        "Invalid literals or selector in GetTotalizer: literals and selector "
        "must be within the range of variables currently in the solver.");
  }

  if (lits.empty()) {
    logger_.Log(
        "Note: Empty totalizer constraint detected. Nothing to encode.");
    return {};
  }
  CallWhenLeavingScope reenable_dump([&]() { logger_.EnableDump(); });
  logger_.DisableDumpTemporarily();

  return totalizer_.EncodeTotalizer(lits, selector, rhs_simplification);
}

template <ValidLiteral TLit, ValidWeight TWeight>
vector<pair<TWeight, TLit>> Solver<TLit, TWeight>::GetGenTotalizer(
    WLits<TLit, TWeight> wlits, TLit selector,
    optional<uint64_t> rhs_simplification) {
  if (should_dump_)
    logger_.DumpGenTotalizer(wlits, selector, rhs_simplification);

  if (!ValidWLits(wlits) || lit_abs<TLit>(selector) > MaxVar()) {
    throw invalid_argument(
        "Invalid weighted literals or selector in GetGenTotalizer: literals "
        "and selector must be within the range of variables currently in the "
        "solver.");
  }

  if (wlits.empty()) {
    logger_.Log(
        "Note: Empty generalized totalizer constraint detected. Nothing to "
        "encode.");
    return {};
  }
  CallWhenLeavingScope reenable_dump([&]() { logger_.EnableDump(); });
  logger_.DisableDumpTemporarily();

  return totalizer_.EncodeGenTotalizer(wlits, selector, rhs_simplification);
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Solver<TLit, TWeight>::AddCardinalityConstraint(Lits<TLit> lits,
                                                     Predicate pred,
                                                     uint64_t rhs,
                                                     optional<TLit> selector) {
  if (should_dump_) logger_.DumpCConstraint(lits, pred, rhs, selector);

  if (!ValidLits(lits) ||
      (selector.has_value() && lit_abs<TLit>(*selector) > MaxVar())) {
    return false;
  }

  CallWhenLeavingScope reenable_dump([&]() { logger_.EnableDump(); });
  logger_.DisableDumpTemporarily();

  if (lits.empty()) {
    logger_.Log(
        "Note: Empty cardinality constraint detected. This constraint will be "
        "ignored.");
    return false;
  }

  bool should_leq_simplify = pred == Predicate::LT || pred == Predicate::LEQ;
  bool should_add_selector = selector.has_value();
  TLit selector_lit = should_add_selector ? selector.value() : 0;

  optional<uint64_t> rhs_simplification =
      pred == Predicate::LT    ? optional<uint64_t>(rhs - 1)
      : pred == Predicate::LEQ ? optional<uint64_t>(rhs)
                               : nullopt;

  const size_t tot_size = rhs_simplification.has_value()
                              ? rhs_simplification.value() + 1
                              : lits.size();

  switch (pred) {
    case Predicate::LT:
      if (rhs == 0) {
        logger_.Log(
            "Unsat cardinality constraint detected: RHS must be greater than 0 "
            "for < cardinality constraints.");
        return false;
      }
      break;
    case Predicate::EQ:
      if (rhs > tot_size) {
        logger_.Log(
            "Unsat cardinality constraint detected: RHS must be less than "
            "or "
            "equal to the number of literals for == cardinality "
            "constraints.");
        return false;
      }
      break;
    case Predicate::GEQ:
      if (rhs > tot_size) {
        logger_.Log(
            "Unsat cardinality constraint detected: RHS must be less than "
            "or "
            "equal to the number of literals for >= cardinality "
            "constraints.");
        return false;
      }
      break;
    case Predicate::GT:
      if (rhs >= tot_size) {
        logger_.Log(
            "Unsat cardinality constraint detected: RHS must be less than "
            "the "
            "number of literals for > cardinality constraints.");
        return false;
      }
      break;
    default:
      break;
  }

  vector<TLit> totalizer = totalizer_.EncodeTotalizer(
      lits, selector, rhs_simplification, should_leq_simplify);

  vector<TLit> tot_clause;
  switch (pred) {
    case Predicate::LT:
      if (rhs - 1 < totalizer.size()) {
        tot_clause.push_back(-totalizer[rhs - 1]);
        if (should_add_selector) {
          tot_clause.push_back(selector_lit);
        }
        AddClause(tot_clause);
      }
      break;
    case Predicate::LEQ:
      if (rhs < totalizer.size()) {
        tot_clause.push_back(-totalizer[rhs]);
        if (should_add_selector) {
          tot_clause.push_back(selector_lit);
        }
        AddClause(tot_clause);
      }
      break;
    case Predicate::EQ:
      if (rhs < totalizer.size()) {
        tot_clause.push_back(-totalizer[rhs]);
        if (should_add_selector) {
          tot_clause.push_back(selector_lit);
        }
        AddClause(tot_clause);
      }
      if (rhs > 0) {
        tot_clause.clear();
        tot_clause.push_back(totalizer[rhs - 1]);
        if (should_add_selector) {
          tot_clause.push_back(selector_lit);
        }
        AddClause(tot_clause);
      }
      break;
    case Predicate::GEQ:
      if (rhs > 0) {
        tot_clause.push_back(totalizer[rhs - 1]);
        if (should_add_selector) {
          tot_clause.push_back(selector_lit);
        }
        AddClause(tot_clause);
      }
      break;
    case Predicate::GT:
      tot_clause.push_back(totalizer[rhs]);
      if (should_add_selector) {
        tot_clause.push_back(selector_lit);
      }
      AddClause(tot_clause);
      break;
  }
  return true;
}

template <ValidLiteral TLit, ValidWeight TWeight>
bool Solver<TLit, TWeight>::AddPBConstraint(WLits<TLit, TWeight> wlits,
                                            Predicate pred, uint64_t rhs,
                                            std::optional<TLit> selector) {
  if (should_dump_) {
    logger_.DumpPBConstraint(wlits, pred, rhs, optional<TLit>(selector));
  }

  if (!ValidWLits(wlits) ||
      (selector.has_value() && lit_abs<TLit>(*selector) > MaxVar())) {
    return false;
  }

  CallWhenLeavingScope reenable_dump([&]() { logger_.EnableDump(); });
  logger_.DisableDumpTemporarily();

  if (wlits.empty()) {
    logger_.Log(
        "Note: Empty pseudo-Boolean constraint detected. This constraint "
        "will "
        "be ignored.");
    return false;
  }

  vector<pair<TWeight, TLit>> sorted_wlits(wlits.begin(), wlits.end());
  sort(sorted_wlits.begin(), sorted_wlits.end(),
       [](const pair<TWeight, TLit>& a, const pair<TWeight, TLit>& b) {
         return a.first < b.first;
       });

  switch (pred) {
    case Predicate::LT:
      if (rhs <= sorted_wlits[0].first) {
        logger_.Log(
            "Unsat pseudo-Boolean constraint detected: RHS must be greater "
            "than the minimum weight of a literal for < pseudo-Boolean "
            "constraints.");
        return false;
      }
      break;
    case Predicate::LEQ:
      if (rhs < sorted_wlits[0].first) {
        logger_.Log(
            "Unsat pseudo-Boolean constraint detected: RHS must be greater "
            "than or equal to the minimum weight of a literal for <= "
            "pseudo-Boolean constraints.");
        return false;
      }
      break;
    default:
      logger_.Log(
          "Error: Predicate not supported for pseudo-Boolean constraints. "
          "Only "
          "< and <= are currently supported.");
      return false;
  }

  vector<pair<TWeight, TLit>> gen_totalizer = totalizer_.EncodeGenTotalizer(
      sorted_wlits, selector,
      pred == Predicate::LT    ? optional<uint64_t>(rhs - 1)
      : pred == Predicate::LEQ ? optional<uint64_t>(rhs)
                               : nullopt);
  // Find an output variable with weight GTE rhs
  auto it = lower_bound(gen_totalizer.begin(), gen_totalizer.end(), rhs,
                        [](const pair<TWeight, TLit>& a, const uint64_t& b) {
                          return a.first < b;
                        });
  auto AddUpperBoundClause = [&]() {
    int index = static_cast<int>(it - gen_totalizer.begin());
    TLit clause[] = {-gen_totalizer[index].second};
    AddClause(clause);
  };
  switch (pred) {
    case Predicate::LT: {
      if (it != gen_totalizer.end()) {
        AddUpperBoundClause();
      }
      break;
    }
    case Predicate::LEQ: {
      if (it != gen_totalizer.end()) {
        if (it->first == rhs && ++it == gen_totalizer.end()) {
          break;  // Found rhs but it was the largest weight
        }
        AddUpperBoundClause();
      }
      break;
    }
    default:
      return false;
  }
  return true;
}

template class Aperture::Solver<int32_t, uint64_t>;