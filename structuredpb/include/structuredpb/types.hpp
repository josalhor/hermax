#ifndef STRUCTUREDPB_TYPES_HPP
#define STRUCTUREDPB_TYPES_HPP

#include <cstdint>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace structuredpb {

using Weight = std::uint64_t;

struct WeightedLiteral {
    int lit = 0;
    Weight weight = 0;
};

struct GroupedLeqConstraint {
    std::vector<WeightedLiteral> terms;
    std::vector<std::vector<int>> groups;
    Weight bound = 0;
    bool emit_amo = true;

    void validate() const {
        std::unordered_map<int, Weight> weights_by_lit;
        weights_by_lit.reserve(terms.size());
        for (const auto& term : terms) {
            if (term.lit == 0) {
                throw std::invalid_argument("structuredpb: literal id 0 is invalid");
            }
            if (term.weight == 0) {
                throw std::invalid_argument("structuredpb: normalized form requires positive weights");
            }
            if (!weights_by_lit.emplace(term.lit, term.weight).second) {
                throw std::invalid_argument("structuredpb: duplicate literals in weighted terms are not supported");
            }
        }
        std::unordered_set<int> seen;
        seen.reserve(terms.size());
        for (const auto& group : groups) {
            if (group.empty()) {
                throw std::invalid_argument("structuredpb: AMO groups must be non-empty");
            }
            for (int lit : group) {
                if (!weights_by_lit.count(lit)) {
                    throw std::invalid_argument("structuredpb: AMO group references a literal not present in terms");
                }
                if (!seen.insert(lit).second) {
                    throw std::invalid_argument("structuredpb: AMO groups must form a partition of the literals");
                }
            }
        }
        if (seen.size() != terms.size()) {
            throw std::invalid_argument("structuredpb: every weighted literal must appear in exactly one AMO group");
        }
    }

    Weight weight_of(int lit) const {
        for (const auto& term : terms) {
            if (term.lit == lit) {
                return term.weight;
            }
        }
        throw std::invalid_argument("structuredpb: literal missing from weighted terms");
    }
};

}  // namespace structuredpb

#endif
