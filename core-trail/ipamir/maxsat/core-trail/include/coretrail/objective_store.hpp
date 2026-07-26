#pragma once

#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

namespace coretrail {

// Canonical user objective. Derived RC2 selectors never enter this store.
class ObjectiveStore {
public:
    void add_unit(int literal, long weight) {
        if (weight <= 0) throw std::invalid_argument("soft weight must be positive");
        auto [it, inserted] = terms_.try_emplace(literal, Term{{literal}, 0});
        if (!inserted && it->second.clause.size() != 1U) {
            throw std::logic_error("unit selector collides with a non-unit soft term");
        }
        it->second.weight += weight;
    }

    void add_clause(int selector, std::vector<int> clause, long weight) {
        if (weight <= 0) throw std::invalid_argument("soft weight must be positive");
        if (!terms_.emplace(selector, Term{std::move(clause), weight}).second) {
            throw std::invalid_argument("selector already exists");
        }
    }

    void set_unit(int literal, long weight) {
        if (weight < 0) throw std::invalid_argument("soft weight must be non-negative");
        auto [it, inserted] = terms_.try_emplace(literal, Term{{literal}, 0});
        if (!inserted && it->second.clause.size() != 1U) {
            throw std::logic_error("unit selector collides with a non-unit soft term");
        }
        it->second.weight = weight;
    }

    long unit_weight(int literal) const {
        const auto it = terms_.find(literal);
        return it == terms_.end() ? 0 : it->second.weight;
    }

    long evaluate(const std::vector<int>& model) const {
        std::unordered_map<int, bool> values;
        values.reserve(model.size());
        for (int lit : model) values[lit < 0 ? -lit : lit] = lit > 0;

        long cost = 0;
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

    void clear() noexcept { terms_.clear(); }

private:
    struct Term {
        std::vector<int> clause;
        long weight;
    };

    std::unordered_map<int, Term> terms_{};
};

}  // namespace coretrail
