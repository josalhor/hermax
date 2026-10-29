#include "structuredpb/gswc.hpp"

#include <algorithm>
#include <unordered_map>
#include <limits>
#include <utility>
#include <vector>

namespace structuredpb {
namespace {

using WeightMap = std::unordered_map<int, Weight>;

void add_pairwise_amo(const GroupedLeqConstraint& constraint, CnfFormula& cnf) {
    if (!constraint.emit_amo) {
        return;
    }
    for (const auto& group : constraint.groups) {
        for (std::size_t i = 0; i < group.size(); ++i) {
            for (std::size_t j = i + 1; j < group.size(); ++j) {
                cnf.add_clause({-group[i], -group[j]});
            }
        }
    }
}

WeightMap make_weight_map(const GroupedLeqConstraint& constraint) {
    WeightMap out;
    out.reserve(constraint.terms.size());
    for (const auto& term : constraint.terms) {
        out.emplace(term.lit, term.weight);
    }
    return out;
}

}  // namespace

EncodeResult GswcEncoder::encode(const GroupedLeqConstraint& constraint,
                                 const EncodeOptions& options) const {
    constraint.validate();

    EncodeResult result(options.clause_memory);
    VariableManager vm(options.top_id);
    result.cnf.num_vars = options.top_id;
    add_pairwise_amo(constraint, result.cnf);
    const auto weights = make_weight_map(constraint);

    const std::size_t num_groups = constraint.groups.size();
    if (constraint.bound >= static_cast<Weight>(std::numeric_limits<int>::max())) {
        throw std::invalid_argument("structuredpb: GSWC bound exceeds supported counter dimensions");
    }
    const int k = static_cast<int>(constraint.bound);
    if (num_groups == 0) {
        result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
        result.stats.clauses = result.cnf.clauses.size();
        return result;
    }

    std::vector<std::vector<int>> rows;
    if (num_groups >= 2 && k > 0) {
        rows.resize(num_groups - 1);
        int prefix_cap = 0;
        for (std::size_t i = 0; i + 1 < num_groups; ++i) {
            // Under the group's AMO, only its largest feasible weight can
            // contribute. Thresholds above this prefix capacity are unreachable.
            int group_cap = 0;
            for (int lit : constraint.groups[i]) {
                if (weights.at(lit) <= static_cast<Weight>(k)) {
                    group_cap = std::max(group_cap, static_cast<int>(weights.at(lit)));
                }
            }
            prefix_cap += std::min(k - prefix_cap, group_cap);
            rows[i].resize(static_cast<std::size_t>(prefix_cap) + 1, 0);
            for (int j = 1; j <= prefix_cap; ++j) {
                rows[i][static_cast<std::size_t>(j)] = vm.new_var();
            }
        }
    }

    for (std::size_t gi = 0; gi < num_groups; ++gi) {
        const bool has_output = gi + 1 < num_groups && k > 0;
        const bool has_input = gi > 0 && k > 0;

        if (has_output && has_input) {
            for (std::size_t j = 1; j < rows[gi - 1].size(); ++j) {
                result.cnf.add_clause({-rows[gi - 1][j], rows[gi][j]});
            }
        }

        for (int lit : constraint.groups[gi]) {
            const Weight weight = weights.at(lit);
            if (weight > static_cast<Weight>(k)) {
                result.cnf.add_clause({-lit});
                continue;
            }

            const int w = static_cast<int>(weight);
            if (has_output) {
                for (int j = 1; j <= w; ++j) {
                    result.cnf.add_clause({-lit, rows[gi][static_cast<std::size_t>(j)]});
                }
            }

            if (has_input) {
                for (int j = 1; j <= std::min(k - w, static_cast<int>(rows[gi - 1].size()) - 1); ++j) {
                    if (has_output) {
                        result.cnf.add_clause({
                            -rows[gi - 1][static_cast<std::size_t>(j)],
                            -lit,
                            rows[gi][static_cast<std::size_t>(j + w)],
                        });
                    }
                }
                const int overflow_threshold = k - w + 1;
                if (overflow_threshold < static_cast<int>(rows[gi - 1].size())) {
                    result.cnf.add_clause({
                        -rows[gi - 1][static_cast<std::size_t>(overflow_threshold)], -lit,
                    });
                }
            }
        }
    }

    result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
    result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - options.top_id);
    result.stats.clauses = result.cnf.clauses.size();
    return result;
}

}  // namespace structuredpb
