#ifndef STRUCTUREDPB_PREPROCESS_LEQ_HPP
#define STRUCTUREDPB_PREPROCESS_LEQ_HPP

#include "structuredpb/cnf.hpp"
#include "structuredpb/types.hpp"

#include <algorithm>
#include <unordered_map>

namespace structuredpb::detail {

// AMOs must already have been emitted (or supplied by the caller), since
// removing an overweight literal from the PB must not remove its AMO facts.
struct PreprocessedLeq {
    GroupedLeqConstraint constraint;
    bool redundant = true;
};

inline PreprocessedLeq preprocess_leq(const GroupedLeqConstraint& input, CnfFormula& cnf) {
    PreprocessedLeq result;
    auto& output = result.constraint;
    output.bound = input.bound;
    output.emit_amo = false;
    output.terms.reserve(input.terms.size());
    output.groups.reserve(input.groups.size());
    std::unordered_map<int, Weight> weights;
    weights.reserve(input.terms.size());
    for (const auto& term : input.terms) weights.emplace(term.lit, term.weight);

    // q*x + r*~x = min(q,r) + |q-r|*(x or ~x).
    // Original AMO clauses stay intact, including facts involving a removed
    // polarity. Perform subtraction before overweight/capacity checks.
    for (const auto& term : input.terms) {
        if (term.lit <= 0) continue;
        auto opposite = weights.find(-term.lit);
        if (opposite == weights.end()) continue;
        auto current = weights.find(term.lit);
        const Weight common = std::min(current->second, opposite->second);
        if (common > output.bound) {
            cnf.add_clause({});
            return result;
        }
        output.bound -= common;
        current->second -= common;
        opposite->second -= common;
    }

    for (const auto& term : input.terms) {
        const Weight weight = weights.at(term.lit);
        if (!weight) continue;
        if (weight > output.bound) cnf.add_clause({-term.lit});
        else output.terms.push_back({term.lit, weight});
    }
    Weight capacity = 0;
    for (const auto& group : input.groups) {
        std::vector<int> kept;
        Weight maximum = 0;
        for (int lit : group) {
            const Weight weight = weights.at(lit);
            if (weight && weight <= output.bound) {
                kept.push_back(lit);
                maximum = std::max(maximum, weight);
            }
        }
        if (!kept.empty()) output.groups.push_back(std::move(kept));
        if (result.redundant) {
            // Saturate by comparing to the bound, not by adding potentially
            // overflowing unsigned weights.
            if (maximum > output.bound - capacity) result.redundant = false;
            else capacity += maximum;
        }
    }
    return result;
}

}  // namespace structuredpb::detail
#endif
