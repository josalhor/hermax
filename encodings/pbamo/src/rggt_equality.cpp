#include "structuredpb/rggt_equality.hpp"

#include "min_ratio_tree.hpp"

#include <algorithm>
#include <functional>
#include <memory>
#include <queue>
#include <unordered_map>
#include <utility>
#include <vector>

namespace structuredpb {
namespace {

struct Signal {
    int lit = 0;
    bool value = false;

    static Signal constant(bool value) { return {0, value}; }
    static Signal literal(int lit) { return {lit, false}; }
    Signal operator!() const { return lit ? literal(-lit) : constant(!value); }
    bool operator==(Signal other) const { return lit == other.lit && value == other.value; }
};

void add_clause(CnfFormula& cnf, std::initializer_list<Signal> signals) {
    Clause clause;
    for (Signal signal : signals) {
        if (!signal.lit) {
            if (signal.value) return;
            continue;
        }
        if (std::find(clause.begin(), clause.end(), -signal.lit) != clause.end()) return;
        if (std::find(clause.begin(), clause.end(), signal.lit) == clause.end()) {
            clause.push_back(signal.lit);
        }
    }
    cnf.add_clause(std::move(clause));
}

struct Node {
    std::vector<Weight> vals;
    std::vector<WeightedLiteral> terms;
    std::vector<Signal> thresholds;
    Node* left = nullptr;
    Node* right = nullptr;
};

struct SumEntry {
    Weight sum;
    std::size_t left;
    std::size_t right;
    bool operator>(const SumEntry& other) const { return sum > other.sum; }
};

std::vector<Weight> reachable_sums(const Node* left, const Node* right, Weight bound) {
    // Merge sorted rows instead of retaining the entire Cartesian product.
    // Values exceeding the target cannot occur in any nonnegative equality.
    std::priority_queue<SumEntry, std::vector<SumEntry>, std::greater<SumEntry>> pending;
    for (std::size_t i = 0; i < left->vals.size(); ++i) {
        const Weight a = left->vals[i];
        if (a <= bound && right->vals.front() <= bound - a) {
            pending.push({a + right->vals.front(), i, 0});
        }
    }
    std::vector<Weight> values;
    while (!pending.empty()) {
        const auto entry = pending.top();
        pending.pop();
        if (values.empty() || values.back() != entry.sum) values.push_back(entry.sum);
        const auto next = entry.right + 1;
        const Weight a = left->vals[entry.left];
        if (next < right->vals.size() && right->vals[next] <= bound - a) {
            pending.push({a + right->vals[next], entry.left, next});
        }
    }
    return values;
}

struct SumTree {
    std::vector<std::unique_ptr<Node>> nodes;
    Node* root = nullptr;
};

SumTree build_tree(const GroupedLeqConstraint& sum) {
    std::unordered_map<int, Weight> weights;
    for (const auto& term : sum.terms) weights.emplace(term.lit, term.weight);
    SumTree tree;
    std::vector<Node*> leaves;
    for (const auto& group : sum.groups) {
        auto node = std::make_unique<Node>();
        node->vals.push_back(0);
        for (int lit : group) {
            const Weight weight = weights.at(lit);
            node->terms.push_back({lit, weight});
            if (weight <= sum.bound) node->vals.push_back(weight);
        }
        std::sort(node->vals.begin(), node->vals.end());
        node->vals.erase(std::unique(node->vals.begin(), node->vals.end()), node->vals.end());
        leaves.push_back(node.get());
        tree.nodes.push_back(std::move(node));
    }
    tree.root = detail::merge_min_ratio_tree(
        std::move(leaves),
        [&](const Node* left, const Node* right) { return reachable_sums(left, right, sum.bound).size(); },
        [&](Node* left, Node* right) {
            auto parent = std::make_unique<Node>();
            parent->left = left;
            parent->right = right;
            parent->vals = reachable_sums(left, right, sum.bound);
            Node* result = parent.get();
            tree.nodes.push_back(std::move(parent));
            return result;
        });
    return tree;
}

void restrict_to_support(Node* node) {
    if (!node->left) return;
    auto& left = node->left->vals;
    auto& right = node->right->vals;
    std::vector<bool> keep_left(left.size(), false), keep_right(right.size(), false);
    const Weight maximum = node->vals.back();
    for (std::size_t i = 0; i < left.size(); ++i) {
        if (left[i] > maximum) continue;
        for (std::size_t j = 0; j < right.size() && right[j] <= maximum - left[i]; ++j) {
            if (std::binary_search(node->vals.begin(), node->vals.end(), left[i] + right[j])) {
                keep_left[i] = keep_right[j] = true;
            }
        }
    }
    const auto retain = [](std::vector<Weight>& values, const std::vector<bool>& keep) {
        std::size_t out = 0;
        for (std::size_t i = 0; i < values.size(); ++i) {
            if (keep[i]) values[out++] = values[i];
        }
        values.resize(out);
    };
    retain(left, keep_left);
    retain(right, keep_right);
    restrict_to_support(node->left);
    restrict_to_support(node->right);
}

Signal at_least(const Node& node, Weight value) {
    const auto it = std::lower_bound(node.vals.begin(), node.vals.end(), value);
    if (it == node.vals.end()) return Signal::constant(false);
    return node.thresholds[static_cast<std::size_t>(it - node.vals.begin())];
}

Signal at_most(const Node& node, Weight value) {
    const auto it = std::upper_bound(node.vals.begin(), node.vals.end(), value);
    if (it == node.vals.end()) return Signal::constant(true);
    return !node.thresholds[static_cast<std::size_t>(it - node.vals.begin())];
}

void encode_leaf(Node& node, VariableManager& vm, CnfFormula& cnf) {
    Clause allowed;
    for (const auto& term : node.terms) {
        if (!std::binary_search(node.vals.begin(), node.vals.end(), term.weight)) {
            cnf.add_clause({-term.lit});
        } else {
            allowed.push_back(term.lit);
        }
    }
    if (node.vals.front() != 0) cnf.add_clause(allowed);
    for (std::size_t i = 1; i < node.vals.size(); ++i) {
        Clause sources;
        for (const auto& term : node.terms) {
            if (term.weight >= node.vals[i] &&
                std::binary_search(node.vals.begin(), node.vals.end(), term.weight)) {
                sources.push_back(term.lit);
            }
        }
        if (sources.size() == 1) {
            node.thresholds[i] = Signal::literal(sources.front());
        } else {
            const int output = vm.new_var();
            node.thresholds[i] = Signal::literal(output);
            for (int lit : sources) cnf.add_clause({-lit, output});
            sources.push_back(-output);
            cnf.add_clause(std::move(sources));
        }
    }
}

void encode_fixed_sum(const Node& node, CnfFormula& cnf) {
    const auto& left = *node.left;
    const auto& right = *node.right;
    const Weight total = node.vals.front();
    // Support filtering makes the child domains complementary around total.
    // Every threshold on the left is equivalent to one upper bound on the right.
    for (std::size_t i = 1; i < left.vals.size(); ++i) {
        const Signal a = left.thresholds[i];
        const Signal b = at_most(right, total - left.vals[i]);
        add_clause(cnf, {!a, b});
        add_clause(cnf, {a, !b});
    }
}

void encode_addition(const Node& node, CnfFormula& cnf) {
    const auto& left = *node.left;
    const auto& right = *node.right;
    const Weight maximum = node.vals.back();
    for (std::size_t i = 0; i < left.vals.size(); ++i) {
        Signal previous;
        bool have_previous = false;
        for (std::size_t j = 0; j < right.vals.size(); ++j) {
            const bool fits = left.vals[i] <= maximum && right.vals[j] <= maximum - left.vals[i];
            const Signal consequence = fits ? at_least(node, left.vals[i] + right.vals[j]) : Signal::constant(false);
            if (!have_previous || !(consequence == previous)) {
                add_clause(cnf, {!left.thresholds[i], !right.thresholds[j], consequence});
            }
            previous = consequence;
            have_previous = true;
        }
        have_previous = false;
        for (std::size_t j = right.vals.size(); j-- > 0;) {
            const bool fits = left.vals[i] <= maximum && right.vals[j] <= maximum - left.vals[i];
            const Signal consequence = fits ? at_most(node, left.vals[i] + right.vals[j]) : Signal::constant(true);
            if (!have_previous || !(consequence == previous)) {
                const Signal a = i + 1 < left.vals.size() ? !left.thresholds[i + 1] : Signal::constant(true);
                const Signal b = j + 1 < right.vals.size() ? !right.thresholds[j + 1] : Signal::constant(true);
                add_clause(cnf, {!a, !b, consequence});
            }
            previous = consequence;
            have_previous = true;
        }
    }
}

void encode_tree(Node& node, VariableManager& vm, CnfFormula& cnf) {
    node.thresholds.assign(node.vals.size(), Signal::constant(true));
    if (!node.left) {
        encode_leaf(node, vm, cnf);
    } else {
        encode_tree(*node.left, vm, cnf);
        encode_tree(*node.right, vm, cnf);
        for (std::size_t i = 1; i < node.vals.size(); ++i) {
            node.thresholds[i] = Signal::literal(vm.new_var());
        }
        if (node.vals.size() == 1) encode_fixed_sum(node, cnf);
        else encode_addition(node, cnf);
    }
    for (std::size_t i = 2; i < node.thresholds.size(); ++i) {
        add_clause(cnf, {!node.thresholds[i], node.thresholds[i - 1]});
    }
}

}  // namespace

EncodeResult encode_rggt_equality(const GroupedLeqConstraint& sum, const EncodeOptions& options) {
    sum.validate();
    EncodeResult result(options.clause_memory);
    result.cnf.num_vars = options.top_id;
    VariableManager vm(options.top_id);
    if (sum.emit_amo) {
        for (const auto& group : sum.groups) {
            for (std::size_t i = 0; i < group.size(); ++i) {
                for (std::size_t j = i + 1; j < group.size(); ++j) {
                    result.cnf.add_clause({-group[i], -group[j]});
                }
            }
        }
    }
    auto tree = build_tree(sum);
    if (!tree.root) {
        if (sum.bound != 0) result.cnf.add_clause({});
    } else if (!std::binary_search(tree.root->vals.begin(), tree.root->vals.end(), sum.bound)) {
        result.cnf.add_clause({});
    } else {
        tree.root->vals = {sum.bound};
        restrict_to_support(tree.root);
        encode_tree(*tree.root, vm, result.cnf);
    }
    result.cnf.num_vars = std::max(result.cnf.num_vars, vm.max_var());
    result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - options.top_id);
    result.stats.clauses = result.cnf.clauses.size();
    return result;
}

}  // namespace structuredpb
