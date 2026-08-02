#ifndef DAG_HH_
#define DAG_HH_

#include <algorithm>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "clset.hh"
#include "itot.hh"

namespace rc2 {

// Kept only for source compatibility with rc2_solver.cc.
// This replacement ignores overlap policy entirely.
enum DagOverlapPolicy {
    DAG_OVERLAP_NONE = 0,
    DAG_OVERLAP_EXPLOIT = 1
};

class ItotDag {
public:
    struct BuildResult {
        TotTree* root{nullptr};
        std::vector<int> rels_used;
        bool amk_cache_hit{false};
    };

    BuildResult build_counter(
        const std::vector<int>& rels,
        unsigned rhs,
        int overlap_policy,
        int& top,
        const std::vector<std::vector<int>>& hard_clauses,
        ClauseSet& delta
    ) {
        (void)overlap_policy;
        (void)hard_clauses;

        std::vector<int> inputs = canonicalize_rels(rels);
        if (inputs.empty()) {
            throw std::runtime_error("ItotDag::build_counter: empty input set");
        }

        const std::string key = lits_key(inputs);

        auto it = exact_cache_.find(key);
        if (it != exact_cache_.end()) {
            TotTree* root = it->second;
            if (root == nullptr) {
                throw std::runtime_error("ItotDag::build_counter: cached null root");
            }

            ClauseSet inc;
            itot_increase(root, inc, rhs, top);
            append_delta(delta, inc);

            validate_counter(root, inputs.size(), rhs, "cached");
            return {root, std::move(inputs), true};
        }

        TotTree* root = build_tree(inputs, rhs, top, delta);
        validate_counter(root, inputs.size(), rhs, "new");

        exact_cache_.emplace(key, root);
        return {root, std::move(inputs), false};
    }

    std::unordered_set<int> expand_rel(int lit) const {
        return {lit};
    }

    void add_mutex_pair(int a, int b) {
        (void)a;
        (void)b;
    }

    void add_mutex_clique(const std::vector<int>& clique) {
        (void)clique;
    }

    void clear() {
        exact_cache_.clear();
        owned_.clear();
    }

private:
    static void append_delta(ClauseSet& dst, ClauseSet& src) {
        for (const auto& cl : src.get_clauses()) {
            dst.add_clause(cl);
        }
    }

    static std::string lits_key(const std::vector<int>& lits) {
        std::ostringstream oss;
        for (size_t i = 0; i < lits.size(); ++i) {
            if (i) oss << ',';
            oss << lits[i];
        }
        return oss.str();
    }

    static std::vector<int> canonicalize_rels(const std::vector<int>& rels) {
        std::vector<int> out = rels;
        std::sort(out.begin(), out.end());

        auto dup = std::adjacent_find(out.begin(), out.end());
        if (dup != out.end()) {
            std::ostringstream oss;
            oss << "ItotDag::build_counter: duplicate input literal " << *dup;
            throw std::runtime_error(oss.str());
        }

        for (int l : out) {
            if (l == 0) {
                throw std::runtime_error("ItotDag::build_counter: literal 0 in input set");
            }
        }

        return out;
    }

    TotTree* make_node() {
        owned_.push_back(std::make_unique<TotTree>());
        return owned_.back().get();
    }

    TotTree* make_leaf(int lit) {
        TotTree* t = make_node();
        t->vars = {lit};
        t->nof_input = 1;
        t->left = nullptr;
        t->right = nullptr;
        return t;
    }

    TotTree* make_internal(
        TotTree* left,
        TotTree* right,
        unsigned rhs,
        int& top,
        ClauseSet& delta
    ) {
        if (left == nullptr || right == nullptr) {
            throw std::runtime_error("ItotDag::make_internal: null child");
        }

        TotTree* t = make_node();
        t->left = left;
        t->right = right;
        t->nof_input = left->nof_input + right->nof_input;

        const unsigned out_count = std::min(rhs + 1, t->nof_input);
        if (out_count == 0) {
            throw std::runtime_error("ItotDag::make_internal: zero output count");
        }

        t->vars.resize(out_count);
        for (unsigned i = 0; i < out_count; ++i) {
            t->vars[i] = ++top;
        }

        itot_new_ua(
            top,
            delta,
            t->vars,
            out_count,
            left->vars,
            right->vars
        );

        return t;
    }

    TotTree* build_tree(
        const std::vector<int>& inputs,
        unsigned rhs,
        int& top,
        ClauseSet& delta
    ) {
        std::vector<TotTree*> layer;
        layer.reserve(inputs.size());

        for (int lit : inputs) {
            layer.push_back(make_leaf(lit));
        }

        while (layer.size() > 1U) {
            std::vector<TotTree*> next;
            next.reserve((layer.size() + 1U) / 2U);

            for (size_t i = 0; i < layer.size(); i += 2U) {
                if (i + 1U == layer.size()) {
                    next.push_back(layer[i]);
                } else {
                    next.push_back(make_internal(layer[i], layer[i + 1U], rhs, top, delta));
                }
            }

            layer.swap(next);
        }

        return layer.empty() ? nullptr : layer.front();
    }

    static void validate_counter(
        TotTree* root,
        size_t input_count,
        unsigned rhs,
        const char* origin
    ) {
        if (root == nullptr) {
            std::ostringstream oss;
            oss << "ItotDag::validate_counter: null root from " << origin;
            throw std::runtime_error(oss.str());
        }

        if (root->nof_input != input_count) {
            std::ostringstream oss;
            oss << "ItotDag::validate_counter: input count mismatch from "
                << origin
                << " root_nof_input=" << root->nof_input
                << " expected=" << input_count;
            throw std::runtime_error(oss.str());
        }

        if (input_count > rhs && root->vars.size() <= rhs) {
            std::ostringstream oss;
            oss << "ItotDag::validate_counter: counter too small from "
                << origin
                << " vars_size=" << root->vars.size()
                << " rhs=" << rhs
                << " input_count=" << input_count;
            throw std::runtime_error(oss.str());
        }
    }

private:
    std::vector<std::unique_ptr<TotTree>> owned_;
    std::unordered_map<std::string, TotTree*> exact_cache_;
};

}  // namespace rc2

#endif  // DAG_HH_