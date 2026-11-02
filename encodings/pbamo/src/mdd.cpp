#include "amo.hpp"
#include "preprocess_leq.hpp"
#include "structuredpb/mdd.hpp"

#include <algorithm>
#include <functional>
#include <limits>
#include <unordered_map>
#include <utility>
#include <vector>

namespace structuredpb {
namespace {

constexpr int kTrueTerminal = -1;
constexpr int kFalseTerminal = -2;
#ifndef STRUCTUREDPB_MDD_RECURSIVE_LIMIT
#define STRUCTUREDPB_MDD_RECURSIVE_LIMIT 512
#endif
constexpr std::size_t kRecursiveLimit = STRUCTUREDPB_MDD_RECURSIVE_LIMIT;

using Arc = std::pair<int, int>;

struct Node {
    int var = 0;
    int else_child = kTrueTerminal;
    std::vector<Arc> arcs;
    bool is_literal = false;
};

struct StateKey {
    std::size_t layer = 0;
    Weight remaining = 0;
    bool operator==(const StateKey& other) const {
        return layer == other.layer && remaining == other.remaining;
    }
};

void mix_hash(std::size_t& hash, std::size_t value) {
    hash ^= value + 0x9e3779b97f4a7c15ULL + (hash << 6U) + (hash >> 2U);
}

struct StateKeyHash {
    std::size_t operator()(const StateKey& key) const noexcept {
        // Separate neighboring layers when remaining budgets form dense ranges.
        return std::hash<Weight>{}(key.remaining) ^
            (std::hash<std::size_t>{}(key.layer) * 0x9e3779b97f4a7c15ULL);
    }
};

struct Group {
    std::vector<WeightedLiteral> terms;
    Weight maximum = 0;
};

std::vector<Group> make_ordered_groups(const GroupedLeqConstraint& constraint) {
    std::unordered_map<int, Weight> weights;
    weights.reserve(constraint.terms.size());
    for (const auto& term : constraint.terms) weights.emplace(term.lit, term.weight);
    std::vector<Group> groups;
    groups.reserve(constraint.groups.size());
    for (const auto& literals : constraint.groups) {
        Group group;
        for (int lit : literals) {
            const Weight weight = weights.at(lit);
            group.terms.push_back({lit, weight});
            group.maximum = std::max(group.maximum, weight);
        }
        std::stable_sort(group.terms.begin(), group.terms.end(), [](const auto& a, const auto& b) {
            return a.weight > b.weight;
        });
        groups.push_back(std::move(group));
    }
    // Heuristic: process the largest possible contributions first, matching
    // PBLib's descending-weight order when every group is a singleton.
    std::stable_sort(groups.begin(), groups.end(), [](const Group& a, const Group& b) {
        return a.maximum > b.maximum;
    });
    return groups;
}


struct SuffixMaximum {
    Weight value = 0;
    bool overflow = false;
};

class Diagram {
public:
    Diagram(const std::vector<Group>& groups, VariableManager& variables)
        : groups_(groups), variables_(variables), suffix_(groups.size() + 1) {
        for (std::size_t i = groups.size(); i-- > 0;) {
            const auto next = suffix_[i + 1];
            if (next.overflow || groups[i].maximum > std::numeric_limits<Weight>::max() - next.value) {
                suffix_[i] = {std::numeric_limits<Weight>::max(), true};
            } else {
                suffix_[i].value = next.value + groups[i].maximum;
            }
        }
    }

    void encode(Weight bound, CnfFormula& cnf) {
        const int root = build(0, bound);
        if (root == kFalseTerminal) cnf.add_clause({});
        else if (root >= 0) cnf.add_clause({-nodes_[static_cast<std::size_t>(root)].var});
        for (const auto& node : nodes_) emit_node(node, cnf);
    }

private:
    int build(std::size_t layer, Weight remaining) {
        if (layer == groups_.size() || (!suffix_[layer].overflow && remaining >= suffix_[layer].value)) {
            return kTrueTerminal;
        }
        const StateKey key{layer, remaining};
        const auto known = states_.find(key);
        if (known != states_.end()) return known->second;

        if (layer >= kRecursiveLimit) return build_iterative(layer, remaining);

        const int else_child = build(layer + 1, remaining);
        std::vector<Arc> arcs;
        arcs.reserve(groups_[layer].terms.size());
        for (const auto& term : groups_[layer].terms) {
            const int child = term.weight > remaining ? kFalseTerminal : build(layer + 1, remaining - term.weight);
            // Choosing this member behaves like the none-selected branch.
            if (child != else_child) arcs.emplace_back(term.lit, child);
        }
        const int result = arcs.empty() ? else_child : intern(else_child, std::move(arcs));
        states_.emplace(key, result);
        return result;
    }

    // Continue the same depth-first traversal on a heap stack when the
    // native call stack approaches its conservative depth limit.
    int build_iterative(std::size_t layer, Weight remaining) {
        struct Frame {
            std::size_t layer;
            Weight remaining;
            std::size_t next = 0;
            int else_child = kTrueTerminal;
            bool have_else = false;
            std::vector<Arc> arcs;
        };
        std::vector<Frame> stack;
        stack.push_back(Frame{layer, remaining});
        int completed = kTrueTerminal;
        bool returning = false;
        while (!stack.empty()) {
            auto& frame = stack.back();
            if (returning) {
                if (!frame.have_else) {
                    frame.else_child = completed;
                    frame.have_else = true;
                } else {
                    const auto& term = groups_[frame.layer].terms[frame.next++];
                    if (completed != frame.else_child) frame.arcs.emplace_back(term.lit, completed);
                }
                returning = false;
                continue;
            }
            if (!frame.have_else) {
                if (frame.layer == groups_.size() ||
                    (!suffix_[frame.layer].overflow && frame.remaining >= suffix_[frame.layer].value)) {
                    completed = kTrueTerminal;
                    stack.pop_back();
                    returning = true;
                    continue;
                }
                const auto it = states_.find(StateKey{frame.layer, frame.remaining});
                if (it != states_.end()) {
                    completed = it->second;
                    stack.pop_back();
                    returning = true;
                    continue;
                }
                frame.arcs.reserve(groups_[frame.layer].terms.size());
                stack.push_back(Frame{frame.layer + 1, frame.remaining});
                continue;
            }
            if (frame.next < groups_[frame.layer].terms.size()) {
                const auto& term = groups_[frame.layer].terms[frame.next];
                if (term.weight > frame.remaining) {
                    completed = kFalseTerminal;
                    returning = true;
                } else {
                    stack.push_back(Frame{frame.layer + 1, frame.remaining - term.weight});
                }
                continue;
            }
            const StateKey key{frame.layer, frame.remaining};
            completed = frame.arcs.empty() ? frame.else_child : intern(frame.else_child, std::move(frame.arcs));
            states_.emplace(key, completed);
            stack.pop_back();
            returning = true;
        }
        return completed;
    }

    int intern(int else_child, std::vector<Arc> arcs) {
        auto hash = std::hash<int>{}(else_child);
        for (const auto& arc : arcs) {
            mix_hash(hash, std::hash<int>{}(arc.first));
            mix_hash(hash, std::hash<int>{}(arc.second));
        }
        // Hashes only select candidates. Compare the full signed literal/child
        // signature, so a collision can never merge different predicates.
        const auto candidates = unique_.equal_range(hash);
        for (auto it = candidates.first; it != candidates.second; ++it) {
            const auto& node = nodes_[static_cast<std::size_t>(it->second)];
            if (node.else_child == else_child && node.arcs == arcs) return it->second;
        }
        Node node;
        node.else_child = else_child;
        node.is_literal = else_child == kTrueTerminal && arcs.size() == 1 && arcs.front().second == kFalseTerminal;
        node.var = node.is_literal ? arcs.front().first : variables_.new_var();
        node.arcs = std::move(arcs);
        const int id = static_cast<int>(nodes_.size());
        nodes_.push_back(std::move(node));
        unique_.emplace(hash, id);
        return id;
    }

    void emit_node(const Node& node, CnfFormula& cnf) const {
        if (node.is_literal) return;
        if (node.else_child >= 0) {
            cnf.add_clause({-nodes_[static_cast<std::size_t>(node.else_child)].var, node.var});
        } else if (node.else_child == kFalseTerminal) {
            cnf.add_clause({node.var});
        }
        for (const auto& [lit, child] : node.arcs) {
            if (child == kTrueTerminal) continue;
            if (child == kFalseTerminal) cnf.add_clause({-lit, node.var});
            else cnf.add_clause({-nodes_[static_cast<std::size_t>(child)].var, -lit, node.var});
        }
    }

    const std::vector<Group>& groups_;
    VariableManager& variables_;
    std::vector<SuffixMaximum> suffix_;
    std::vector<Node> nodes_;
    std::unordered_map<StateKey, int, StateKeyHash> states_;
    // Store each signature once in nodes_; this table retains only hash/ID pairs.
    std::unordered_multimap<std::size_t, int> unique_;
};

}  // namespace

EncodeResult MddEncoder::encode(const GroupedLeqConstraint& constraint,
                                const EncodeOptions& options) const {
    constraint.validate();
    const int top_id = constraint.effective_top_id(options.top_id);
    EncodeResult result(options.clause_memory);
    result.cnf.num_vars = top_id;
    VariableManager variables(top_id);
    add_amo_groups(constraint, result.cnf, variables);
    const auto prepared = detail::preprocess_leq(constraint, result.cnf);
    if (!prepared.redundant) {
        const auto groups = make_ordered_groups(prepared.constraint);
        Diagram(groups, variables).encode(prepared.constraint.bound, result.cnf);
    }
    result.cnf.num_vars = std::max(result.cnf.num_vars, variables.max_var());
    result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - top_id);
    result.stats.clauses = result.cnf.clauses.size();
    return result;
}

}  // namespace structuredpb
