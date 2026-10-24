#pragma once

#include <algorithm>
#include <cstdint>
#include <functional>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <unordered_set>
#include <utility>
#include <vector>

#include "PBConfig.h"
#include "clausedatabase.h"
#include "pbconstraint.h"

namespace integer_sum {
class BudgetExceeded : public std::runtime_error {
public:
    explicit BudgetExceeded(const char* resource) : std::runtime_error(resource) {}
};

inline std::int64_t total_weight(const std::vector<std::int64_t>& weights) {
    std::int64_t total = 0;
    for (const auto w : weights) {
        if (w <= 0) throw std::invalid_argument("weights must be positive");
        if (w > std::numeric_limits<std::int64_t>::max() - total)
            throw std::overflow_error("sum of weights exceeds the native range");
        total += w;
    }
    return total;
}

inline std::int64_t count_states(std::vector<std::int64_t> weights,
                                std::int64_t bound, PBLib::Comparator comparator,
                                std::int64_t limit) {
    auto total = total_weight(weights);
    const bool equality = comparator == PBLib::BOTH;
    if (weights.empty() || bound < 0 || bound > total ||
        (!equality && (bound == 0 || bound == total))) return 0;
    if (comparator == PBLib::GEQ) bound = total - bound;
    std::int64_t divisor = 0;
    for (auto w : weights) divisor = std::gcd(divisor, w);
    if (equality && bound % divisor) return 0;
    bound /= divisor;
    for (auto& w : weights) w /= divisor;
    total /= divisor;
    while (true) {
        if (equality && bound > total / 2) bound = total - bound;
        weights.erase(std::remove_if(weights.begin(), weights.end(),
            [bound](auto w) { return w > bound; }), weights.end());
        total = total_weight(weights);
        if (bound == 0 || bound >= total) return 0;
        if (!equality || bound <= total / 2) break;
    }
    std::sort(weights.begin(), weights.end(), std::greater<std::int64_t>());
    std::unordered_set<std::int64_t> sums{0};
    std::int64_t count = 0, remaining = total;
    for (auto w : weights) {
        const auto lower = std::max<std::int64_t>(0, bound - remaining + !equality);
        std::unordered_set<std::int64_t> next;
        for (auto sum : sums) {
            if (sum < lower || sum > bound) continue;
            if (limit && count == limit) throw BudgetExceeded("states");
            ++count;
            next.insert(sum);
            if (w <= bound - sum) next.insert(sum + w);
        }
        if (next.empty()) break;
        sums = std::move(next);
        remaining -= w;
    }
    return count;
}

class ClauseSink final : public ClauseDatabase {
    std::int64_t limit_;
    void addClauseIntern(const std::vector<std::int32_t>& clause) override {
        if (limit_ && clauses.size() >= static_cast<std::size_t>(limit_))
            throw BudgetExceeded("clauses");
        clauses.push_back(clause);
    }
public:
    std::vector<std::vector<std::int32_t>> clauses;
    ClauseSink(PBConfig config, std::int64_t limit) : ClauseDatabase(config), limit_(limit) {}
};
}
