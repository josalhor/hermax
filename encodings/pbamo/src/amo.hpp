#ifndef STRUCTUREDPB_AMO_HPP
#define STRUCTUREDPB_AMO_HPP

#include "structuredpb/cnf.hpp"
#include "structuredpb/types.hpp"

namespace structuredpb {

inline void add_amo_groups(const GroupedLeqConstraint& constraint, CnfFormula& cnf,
                           VariableManager& variables) {
    if (!constraint.emit_amo) return;
    for (const auto& group : constraint.groups) {
        if (group.size() < 32) {
            for (std::size_t i = 0; i < group.size(); ++i) {
                for (std::size_t j = i + 1; j < group.size(); ++j) {
                    cnf.add_clause({-group[i], -group[j]});
                }
            }
            continue;
        }
        // A ladder represents exactly one input, including a slack input for none.
        const int slack = variables.new_var();
        std::vector<int> cuts(group.size());
        for (auto& cut : cuts) cut = variables.new_var();
        for (std::size_t i = 1; i < cuts.size(); ++i) {
            cnf.add_clause({-cuts[i], cuts[i - 1]});
        }
        cnf.add_clause({cuts.front(), group.front()});
        cnf.add_clause({-group.front(), -cuts.front()});
        for (std::size_t i = 1; i < group.size(); ++i) {
            cnf.add_clause({-cuts[i - 1], cuts[i], group[i]});
            cnf.add_clause({cuts[i - 1], -group[i]});
            cnf.add_clause({-group[i], -cuts[i]});
        }
        cnf.add_clause({-cuts.back(), slack});
        cnf.add_clause({-slack, cuts.back()});
    }
}

}  // namespace structuredpb

#endif
