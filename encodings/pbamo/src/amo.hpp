#ifndef STRUCTUREDPB_AMO_HPP
#define STRUCTUREDPB_AMO_HPP

#include "structuredpb/cnf.hpp"
#include "structuredpb/types.hpp"

namespace structuredpb {

inline void add_amo_group(const std::vector<int>& group, CnfFormula& cnf,
                          VariableManager& variables, bool equality = false) {
    const auto n = group.size();
    if (n <= (equality ? 5u : 6u)) {
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = i + 1; j < n; ++j) {
                cnf.add_clause({-group[i], -group[j]});
            }
        }
        if (equality) cnf.add_clause(group);
        return;
    }
    // A cut means no input in this prefix has been selected.
    std::vector<int> cuts(n - 1);
    for (auto& cut : cuts) cut = variables.new_var();
    cnf.add_clause({-group.front(), -cuts.front()});
    for (std::size_t i = 1; i < cuts.size(); ++i) {
        cnf.add_clause({cuts[i - 1], -cuts[i]});
        cnf.add_clause({-group[i], cuts[i - 1]});
        cnf.add_clause({-group[i], -cuts[i]});
    }
    cnf.add_clause({cuts.back(), -group.back()});
    if (equality) {
        cnf.add_clause(group);
    } else {
        // Close the counter: it cannot invent a selection when all inputs are false.
        Clause closing{cuts.back()};
        closing.insert(closing.end(), group.begin(), group.end() - 1);
        cnf.add_clause(std::move(closing));
    }
}

inline void add_amo_groups(const GroupedLeqConstraint& constraint, CnfFormula& cnf,
                           VariableManager& variables) {
    if (!constraint.emit_amo) return;
    for (const auto& group : constraint.groups) {
        add_amo_group(group, cnf, variables);
    }
}

}  // namespace structuredpb

#endif
