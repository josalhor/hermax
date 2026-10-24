#pragma once

// Modulo-totalizer arithmetic adapted from PySAT/BOLT (A. Ignatiev, 2017).

#include "cnf.hpp"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

namespace integer_sum {
using Chains = std::vector<std::vector<int>>;
struct Cost {
    std::uint64_t variables = 0, clauses = 0;
    std::size_t capacity = 0, quotient = 0, remainder = 0;
};
struct Node {
    std::vector<int> quotient, remainder;
    std::size_t capacity = 0;
};
struct Plan {
    Cost leaf, whole;
    std::size_t modulus = 0;
};

inline int fresh(int& top) {
    if (top == std::numeric_limits<int>::max())
        throw std::overflow_error("order sum exhausted variable IDs");
    return ++top;
}
inline void allocate(std::vector<int>& out, std::size_t size, int& top) {
    out.reserve(size);
    for (std::size_t i = 0; i < size; ++i) out.push_back(fresh(top));
}
inline void add_unary(Cnf& cnf, std::vector<int>& out,
                      const std::vector<int>& a, const std::vector<int>& b) {
    for (std::size_t j = 0; j < b.size(); ++j) cnf.add({-b[j], out[j]});
    for (std::size_t i = 0; i < a.size(); ++i) cnf.add({-a[i], out[i]});
    for (std::size_t i = 1; i <= a.size(); ++i)
        for (std::size_t j = 1; j <= b.size(); ++j)
            cnf.add({-a[i-1], -b[j-1], out[i+j-1]});
}

inline void add_modulo(int& top, Cnf& cnf, const std::vector<int>& quotient,
                      const std::vector<int>& remainder,
                      const std::vector<int>& aq, const std::vector<int>& ar,
                      const std::vector<int>& bq, const std::vector<int>& br,
                      std::size_t modulus) {
    const int carry = fresh(top);
    for (std::size_t j = 0; j < br.size(); ++j)
        cnf.add({-br[j], remainder[j], carry});
    for (std::size_t i = 0; i < ar.size(); ++i)
        cnf.add({-ar[i], remainder[i], carry});
    for (std::size_t i = 1; i <= ar.size(); ++i) {
        for (std::size_t j = 1; j <= br.size(); ++j) {
            const auto sum = i + j;
            if (sum < modulus) cnf.add({-ar[i-1], -br[j-1], remainder[sum-1], carry});
            else if (sum == modulus) cnf.add({-ar[i-1], -br[j-1], carry});
            else cnf.add({-ar[i-1], -br[j-1], remainder[sum % modulus - 1]});
        }
    }
    if (quotient.empty()) cnf.add({-carry});
    else cnf.add({-carry, quotient[0]});
    auto lift = [&](const std::vector<int>& child) {
        for (std::size_t i = 1; i <= child.size(); ++i) {
            if (i <= quotient.size()) cnf.add({-child[i-1], quotient[i-1]});
            else cnf.add({-child[i-1]});
            if (i < quotient.size()) cnf.add({-carry, -child[i-1], quotient[i]});
            else cnf.add({-carry, -child[i-1]});
        }
    };
    lift(bq);
    lift(aq);
    for (std::size_t i = 1; i <= aq.size(); ++i) {
        for (std::size_t j = 1; j <= bq.size(); ++j) {
            const auto sum = i + j;
            if (sum <= quotient.size()) cnf.add({-aq[i-1], -bq[j-1], quotient[sum-1]});
            else cnf.add({-aq[i-1], -bq[j-1]});
            std::vector<int> clause{-carry, -aq[i-1], -bq[j-1]};
            if (sum < quotient.size()) clause.push_back(quotient[sum]);
            cnf.add(std::move(clause));
        }
    }
}

inline void compare_modulo(Cnf& cnf, const std::vector<int>& quotient,
                           const std::vector<int>& remainder, std::size_t modulus, int bound) {
    const auto q = static_cast<std::size_t>(bound) / modulus;
    for (std::size_t j = static_cast<std::size_t>(bound) % modulus + 1; j < modulus; ++j) {
        if (q) cnf.add({-quotient[q-1], -remainder[j-1]});
        else cnf.add({-remainder[j-1]});
    }
}

inline Cost merged_cost(const Cost& a, const Cost& b, std::size_t p, int bound) {
    Cost out;
    out.capacity = a.capacity + b.capacity;
    out.quotient = std::min(out.capacity / p, static_cast<std::size_t>(bound) / p);
    out.remainder = std::min(p - 1, out.capacity);
    out.variables = a.variables + b.variables + out.quotient + out.remainder + 1;
    out.clauses = a.clauses + b.clauses + a.remainder + b.remainder
        + static_cast<std::uint64_t>(a.remainder) * b.remainder + 1
        + 2 * (a.quotient + b.quotient) + 2 * static_cast<std::uint64_t>(a.quotient) * b.quotient;
    return out;
}
inline Node merge(Node& a, Node& b, std::size_t p, int bound, int& top, Cnf& cnf) {
    Node out;
    out.capacity = a.capacity + b.capacity;
    allocate(out.quotient, std::min(out.capacity / p, static_cast<std::size_t>(bound) / p), top);
    allocate(out.remainder, std::min(p - 1, out.capacity), top);
    add_modulo(top, cnf, out.quotient, out.remainder, a.quotient, a.remainder, b.quotient, b.remainder, p);
    return out;
}

// Chain fragments are identified by position, independently of literal polarity.
class LeafBuilder {
    std::vector<int> inputs_;
    std::vector<std::size_t> ends_;
    bool ordered(std::size_t begin, std::size_t end) const {
        const auto it = std::upper_bound(ends_.begin(), ends_.end(), begin);
        return it != ends_.end() && end <= *it;
    }
    Cost small_cost(std::size_t begin, std::size_t end) const {
        Cost out;
        out.capacity = end - begin; out.remainder = out.capacity;
        if (out.capacity < 2 || ordered(begin, end)) return out;
        const auto mid = begin + (out.capacity + 1) / 2;
        const Cost a = small_cost(begin, mid), b = small_cost(mid, end);
        out.variables = a.variables + b.variables + out.capacity;
        out.clauses = a.clauses + b.clauses + out.capacity
            + static_cast<std::uint64_t>(a.capacity) * b.capacity;
        return out;
    }
    std::vector<int> small(std::size_t begin, std::size_t end, int& top, Cnf& cnf) const {
        const auto size = end - begin;
        if (size < 2 || ordered(begin, end))
            return {inputs_.begin() + begin, inputs_.begin() + end};
        const auto mid = begin + (size + 1) / 2;
        auto a = small(begin, mid, top, cnf), b = small(mid, end, top, cnf);
        std::vector<int> out;
        allocate(out, size, top);
        add_unary(cnf, out, a, b);
        return out;
    }
    Cost cost(std::size_t begin, std::size_t end, std::size_t p, int bound) const {
        if (end - begin < p) return small_cost(begin, end);
        const auto mid = begin + (end - begin + 1) / 2;
        return merged_cost(cost(begin, mid, p, bound), cost(mid, end, p, bound), p, bound);
    }
    Node build(std::size_t begin, std::size_t end, std::size_t p, int bound,
               int& top, Cnf& cnf) const {
        if (end - begin < p) {
            Node out; out.capacity = end - begin; out.remainder = small(begin, end, top, cnf);
            return out;
        }
        const auto mid = begin + (end - begin + 1) / 2;
        Node a = build(begin, mid, p, bound, top, cnf);
        Node b = build(mid, end, p, bound, top, cnf);
        return merge(a, b, p, bound, top, cnf);
    }
public:
    explicit LeafBuilder(const Chains& chains) {
        for (const auto& row : chains) {
            inputs_.insert(inputs_.end(), row.begin(), row.end());
            ends_.push_back(inputs_.size());
        }
    }
    explicit LeafBuilder(const std::vector<std::size_t>& widths) {
        std::size_t end = 0;
        for (const auto w : widths) {end += w; ends_.push_back(end);}
    }
    Cost cost(std::size_t p, int bound) const {
        return cost(0, ends_.back(), p, bound);
    }
    Node build(std::size_t p, int bound, int& top, Cnf& cnf) const {
        return build(0, inputs_.size(), p, bound, top, cnf);
    }
};

inline void interval(Cnf& cnf, const std::vector<int>& chain,
                     std::size_t lo, std::size_t hi, int conclusion) {
    if (lo >= chain.size() + 1 || hi < lo) return;
    hi = std::min(hi, chain.size());
    std::vector<int> clause;
    if (lo) clause.push_back(-chain[lo - 1]);
    if (hi < chain.size()) clause.push_back(chain[hi]);
    clause.push_back(conclusion);
    cnf.add(std::move(clause));
}
inline Node whole_leaf(const std::vector<int>& row, std::size_t p, int& top, Cnf& cnf) {
    Node out; out.capacity = row.size();
    if (row.size() < p) {out.remainder = row; return out;}
    for (std::size_t value = p; value <= row.size(); value += p)
        out.quotient.push_back(row[value - 1]);
    allocate(out.remainder, p - 1, top);
    for (std::size_t j = 1; j < p; ++j) {
        for (std::size_t block = 0; block <= row.size(); block += p) {
            interval(cnf, row, block, block + j - 1, -out.remainder[j - 1]);
            interval(cnf, row, block + j, block + p - 1, out.remainder[j - 1]);
        }
    }
    for (std::size_t j = 1; j < out.remainder.size(); ++j)
        cnf.add({-out.remainder[j], out.remainder[j - 1]});
    return out;
}
inline Cost whole_cost(const std::vector<std::size_t>& widths, std::size_t begin,
                       std::size_t end, std::size_t p, int bound) {
    if (end - begin == 1) {
        Cost out; out.capacity = widths[begin];
        out.quotient = out.capacity / p; out.remainder = std::min(p - 1, out.capacity);
        if (out.capacity >= p) {
            out.variables = p - 1;
            out.clauses = 2 * (out.capacity / p) * (p - 1) + 2 * p - 3 + out.capacity % p;
        }
        return out;
    }
    const auto mid = begin + (end - begin + 1) / 2;
    return merged_cost(whole_cost(widths, begin, mid, p, bound),
                       whole_cost(widths, mid, end, p, bound), p, bound);
}
inline Node whole(const Chains& rows, std::size_t begin, std::size_t end,
                  std::size_t p, int bound, int& top, Cnf& cnf) {
    if (end - begin == 1) return whole_leaf(rows[begin], p, top, cnf);
    const auto mid = begin + (end - begin + 1) / 2;
    Node a = whole(rows, begin, mid, p, bound, top, cnf);
    Node b = whole(rows, mid, end, p, bound, top, cnf);
    return merge(a, b, p, bound, top, cnf);
}
inline void capacities(const std::vector<std::size_t>& widths, std::size_t begin,
                       std::size_t end, std::vector<std::size_t>& out) {
    if (end - begin == 1) {out.push_back(widths[begin]); return;}
    const auto mid = begin + (end - begin + 1) / 2;
    capacities(widths, begin, mid, out); capacities(widths, mid, end, out);
    std::size_t total = 0;
    for (std::size_t i = begin; i < end; ++i) total += widths[i];
    out.push_back(total);
}
inline Cost with_comparison(Cost out, std::size_t p, int bound) {
    out.clauses += p > out.capacity ? 1 : p - 1 - static_cast<std::size_t>(bound) % p;
    return out;
}
inline std::size_t select_modulus(const std::vector<std::size_t>& widths, int bound) {
    std::vector<std::size_t> values;
    capacities(widths, 0, widths.size(), values); values.push_back(bound);
    const auto total = *std::max_element(values.begin(), values.end());
    std::set<std::size_t> candidates{2, total + 1};
    // Between changes to floor(capacity/p), every remaining term in the exact
    // cost is nondecreasing in p. Only the left ends of these intervals can win.
    // Jump between quotient intervals: O(sqrt(capacity)) events per capacity.
    for (const auto value : values) {
        for (std::size_t p = 2; p <= value;) {
            p = value / (value / p) + 1;
            candidates.insert(p);
        }
    }
    std::size_t selected = 2;
    Cost best = with_comparison(whole_cost(widths, 0, widths.size(), selected, bound), selected, bound);
    for (const auto p : candidates) {
        const auto candidate = with_comparison(whole_cost(widths, 0, widths.size(), p, bound), p, bound);
        if (candidate.clauses < best.clauses ||
            (candidate.clauses == best.clauses && candidate.variables < best.variables)) {
            selected = p; best = candidate;
        }
    }
    return selected;
}
inline std::size_t capacity(const std::vector<std::size_t>& widths) {
    std::size_t total = 0; for (const auto w : widths) total += w; return total;
}
inline bool simple_cost(const std::vector<std::size_t>& widths, int bound, Cost& out) {
    const auto total = capacity(widths);
    if (bound < 0) {out.clauses = 1; return true;}
    if (static_cast<std::size_t>(bound) >= total) return true;
    if (bound == 0) {out.clauses = widths.size(); return true;}
    if (widths.size() == 1 || static_cast<std::size_t>(bound) == total - 1) {
        out.clauses = 1; return true;
    }
    return false;
}
inline Plan assess(const std::vector<std::size_t>& widths, int bound) {
    Plan plan;
    if (simple_cost(widths, bound, plan.leaf)) {plan.whole = plan.leaf; return plan;}
    const auto p = std::max<std::size_t>(2, static_cast<std::size_t>(std::sqrt(bound)));
    plan.leaf = with_comparison(LeafBuilder(widths).cost(p, bound), p, bound);
    plan.modulus = select_modulus(widths, bound);
    plan.whole = with_comparison(whole_cost(widths, 0, widths.size(), plan.modulus, bound), plan.modulus, bound);
    return plan;
}
inline void encode(const Chains& rows, int bound, int mode, std::size_t forced_p,
                   int& top, Cnf& cnf) {
    std::vector<std::size_t> widths;
    for (const auto& row : rows) widths.push_back(row.size());
    const auto total = capacity(widths);
    if (bound < 0) {cnf.add({}); return;}
    if (static_cast<std::size_t>(bound) >= total) return;
    if (bound == 0) {for (const auto& row : rows) cnf.add({-row.front()}); return;}
    if (rows.size() == 1) {cnf.add({-rows.front()[bound]}); return;}
    if (static_cast<std::size_t>(bound) == total - 1) {
        std::vector<int> clause;
        for (const auto& row : rows) clause.push_back(-row.back());
        cnf.add(std::move(clause)); return;
    }
    const auto p = mode == 0 ? std::max<std::size_t>(2, static_cast<std::size_t>(std::sqrt(bound)))
        : (forced_p ? forced_p : select_modulus(widths, bound));
    Node root = mode == 0 ? LeafBuilder(rows).build(p, bound, top, cnf)
                          : whole(rows, 0, rows.size(), p, bound, top, cnf);
    if (p > total) cnf.add({-root.remainder[bound]});
    else compare_modulo(cnf, root.quotient, root.remainder, p, bound);
}
} // namespace integer_sum
