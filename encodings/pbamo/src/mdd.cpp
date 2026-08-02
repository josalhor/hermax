#include "structuredpb/mdd.hpp"

#include <algorithm>
#include <functional>
#include <unordered_map>
#include <utility>
#include <vector>

namespace structuredpb {
namespace {

constexpr int kTrueTerminal = -1;
constexpr int kFalseTerminal = -2;

struct Node {
    int var = 0;
    int else_child = kTrueTerminal;
    std::vector<std::pair<int, int>> arcs;
};

struct StateKey {
    std::size_t layer = 0;
    Weight remaining = 0;
};

struct StateKeyHash {
    std::size_t operator()(const StateKey& key) const noexcept {
        const auto h1 = std::hash<std::size_t>{}(key.layer);
        const auto h2 = std::hash<Weight>{}(key.remaining);
        return h1 ^ (h2 + 0x9e3779b97f4a7c15ULL + (h1 << 6U) + (h1 >> 2U));
    }
};

bool operator==(const StateKey& lhs, const StateKey& rhs) {
    return lhs.layer == rhs.layer && lhs.remaining == rhs.remaining;
}

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

std::unordered_map<int, Weight> make_weight_map(const GroupedLeqConstraint& constraint) {
    std::unordered_map<int, Weight> out;
    out.reserve(constraint.terms.size());
    for (const auto& term : constraint.terms) {
        out.emplace(term.lit, term.weight);
    }
    return out;
}

}  // namespace

EncodeResult MddEncoder::encode(const GroupedLeqConstraint& constraint,
                                const EncodeOptions& options) const {
    constraint.validate();

    EncodeResult result;
    VariableManager vm(options.top_id);
    result.cnf.num_vars = options.top_id;
    add_pairwise_amo(constraint, result.cnf);
    const auto weights = make_weight_map(constraint);

    const std::size_t num_groups = constraint.groups.size();
    std::vector<Weight> max_group_weight(num_groups, 0);
    for (std::size_t i = 0; i < num_groups; ++i) {
        for (int lit : constraint.groups[i]) {
            max_group_weight[i] = std::max(max_group_weight[i], weights.at(lit));
        }
    }
    std::vector<Weight> suffix_max(num_groups + 1, 0);
    for (std::size_t i = num_groups; i-- > 0;) {
        suffix_max[i] = suffix_max[i + 1] + max_group_weight[i];
    }

    std::vector<Node> nodes;
    std::unordered_map<StateKey, int, StateKeyHash> memo;

    std::function<int(std::size_t, Weight)> build = [&](std::size_t layer, Weight remaining) -> int {
        if (layer == num_groups || remaining >= suffix_max[layer]) {
            return kTrueTerminal;
        }
        const StateKey memo_key{layer, remaining};
        auto memo_it = memo.find(memo_key);
        if (memo_it != memo.end()) {
            return memo_it->second;
        }

        const int else_child = build(layer + 1, remaining);
        std::vector<std::pair<int, int>> arcs;
        arcs.reserve(constraint.groups[layer].size());
        bool all_same = true;
        for (int lit : constraint.groups[layer]) {
            const Weight w = weights.at(lit);
            const int child = w > remaining ? kFalseTerminal : build(layer + 1, remaining - w);
            arcs.push_back({lit, child});
            if (child != else_child) {
                all_same = false;
            }
        }

        if (all_same) {
            memo.emplace(memo_key, else_child);
            return else_child;
        }

        Node node;
        node.var = vm.new_var();
        node.else_child = else_child;
        node.arcs = std::move(arcs);
        nodes.push_back(std::move(node));
        const int node_id = static_cast<int>(nodes.size()) - 1;
        memo.emplace(memo_key, node_id);
        return node_id;
    };

    const int root = build(0, constraint.bound);
    if (root == kFalseTerminal) {
        result.cnf.add_clause({});
    } else if (root >= 0) {
        result.cnf.add_clause({-nodes[static_cast<std::size_t>(root)].var});
    }

    for (const auto& node : nodes) {
        if (node.else_child >= 0) {
            result.cnf.add_clause({
                -nodes[static_cast<std::size_t>(node.else_child)].var,
                node.var,
            });
        } else if (node.else_child == kFalseTerminal) {
            result.cnf.add_clause({node.var});
        }

        for (const auto& [lit, child] : node.arcs) {
            if (child == node.else_child || child == kTrueTerminal) {
                continue;
            }
            if (child == kFalseTerminal) {
                result.cnf.add_clause({-lit, node.var});
            } else {
                result.cnf.add_clause({
                    -nodes[static_cast<std::size_t>(child)].var,
                    -lit,
                    node.var,
                });
            }
        }
    }

    result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
    result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - options.top_id);
    result.stats.clauses = result.cnf.clauses.size();
    return result;
}

}  // namespace structuredpb
