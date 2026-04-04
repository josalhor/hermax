#include "structuredpb/rggt.hpp"

#include <algorithm>
#include <cstddef>
#include <limits>
#include <memory>
#include <optional>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

namespace structuredpb {
namespace {

struct TermRef {
    int lit = 0;
    Weight weight = 0;
};

struct Interval {
    Weight lo = 0;
    Weight hi = 0;
};

struct Node {
    bool leaf = false;
    std::vector<Weight> vals;
    std::vector<Interval> intervals;
    std::vector<TermRef> terms;
    Node* left = nullptr;
    Node* right = nullptr;
    bool is_root = false;
};

Weight clip_sum(Weight lhs, Weight rhs, Weight cap) {
    if (lhs >= cap || rhs >= cap) {
        return cap;
    }
    if (lhs > cap - rhs) {
        return cap;
    }
    return lhs + rhs;
}

void sort_unique(std::vector<Weight>& vals) {
    std::sort(vals.begin(), vals.end());
    vals.erase(std::unique(vals.begin(), vals.end()), vals.end());
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

std::vector<Weight> combine_vals(const std::vector<Weight>& left, const std::vector<Weight>& right, Weight cap) {
    std::vector<Weight> out;
    out.reserve(left.size() * right.size());
    for (Weight l : left) {
        for (Weight r : right) {
            out.push_back(clip_sum(l, r, cap));
        }
    }
    sort_unique(out);
    return out;
}

std::vector<std::vector<TermRef>> build_mutable_groups(const GroupedLeqConstraint& constraint) {
    std::unordered_map<int, Weight> weight_by_lit;
    weight_by_lit.reserve(constraint.terms.size());
    for (const auto& term : constraint.terms) {
        weight_by_lit.emplace(term.lit, term.weight);
    }
    std::vector<std::vector<TermRef>> groups;
    groups.reserve(constraint.groups.size());
    for (const auto& group : constraint.groups) {
        std::vector<TermRef> terms;
        terms.reserve(group.size());
        for (int lit : group) {
            terms.push_back(TermRef{lit, weight_by_lit.at(lit)});
        }
        groups.push_back(std::move(terms));
    }
    return groups;
}

std::vector<Weight> leaf_vals(const std::vector<TermRef>& terms, Weight cap) {
    std::vector<Weight> vals;
    vals.reserve(terms.size() + 1);
    vals.push_back(0);
    for (const auto& term : terms) {
        vals.push_back(std::min(term.weight, cap));
    }
    sort_unique(vals);
    return vals;
}

Node* build_leaf(std::vector<std::unique_ptr<Node>>& storage, const std::vector<TermRef>& terms, Weight cap) {
    auto node = std::make_unique<Node>();
    node->leaf = true;
    node->terms = terms;
    node->vals = leaf_vals(terms, cap);
    storage.push_back(std::move(node));
    return storage.back().get();
}

Node* merge_nodes(std::vector<std::unique_ptr<Node>>& storage, Node* left, Node* right, Weight cap) {
    auto node = std::make_unique<Node>();
    node->left = left;
    node->right = right;
    node->vals = combine_vals(left->vals, right->vals, cap);
    storage.push_back(std::move(node));
    return storage.back().get();
}

Node* build_min_ratio_tree(std::vector<std::vector<TermRef>> const& groups,
                           std::vector<std::unique_ptr<Node>>& storage,
                           Weight cap) {
    std::vector<Node*> active;
    active.reserve(groups.size());
    for (const auto& group : groups) {
        active.push_back(build_leaf(storage, group, cap));
    }
    if (active.empty()) {
        return nullptr;
    }
    while (active.size() > 1) {
        std::size_t best_i = 0;
        std::size_t best_j = 1;
        std::size_t best_size = std::numeric_limits<std::size_t>::max();
        std::size_t best_prod = 1;
        for (std::size_t i = 0; i < active.size(); ++i) {
            for (std::size_t j = i + 1; j < active.size(); ++j) {
                const auto vals = combine_vals(active[i]->vals, active[j]->vals, cap);
                const std::size_t size = vals.size();
                const std::size_t prod = active[i]->vals.size() * active[j]->vals.size();
                const std::size_t lhs = size * best_prod;
                const std::size_t rhs = best_size * prod;
                if (best_size == std::numeric_limits<std::size_t>::max() || lhs < rhs ||
                    (lhs == rhs && size < best_size)) {
                    best_i = i;
                    best_j = j;
                    best_size = size;
                    best_prod = prod;
                }
            }
        }
        if (best_j < best_i) {
            std::swap(best_i, best_j);
        }
        Node* left = active[best_i];
        Node* right = active[best_j];
        Node* parent = merge_nodes(storage, left, right, cap);
        active.erase(active.begin() + static_cast<std::ptrdiff_t>(best_j));
        active.erase(active.begin() + static_cast<std::ptrdiff_t>(best_i));
        active.push_back(parent);
    }
    active.front()->is_root = true;
    return active.front();
}

std::size_t interval_index(const std::vector<Interval>& intervals, Weight value) {
    for (std::size_t i = 0; i < intervals.size(); ++i) {
        if (intervals[i].lo <= value && value <= intervals[i].hi) {
            return i;
        }
    }
    throw std::logic_error("structuredpb: interval lookup failed");
}

void merge_adjacent_child_intervals(const Node* parent, Node* child, const Node* sibling, Weight cap) {
    child->intervals.clear();
    for (Weight value : child->vals) {
        child->intervals.push_back(Interval{value, value});
    }
    bool changed = true;
    while (changed && child->intervals.size() > 1) {
        changed = false;
        for (std::size_t idx = 0; idx + 1 < child->intervals.size(); ++idx) {
            const Interval first = child->intervals[idx];
            const Interval second = child->intervals[idx + 1];
            bool can_merge = true;
            for (Weight other : sibling->vals) {
                const Weight sum_first = clip_sum(first.hi, other, cap);
                const Weight sum_second = clip_sum(second.lo, other, cap);
                if (interval_index(parent->intervals, sum_first) != interval_index(parent->intervals, sum_second)) {
                    can_merge = false;
                    break;
                }
            }
            if (!can_merge) {
                continue;
            }
            child->intervals[idx] = Interval{first.lo, second.hi};
            child->intervals.erase(child->intervals.begin() + static_cast<std::ptrdiff_t>(idx + 1));
            changed = true;
            break;
        }
    }
}

void make_child_intervals(Node* node, Weight cap) {
    if (node == nullptr || node->leaf) {
        return;
    }
    merge_adjacent_child_intervals(node, node->left, node->right, cap);
    merge_adjacent_child_intervals(node, node->right, node->left, cap);
    make_child_intervals(node->left, cap);
    make_child_intervals(node->right, cap);
}

void initialize_root_intervals(Node* root, Weight cap) {
    root->intervals.clear();
    if (root == nullptr) {
        return;
    }
    Weight max_non_overflow = 0;
    for (Weight value : root->vals) {
        if (value < cap) {
            max_non_overflow = std::max(max_non_overflow, value);
        }
    }
    root->intervals.push_back(Interval{0, max_non_overflow});
    if (std::find(root->vals.begin(), root->vals.end(), cap) != root->vals.end()) {
        root->intervals.push_back(Interval{cap, cap});
    }
}

bool reduce_leaf_terms(std::vector<std::vector<TermRef>>& groups,
                       const std::vector<std::unique_ptr<Node>>& storage,
                       Weight cap) {
    bool changed = false;
    std::size_t group_index = 0;
    for (const auto& node_ptr : storage) {
        const Node& node = *node_ptr;
        if (!node.leaf) {
            continue;
        }
        auto& group = groups[group_index++];
        for (const auto& interval : node.intervals) {
            if (interval.lo >= interval.hi) {
                continue;
            }
            for (auto& term : group) {
                const Weight clipped = std::min(term.weight, cap);
                if (interval.lo < clipped && clipped <= interval.hi) {
                    term.weight = interval.lo;
                    changed = true;
                }
            }
        }
        group.erase(std::remove_if(group.begin(),
                                   group.end(),
                                   [](const TermRef& term) { return term.weight == 0; }),
                    group.end());
    }
    groups.erase(std::remove_if(groups.begin(),
                                groups.end(),
                                [](const std::vector<TermRef>& group) { return group.empty(); }),
                 groups.end());
    return changed;
}

struct BuiltTree {
    std::vector<std::vector<TermRef>> groups;
    std::vector<std::unique_ptr<Node>> storage;
    Node* root = nullptr;
};

BuiltTree build_reduced_tree(const GroupedLeqConstraint& constraint, Weight cap) {
    BuiltTree built;
    built.groups = build_mutable_groups(constraint);
    bool changed = false;
    do {
        changed = false;
        built.storage.clear();
        built.root = build_min_ratio_tree(built.groups, built.storage, cap);
        if (built.root == nullptr) {
            return built;
        }
        initialize_root_intervals(built.root, cap);
        make_child_intervals(built.root, cap);
        changed = reduce_leaf_terms(built.groups, built.storage, cap);
    } while (changed);
    built.storage.clear();
    built.root = build_min_ratio_tree(built.groups, built.storage, cap);
    if (built.root != nullptr) {
        initialize_root_intervals(built.root, cap);
        make_child_intervals(built.root, cap);
    }
    return built;
}

struct EncodedNodeInfo {
    std::vector<int> interval_vars;
};

int parent_interval_var(const Node* node,
                        std::size_t idx,
                        Weight cap,
                        const std::unordered_map<const Node*, EncodedNodeInfo>& info) {
    if (node->is_root) {
        const auto& interval = node->intervals[idx];
        if (interval.lo == cap) {
            const auto& vars = info.at(node).interval_vars;
            return vars[idx];
        }
        return 0;
    }
    return info.at(node).interval_vars[idx];
}

void encode_internal(Node* node,
                     Weight cap,
                     VariableManager& vm,
                     CnfFormula& cnf,
                     std::unordered_map<const Node*, EncodedNodeInfo>& info) {
    if (node == nullptr) {
        return;
    }
    if (node->leaf) {
        EncodedNodeInfo leaf_info;
        leaf_info.interval_vars.resize(node->intervals.size(), 0);
        for (std::size_t idx = 0; idx < node->intervals.size(); ++idx) {
            const Interval interval = node->intervals[idx];
            if (interval.lo == 0) {
                continue;
            }
            std::vector<int> linked;
            for (const auto& term : node->terms) {
                if (std::min(term.weight, cap) == interval.lo) {
                    linked.push_back(term.lit);
                }
            }
            if (linked.empty()) {
                throw std::logic_error("structuredpb: missing linked term for leaf interval");
            }
            if (linked.size() == 1) {
                leaf_info.interval_vars[idx] = linked.front();
            } else {
                const int aux = vm.new_var();
                leaf_info.interval_vars[idx] = aux;
                for (int lit : linked) {
                    cnf.add_clause({-lit, aux});
                }
            }
        }
        info.emplace(node, std::move(leaf_info));
        return;
    }

    encode_internal(node->left, cap, vm, cnf, info);
    encode_internal(node->right, cap, vm, cnf, info);

    EncodedNodeInfo node_info;
    node_info.interval_vars.resize(node->intervals.size(), 0);
    for (std::size_t idx = 0; idx < node->intervals.size(); ++idx) {
        const Interval interval = node->intervals[idx];
        if (interval.lo == 0) {
            continue;
        }
        if (node->is_root && interval.lo < cap) {
            continue;
        }
        node_info.interval_vars[idx] = vm.new_var();
    }
    info.emplace(node, std::move(node_info));

    const auto add_pass_clause = [&](const Node* child) {
        const auto& child_info = info.at(child).interval_vars;
        for (std::size_t child_idx = 0; child_idx < child->intervals.size(); ++child_idx) {
            const Interval child_interval = child->intervals[child_idx];
            const int child_var = child_info[child_idx];
            if (child_var == 0) {
                continue;
            }
            for (std::size_t parent_idx = 0; parent_idx < node->intervals.size(); ++parent_idx) {
                const Interval parent_interval = node->intervals[parent_idx];
                if (parent_interval.lo <= child_interval.lo && child_interval.hi <= parent_interval.hi) {
                    const int parent_var = parent_interval_var(node, parent_idx, cap, info);
                    if (parent_var != 0) {
                        cnf.add_clause({-child_var, parent_var});
                    }
                    break;
                }
            }
        }
    };
    add_pass_clause(node->left);
    add_pass_clause(node->right);

    const auto& left_vars = info.at(node->left).interval_vars;
    const auto& right_vars = info.at(node->right).interval_vars;
    for (std::size_t li = 0; li < node->left->intervals.size(); ++li) {
        const int lvar = left_vars[li];
        if (lvar == 0) {
            continue;
        }
        const Interval lint = node->left->intervals[li];
        for (std::size_t ri = 0; ri < node->right->intervals.size(); ++ri) {
            const int rvar = right_vars[ri];
            if (rvar == 0) {
                continue;
            }
            const Interval rint = node->right->intervals[ri];
            const Weight sum_lo = clip_sum(lint.lo, rint.lo, cap);
            const Weight sum_hi = clip_sum(lint.hi, rint.hi, cap);
            for (std::size_t parent_idx = 0; parent_idx < node->intervals.size(); ++parent_idx) {
                const Interval parent_interval = node->intervals[parent_idx];
                if (parent_interval.lo <= sum_lo && sum_hi <= parent_interval.hi) {
                    const int parent_var = parent_interval_var(node, parent_idx, cap, info);
                    if (parent_var != 0) {
                        cnf.add_clause({-lvar, -rvar, parent_var});
                    }
                    break;
                }
            }
        }
    }
}

}  // namespace

EncodeResult RggtEncoder::encode(const GroupedLeqConstraint& constraint,
                                 const EncodeOptions& options) const {
    constraint.validate();

    EncodeResult result;
    VariableManager vm(options.top_id);
    result.cnf.num_vars = options.top_id;
    add_pairwise_amo(constraint, result.cnf);

    const Weight cap = constraint.bound + 1;
    const auto built = build_reduced_tree(constraint, cap);
    if (built.root == nullptr || built.groups.empty()) {
        result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
        result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - options.top_id);
        result.stats.clauses = result.cnf.clauses.size();
        return result;
    }

    if (built.root->leaf) {
        for (const auto& term : built.root->terms) {
            if (term.weight > constraint.bound) {
                result.cnf.add_clause({-term.lit});
            }
        }
        result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
        result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - options.top_id);
        result.stats.clauses = result.cnf.clauses.size();
        return result;
    }

    std::unordered_map<const Node*, EncodedNodeInfo> info;
    info.reserve(built.storage.size());
    encode_internal(built.root, cap, vm, result.cnf, info);

    const auto root_it = info.find(built.root);
    if (root_it != info.end()) {
        for (std::size_t idx = 0; idx < built.root->intervals.size(); ++idx) {
            if (built.root->intervals[idx].lo == cap) {
                const int overflow = root_it->second.interval_vars[idx];
                if (overflow != 0) {
                    result.cnf.add_clause({-overflow});
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
