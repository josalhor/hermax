#ifndef STRUCTUREDPB_MIN_RATIO_TREE_HPP
#define STRUCTUREDPB_MIN_RATIO_TREE_HPP

#include <cstddef>
#include <limits>
#include <unordered_map>
#include <utility>
#include <vector>

namespace structuredpb::detail {

// Node values remain immutable during a build. The callbacks compute a
// candidate domain's size and construct only the selected parent.
template<class Node, class Score, class Merge>
Node* merge_min_ratio_tree(std::vector<Node*> active, Score score, Merge merge) {
    if (active.empty()) {
        return nullptr;
    }
    // Values are immutable during this tree build. Keep only each pair's
    // score, not its potentially large vector of attainable sums.
    std::unordered_map<const Node*, std::unordered_map<const Node*, std::size_t>> merge_sizes;
    while (active.size() > 1) {
        std::size_t best_i = 0;
        std::size_t best_j = 1;
        std::size_t best_size = std::numeric_limits<std::size_t>::max();
        std::size_t best_prod = 1;
        for (std::size_t i = 0; i < active.size(); ++i) {
            auto& sizes = merge_sizes[active[i]];
            for (std::size_t j = i + 1; j < active.size(); ++j) {
                auto found = sizes.find(active[j]);
                if (found == sizes.end()) {
                    found = sizes.emplace(active[j], score(active[i], active[j])).first;
                }
                const std::size_t size = found->second;
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
        Node* parent = merge(left, right);
        active.erase(active.begin() + static_cast<std::ptrdiff_t>(best_j));
        active.erase(active.begin() + static_cast<std::ptrdiff_t>(best_i));
        active.push_back(parent);
    }
    return active.front();
}

}  // namespace structuredpb::detail

#endif
