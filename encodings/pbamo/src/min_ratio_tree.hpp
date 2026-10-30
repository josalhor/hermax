#ifndef STRUCTUREDPB_MIN_RATIO_TREE_HPP
#define STRUCTUREDPB_MIN_RATIO_TREE_HPP

#include <cstddef>
#include <limits>
#include <map>
#include <queue>
#include <type_traits>
#include <utility>
#include <vector>

namespace structuredpb::detail {

// Scores depend only on immutable value sets; encoding nodes remain distinct.
template<class Node, class Score, class Merge>
Node* merge_min_ratio_tree(std::vector<Node*> nodes, Score score, Merge merge) {
    if (nodes.empty()) return nullptr;
    using Values = std::decay_t<decltype(nodes.front()->vals)>;
    struct ValuesLess {
        bool operator()(const Values* a, const Values* b) const { return *a < *b; }
    };
    struct Domain {
        std::vector<std::size_t> members;
        std::size_t head = 0;
    };
    struct Entry {
        std::size_t size, product, left, right;
    };
    struct Worse {
        bool operator()(const Entry& a, const Entry& b) const {
            const auto x = a.size * b.product, y = b.size * a.product;
            if (x != y) return x > y;
            if (a.size != b.size) return a.size > b.size;
            if (a.left != b.left) return a.left > b.left;
            return a.right > b.right;
        }
    };
    // Nodes outlive this planner, so intern value sets without copying vectors.
    std::map<const Values*, std::size_t, ValuesLess> index;
    std::vector<Domain> domains;
    std::vector<std::size_t> node_domain;
    auto register_node = [&](std::size_t node) {
        auto found = index.try_emplace(&nodes[node]->vals, domains.size());
        const auto id = found.first->second;
        if (found.second) domains.push_back({});
        domains[id].members.push_back(node);
        node_domain.push_back(id);
        return id;
    };
    for (std::size_t i = 0; i < nodes.size(); ++i) register_node(i);
    auto count = [&](std::size_t id) { return domains[id].members.size() - domains[id].head; };
    const auto missing = std::numeric_limits<std::size_t>::max();
    auto representative = [&](std::size_t a, std::size_t b) {
        if (!count(a) || !count(b) || (a == b && count(a) < 2)) {
            return std::make_pair(missing, missing);
        }
        auto left = domains[a].members[domains[a].head];
        auto right = domains[b].members[domains[b].head + (a == b)];
        if (right < left) std::swap(left, right);
        return std::make_pair(left, right);
    };
    auto candidate = [&](std::size_t a, std::size_t b) {
        const auto pair = representative(a, b);
        return Entry{score(nodes[pair.first], nodes[pair.second]),
                     nodes[pair.first]->vals.size() * nodes[pair.second]->vals.size(), pair.first, pair.second};
    };
    std::vector<Entry> initial;
    initial.reserve((domains.size() - 1) * (domains.size() - 1));
    for (std::size_t a = 0; a < domains.size(); ++a) {
        for (std::size_t b = a; b < domains.size(); ++b) {
            if (representative(a, b).first != missing) initial.push_back(candidate(a, b));
        }
    }
    std::priority_queue<Entry, std::vector<Entry>, Worse> pending(Worse{}, std::move(initial));
    std::size_t remaining = nodes.size();
    while (remaining > 1) {
        auto best = pending.top();
        pending.pop();
        const auto a = node_domain[best.left], b = node_domain[best.right];
        const auto pair = representative(a, b);
        if (pair.first == missing) continue;
        if (pair.first != best.left || pair.second != best.right) {
            // Retiring members can only move this pair later in the tie order.
            best.left = pair.first;
            best.right = pair.second;
            pending.push(best);
            continue;
        }
        ++domains[a].head;
        ++domains[b].head;
        auto parent = merge(nodes[best.left], nodes[best.right]);
        nodes.push_back(parent);
        const auto id = register_node(nodes.size() - 1);
        const auto previous_count = count(id) - 1;
        const auto next = representative(a, b);
        if (next.first != missing) pending.push({best.size, best.product, next.first, next.second});
        auto same_pair = [&](std::size_t x, std::size_t y) {
            return (x == a && y == b) || (x == b && y == a);
        };
        // A new first member enables cross-domain pairs; a second enables self-pairs.
        if (previous_count == 0) {
            for (std::size_t other = 0; other < domains.size(); ++other) {
                if (count(other) && other != id && !same_pair(id, other)) {
                    pending.push(candidate(id, other));
                }
            }
        } else if (previous_count == 1 && !same_pair(id, id)) {
            pending.push(candidate(id, id));
        }
        --remaining;
    }
    return nodes.back();
}
}  // namespace structuredpb::detail

#endif
