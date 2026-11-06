#pragma once

#include "coretrail/weight.hpp"
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

namespace coretrail {

// Canonical user objective. Derived RC2 selectors never enter this store.
class ObjectiveStore {
public:
    // Validate non-negative, finite weights and exact integer overflow.
    void validate_weight(int selector, Weight weight, bool replace) const {
        if (!weight.finite() || weight < 0) throw std::invalid_argument("soft weight must be finite and non-negative");
        Weight retained = total_weight_;
        if (replace) {
            const auto it = terms_.find(selector);
            if (it != terms_.end()) retained -= it->second.weight;
        }
        (void)(retained + weight); // check exact integer overflow; doubles remain finite-checked
    }

    void add_unit(int selector, int literal, Weight weight) {
        if (weight <= 0) throw std::invalid_argument("soft weight must be positive");
        validate_weight(selector, weight, false);
        auto [it, inserted] = terms_.try_emplace(selector, Term{{literal}, 0});
        if (!inserted && it->second.clause.size() != 1U) {
            throw std::logic_error("unit selector collides with a non-unit soft term");
        }
        it->second.weight += weight;
        total_weight_ += weight;
    }

    void add_clause(int selector, std::vector<int> clause, Weight weight) {
        if (weight <= 0) throw std::invalid_argument("soft weight must be positive");
        validate_weight(selector, weight, false);
        if (!terms_.emplace(selector, Term{std::move(clause), weight}).second) {
            throw std::invalid_argument("selector already exists");
        }
        total_weight_ += weight;
    }

    void set_unit(int selector, int literal, Weight weight) {
        if (weight < 0) throw std::invalid_argument("soft weight must be non-negative");
        validate_weight(selector, weight, true);
        auto [it, inserted] = terms_.try_emplace(selector, Term{{literal}, 0});
        if (!inserted && it->second.clause.size() != 1U) {
            throw std::logic_error("unit selector collides with a non-unit soft term");
        }
        total_weight_ -= it->second.weight;
        total_weight_ += weight;
        it->second.weight = weight;
    }

    Weight unit_weight(int literal) const {
        const auto it = terms_.find(literal);
        return it == terms_.end() ? Weight(0) : it->second.weight;
    }

    Weight evaluate(const std::vector<int>& model) const {
        std::unordered_map<int, bool> values;
        values.reserve(model.size());
        for (int lit : model) values[lit < 0 ? -lit : lit] = lit > 0;

        Weight cost = 0;
        for (const auto& [selector, term] : terms_) {
            (void)selector;
            if (term.weight == 0) continue;
            bool satisfied = false;
            for (int lit : term.clause) {
                const auto value = values.find(lit < 0 ? -lit : lit);
                if (value != values.end() && value->second == (lit > 0)) {
                    satisfied = true;
                    break;
                }
            }
            if (!satisfied) cost += term.weight;
        }
        return cost;
    }

    void clear() noexcept {
        terms_.clear();
        total_weight_ = 0;
    }

private:
    struct Term {
        std::vector<int> clause;
        Weight weight;
    };

    std::unordered_map<int, Term> terms_{};
    Weight total_weight_{0};
};

}  // namespace coretrail


