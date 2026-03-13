#include "structuredpb/gmto.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

namespace structuredpb {
namespace {

struct GroupTerm {
    int lit = 0;
    Weight weight = 0;
};

struct GroupData {
    std::vector<GroupTerm> terms;
};

struct DigitVector {
    std::vector<Weight> values;
    std::vector<int> lits;
};

struct Node {
    Weight total = 0;
    std::vector<Weight> reachable_sums;
    std::vector<DigitVector> digits;
    std::unique_ptr<Node> left;
    std::unique_ptr<Node> right;
};

struct EstimateNode {
    std::vector<Weight> reachable_sums;
    std::vector<std::vector<Weight>> digits;
    std::size_t clauses = 0;
    std::size_t vars = 0;
};

struct BeamState {
    std::vector<Weight> moduli;
    std::vector<Weight> residuals;
    Weight product = 1;
    long double score = 0.0L;
};

Weight safe_sum(Weight a, Weight b) {
    if (std::numeric_limits<Weight>::max() - a < b) {
        return std::numeric_limits<Weight>::max();
    }
    return a + b;
}

Weight safe_mul(Weight a, Weight b) {
    if (a == 0 || b == 0) {
        return 0;
    }
    if (std::numeric_limits<Weight>::max() / a < b) {
        return std::numeric_limits<Weight>::max();
    }
    return a * b;
}

Weight ceil_div(Weight a, Weight b) {
    return (a / b) + (a % b != 0 ? 1 : 0);
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

bool normalize_clause(Clause& clause) {
    std::sort(clause.begin(), clause.end());
    clause.erase(std::unique(clause.begin(), clause.end()), clause.end());
    for (std::size_t i = 1; i < clause.size(); ++i) {
        if (clause[i - 1] == -clause[i]) {
            return false;
        }
    }
    return !clause.empty();
}

void add_implication_clause(CnfFormula& cnf, const std::vector<int>& antecedent_lits, int out_lit) {
    Clause clause;
    clause.reserve(antecedent_lits.size() + (out_lit != 0 ? 1 : 0));
    for (int lit : antecedent_lits) {
        if (lit != 0) {
            clause.push_back(-lit);
        }
    }
    if (out_lit != 0) {
        clause.push_back(out_lit);
    }
    if (normalize_clause(clause)) {
        cnf.add_clause(std::move(clause));
    }
}

Weight clip_upper_value(Weight value, Weight upper_cap) {
    if (upper_cap == 0) {
        return value;
    }
    return std::min(value, upper_cap);
}

std::vector<Weight> distinct_sorted(std::vector<Weight> values) {
    values.erase(std::remove(values.begin(), values.end(), 0), values.end());
    std::sort(values.begin(), values.end());
    values.erase(std::unique(values.begin(), values.end()), values.end());
    return values;
}

std::vector<GroupData> preprocess_groups(const GroupedLeqConstraint& constraint, CnfFormula& cnf) {
    std::unordered_map<int, Weight> weight_by_lit;
    weight_by_lit.reserve(constraint.terms.size());
    for (const auto& term : constraint.terms) {
        weight_by_lit.emplace(term.lit, term.weight);
    }

    std::vector<GroupData> groups;
    groups.reserve(constraint.groups.size());
    for (const auto& group_lits : constraint.groups) {
        GroupData group;
        for (int lit : group_lits) {
            const Weight weight = weight_by_lit.at(lit);
            if (weight > constraint.bound) {
                cnf.add_clause({-lit});
                continue;
            }
            group.terms.push_back(GroupTerm{lit, weight});
        }
        if (!group.terms.empty()) {
            groups.push_back(std::move(group));
        }
    }
    return groups;
}

Weight total_group_capacity(const std::vector<GroupData>& groups) {
    Weight total = 0;
    for (const auto& group : groups) {
        Weight best = 0;
        for (const auto& term : group.terms) {
            best = std::max(best, term.weight);
        }
        total = safe_sum(total, best);
    }
    return total;
}

int max_input_var(const GroupedLeqConstraint& constraint) {
    int top = 0;
    for (const auto& term : constraint.terms) {
        top = std::max(top, std::abs(term.lit));
    }
    return top;
}

std::vector<Weight> decompose_number(Weight value, const std::vector<Weight>& moduli) {
    std::vector<Weight> digits;
    digits.reserve(moduli.size() + 1);
    Weight current = value;
    for (Weight modulus : moduli) {
        digits.push_back(current % modulus);
        current /= modulus;
    }
    digits.push_back(current);
    return digits;
}

std::vector<Weight> combine_reachable_sums(const std::vector<Weight>& left,
                                           const std::vector<Weight>& right,
                                           Weight strict_bound) {
    std::vector<Weight> out;
    out.reserve(left.size() * right.size());
    for (Weight a : left) {
        for (Weight b : right) {
            out.push_back(std::min(strict_bound, safe_sum(a, b)));
        }
    }
    std::sort(out.begin(), out.end());
    out.erase(std::unique(out.begin(), out.end()), out.end());
    return out;
}

std::vector<std::vector<Weight>> digit_domains_from_reachable(const std::vector<Weight>& reachable_sums,
                                                              const std::vector<Weight>& moduli,
                                                              Weight upper_cap) {
    std::vector<std::vector<Weight>> digits(moduli.size() + 1);
    for (Weight sum : reachable_sums) {
        if (sum == 0) {
            continue;
        }
        auto decomp = decompose_number(sum, moduli);
        for (std::size_t level = 0; level < decomp.size(); ++level) {
            Weight value = decomp[level];
            if (level + 1 == decomp.size()) {
                value = clip_upper_value(value, upper_cap);
            }
            if (value > 0) {
                digits[level].push_back(value);
            }
        }
    }
    for (auto& digit : digits) {
        digit = distinct_sorted(std::move(digit));
    }
    return digits;
}

int digit_lit(const DigitVector& digit, Weight value) {
    if (value == 0) {
        throw std::invalid_argument("structuredpb: digit value 0 does not correspond to a literal");
    }
    const auto it = std::lower_bound(digit.values.begin(), digit.values.end(), value);
    if (it == digit.values.end() || *it != value) {
        throw std::out_of_range("structuredpb: digit value missing in GMTO node");
    }
    return digit.lits[static_cast<std::size_t>(it - digit.values.begin())];
}

std::vector<Weight> factor_candidates(Weight value, Weight limit) {
    std::vector<Weight> out;
    if (value < 2) {
        return out;
    }
    for (Weight d = 2; d * d <= value && d <= limit; ++d) {
        if (value % d != 0) {
            continue;
        }
        out.push_back(d);
        const Weight other = value / d;
        if (other <= limit) {
            out.push_back(other);
        }
    }
    if (value <= limit) {
        out.push_back(value);
    }
    return distinct_sorted(std::move(out));
}

std::vector<Weight> build_divisibility_sequence(const std::vector<Weight>& weights,
                                                Weight strict_bound,
                                                Weight candidate_limit_cap) {
    if (strict_bound <= 4) {
        return {2};
    }

    std::vector<Weight> residuals = weights;
    std::vector<Weight> moduli;
    Weight product = 1;
    const std::size_t max_levels = 8;

    while (product < strict_bound && moduli.size() < max_levels) {
        const Weight remaining = ceil_div(strict_bound, product);
        const Weight candidate_limit = std::max<Weight>(2, std::min<Weight>(remaining, candidate_limit_cap));

        Weight best = 2;
        long double best_score = -1e300L;
        for (Weight candidate = 2; candidate <= candidate_limit; ++candidate) {
            std::vector<Weight> remainders;
            std::vector<Weight> quotients;
            remainders.reserve(residuals.size());
            quotients.reserve(residuals.size());
            std::size_t divisible = 0;
            for (Weight weight : residuals) {
                if (weight == 0) {
                    continue;
                }
                const Weight rem = weight % candidate;
                const Weight quo = weight / candidate;
                if (rem == 0) {
                    ++divisible;
                } else {
                    remainders.push_back(rem);
                }
                if (quo > 0) {
                    quotients.push_back(quo);
                }
            }
            remainders = distinct_sorted(std::move(remainders));
            quotients = distinct_sorted(std::move(quotients));
            const long double divisibility =
                residuals.empty() ? 0.0L : static_cast<long double>(divisible) / static_cast<long double>(residuals.size());
            const long double digit_penalty = static_cast<long double>(remainders.size());
            const long double upper_penalty = static_cast<long double>(quotients.size());
            const long double scale_bonus = std::log(static_cast<long double>(candidate) + 1.0L) / std::log(2.0L);
            const long double score = (divisibility * 1000.0L) - (digit_penalty * 10.0L) - upper_penalty + scale_bonus;
            if (score > best_score || (score == best_score && candidate > best)) {
                best_score = score;
                best = candidate;
            }
        }

        moduli.push_back(best);
        product = safe_mul(product, best);
        for (Weight& weight : residuals) {
            weight /= best;
        }

        bool all_zero = true;
        for (Weight weight : residuals) {
            if (weight != 0) {
                all_zero = false;
                break;
            }
        }
        if (all_zero && product >= strict_bound) {
            break;
        }
    }

    if (moduli.empty()) {
        moduli.push_back(2);
    }
    return moduli;
}

std::vector<Weight> build_equal_sequence(Weight strict_bound, std::size_t levels) {
    if (strict_bound <= 4) {
        return {2};
    }
    if (levels == 0) {
        levels = 1;
    }
    const long double exponent = 1.0L / static_cast<long double>(levels + 1);
    Weight base = static_cast<Weight>(std::ceil(std::pow(static_cast<long double>(strict_bound), exponent)));
    base = std::max<Weight>(2, base);
    std::vector<Weight> moduli(levels, base);
    Weight product = 1;
    for (Weight modulus : moduli) {
        product = safe_mul(product, modulus);
    }
    while (product < strict_bound) {
        moduli.back() += 1;
        product = safe_mul(product / std::max<Weight>(2, moduli.back() - 1), moduli.back());
    }
    return moduli;
}

void append_candidate(std::vector<std::vector<Weight>>& candidates, std::vector<Weight> candidate) {
    if (candidate.empty()) {
        return;
    }
    if (std::find(candidates.begin(), candidates.end(), candidate) == candidates.end()) {
        candidates.push_back(std::move(candidate));
    }
}

std::vector<Weight> next_modulus_candidates(const std::vector<Weight>& residuals, Weight remaining) {
    const Weight limit = std::max<Weight>(2, std::min<Weight>(remaining, 4096));
    std::vector<Weight> candidates;
    for (Weight v = 2; v <= std::min<Weight>(32, limit); ++v) {
        candidates.push_back(v);
    }

    Weight gcd_all = 0;
    for (Weight weight : residuals) {
        if (weight <= 1) {
            continue;
        }
        gcd_all = (gcd_all == 0) ? weight : std::gcd(gcd_all, weight);
    }
    if (gcd_all > 1) {
        auto gcd_factors = factor_candidates(gcd_all, limit);
        candidates.insert(candidates.end(), gcd_factors.begin(), gcd_factors.end());
    }

    std::vector<std::pair<std::size_t, Weight>> heavy;
    for (Weight weight : residuals) {
        if (weight > 1) {
            heavy.push_back({static_cast<std::size_t>(weight), weight});
        }
    }
    std::sort(heavy.begin(), heavy.end(), std::greater<>());
    for (std::size_t i = 0; i < std::min<std::size_t>(heavy.size(), 6); ++i) {
        auto factors = factor_candidates(heavy[i].second, limit);
        candidates.insert(candidates.end(), factors.begin(), factors.end());
    }

    for (std::size_t levels = 1; levels <= 6; ++levels) {
        const long double exponent = 1.0L / static_cast<long double>(levels + 1);
        Weight root = static_cast<Weight>(std::llround(std::pow(static_cast<long double>(remaining), exponent)));
        root = std::max<Weight>(2, std::min<Weight>(root, limit));
        candidates.push_back(root);
        if (root + 1 <= limit) {
            candidates.push_back(root + 1);
        }
    }

    return distinct_sorted(std::move(candidates));
}

BeamState advance_state(const BeamState& state, Weight modulus) {
    BeamState next = state;
    next.moduli.push_back(modulus);
    next.product = safe_mul(next.product, modulus);
    next.residuals.clear();
    next.residuals.reserve(state.residuals.size());

    std::vector<Weight> remainders;
    std::vector<Weight> quotients;
    remainders.reserve(state.residuals.size());
    quotients.reserve(state.residuals.size());
    std::size_t divisible = 0;
    for (Weight weight : state.residuals) {
        if (weight == 0) {
            next.residuals.push_back(0);
            continue;
        }
        const Weight rem = weight % modulus;
        const Weight quo = weight / modulus;
        next.residuals.push_back(quo);
        if (rem == 0) {
            ++divisible;
        } else {
            remainders.push_back(rem);
        }
        if (quo > 0) {
            quotients.push_back(quo);
        }
    }

    remainders = distinct_sorted(std::move(remainders));
    quotients = distinct_sorted(std::move(quotients));
    const long double divisibility =
        state.residuals.empty() ? 0.0L : static_cast<long double>(divisible) / static_cast<long double>(state.residuals.size());
    next.score += (divisibility * 1000.0L)
        - (static_cast<long double>(remainders.size()) * 12.0L)
        - (static_cast<long double>(quotients.size()) * 3.0L)
        + (std::log(static_cast<long double>(modulus) + 1.0L) / std::log(2.0L));
    return next;
}

EstimateNode estimate_tree(const std::vector<GroupData>& groups,
                           std::size_t begin,
                           std::size_t end,
                           const std::vector<Weight>& moduli,
                           Weight strict_bound,
                           Weight upper_cap) {
    EstimateNode node;
    if (end - begin == 1) {
        node.reachable_sums.push_back(0);
        for (const auto& term : groups[begin].terms) {
            node.reachable_sums.push_back(std::min(strict_bound, term.weight));
        }
        std::sort(node.reachable_sums.begin(), node.reachable_sums.end());
        node.reachable_sums.erase(std::unique(node.reachable_sums.begin(), node.reachable_sums.end()), node.reachable_sums.end());
        node.digits = digit_domains_from_reachable(node.reachable_sums, moduli, upper_cap);
        for (std::size_t level = 0; level < node.digits.size(); ++level) {
            for (Weight value : node.digits[level]) {
                std::size_t count = 0;
                for (const auto& term : groups[begin].terms) {
                    Weight digit = decompose_number(term.weight, moduli)[level];
                    if (level + 1 == node.digits.size()) {
                        digit = clip_upper_value(digit, upper_cap);
                    }
                    if (digit == value) {
                        ++count;
                    }
                }
                if (count > 1) {
                    node.vars += 1;
                    node.clauses += count;
                }
            }
        }
        return node;
    }

    const std::size_t mid = begin + (end - begin) / 2;
    EstimateNode left = estimate_tree(groups, begin, mid, moduli, strict_bound, upper_cap);
    EstimateNode right = estimate_tree(groups, mid, end, moduli, strict_bound, upper_cap);
    node.clauses = left.clauses + right.clauses;
    node.vars = left.vars + right.vars;
    node.reachable_sums = combine_reachable_sums(left.reachable_sums, right.reachable_sums, strict_bound);
    node.digits = digit_domains_from_reachable(node.reachable_sums, moduli, upper_cap);
    for (const auto& digit : node.digits) {
        node.vars += digit.size();
    }
    for (Weight left_sum : left.reachable_sums) {
        for (Weight right_sum : right.reachable_sums) {
            if (left_sum == 0 && right_sum == 0) {
                continue;
            }
            const Weight out_sum = std::min(strict_bound, safe_sum(left_sum, right_sum));
            const auto out_digits = decompose_number(out_sum, moduli);
            for (Weight digit : out_digits) {
                if (digit > 0) {
                    node.clauses += 1;
                }
            }
        }
    }
    return node;
}

std::vector<Weight> select_moduli(const std::vector<GroupData>& groups, Weight strict_bound) {
    std::vector<Weight> weights;
    for (const auto& group : groups) {
        for (const auto& term : group.terms) {
            weights.push_back(term.weight);
        }
    }

    std::vector<std::vector<Weight>> candidates;
    for (std::size_t levels = 1; levels <= 6; ++levels) {
        append_candidate(candidates, build_equal_sequence(strict_bound, levels));
    }
    append_candidate(candidates, build_divisibility_sequence(weights, strict_bound, 64));
    append_candidate(candidates, build_divisibility_sequence(weights, strict_bound, 256));
    append_candidate(candidates, build_divisibility_sequence(weights, strict_bound, 1024));

    std::vector<BeamState> frontier = {BeamState{{}, weights, 1, 0.0L}};
    const std::size_t beam_width = 8;
    const std::size_t max_levels = 8;
    for (std::size_t depth = 0; depth < max_levels; ++depth) {
        std::vector<BeamState> expanded;
        for (const BeamState& state : frontier) {
            if (state.product >= strict_bound) {
                append_candidate(candidates, state.moduli);
                expanded.push_back(state);
                continue;
            }
            const Weight remaining = ceil_div(strict_bound, state.product);
            const auto modulus_candidates = next_modulus_candidates(state.residuals, remaining);
            for (Weight modulus : modulus_candidates) {
                expanded.push_back(advance_state(state, modulus));
            }
        }
        std::sort(expanded.begin(), expanded.end(), [](const BeamState& a, const BeamState& b) {
            if (a.score != b.score) {
                return a.score > b.score;
            }
            return a.moduli.size() < b.moduli.size();
        });
        frontier.clear();
        for (const BeamState& state : expanded) {
            if (frontier.size() >= beam_width) {
                break;
            }
            frontier.push_back(state);
            if (state.product >= strict_bound) {
                append_candidate(candidates, state.moduli);
            }
        }
    }
    for (const BeamState& state : frontier) {
        append_candidate(candidates, state.moduli);
    }

    std::vector<Weight> best = candidates.front();
    std::size_t best_clauses = std::numeric_limits<std::size_t>::max();
    std::size_t best_vars = std::numeric_limits<std::size_t>::max();
    for (const auto& candidate : candidates) {
        const Weight candidate_upper_cap = decompose_number(strict_bound, candidate).back() + 1;
        const EstimateNode est = estimate_tree(groups, 0, groups.size(), candidate, strict_bound, candidate_upper_cap);
        if (est.clauses < best_clauses ||
            (est.clauses == best_clauses && est.vars < best_vars) ||
            (est.clauses == best_clauses && est.vars == best_vars && candidate.size() < best.size())) {
            best = candidate;
            best_clauses = est.clauses;
            best_vars = est.vars;
        }
    }
    return best;
}

Weight group_sort_key(const GroupData& group) {
    Weight best = 0;
    for (const auto& term : group.terms) {
        best = std::max(best, term.weight);
    }
    return best;
}

std::vector<GroupData> reorder_groups(std::vector<GroupData> groups, const std::vector<Weight>& moduli) {
    std::sort(groups.begin(), groups.end(), [&](const GroupData& a, const GroupData& b) {
        const auto da = decompose_number(group_sort_key(a), moduli);
        const auto db = decompose_number(group_sort_key(b), moduli);
        for (std::size_t rev = 0; rev < da.size(); ++rev) {
            const std::size_t idx = da.size() - 1 - rev;
            if (da[idx] != db[idx]) {
                return da[idx] > db[idx];
            }
        }
        return group_sort_key(a) > group_sort_key(b);
    });
    return groups;
}

std::unique_ptr<Node> build_tree(const std::vector<GroupData>& groups,
                                 std::size_t begin,
                                 std::size_t end,
                                 const std::vector<Weight>& moduli,
                                 Weight strict_bound,
                                 Weight upper_cap,
                                 VariableManager& varmgr,
                                 CnfFormula& cnf) {
    auto node = std::make_unique<Node>();

    if (end - begin == 1) {
        node->reachable_sums.push_back(0);
        for (const auto& term : groups[begin].terms) {
            node->reachable_sums.push_back(std::min(strict_bound, term.weight));
            node->total = std::max(node->total, term.weight);
        }
        std::sort(node->reachable_sums.begin(), node->reachable_sums.end());
        node->reachable_sums.erase(std::unique(node->reachable_sums.begin(), node->reachable_sums.end()), node->reachable_sums.end());
        std::vector<std::vector<Weight>> domains = digit_domains_from_reachable(node->reachable_sums, moduli, upper_cap);
        node->digits.resize(domains.size());
        for (std::size_t level = 0; level < domains.size(); ++level) {
            node->digits[level].values = domains[level];
            node->digits[level].lits.reserve(domains[level].size());
            for (Weight value : domains[level]) {
                std::vector<int> linked;
                for (const auto& term : groups[begin].terms) {
                    Weight digit = decompose_number(term.weight, moduli)[level];
                    if (level + 1 == domains.size()) {
                        digit = clip_upper_value(digit, upper_cap);
                    }
                    if (digit == value) {
                        linked.push_back(term.lit);
                    }
                }
                if (linked.empty()) {
                    throw std::logic_error("structuredpb: missing leaf digit source in GMTO");
                }
                if (linked.size() == 1) {
                    node->digits[level].lits.push_back(linked.front());
                } else {
                    const int aux = varmgr.new_var();
                    node->digits[level].lits.push_back(aux);
                    for (int lit : linked) {
                        cnf.add_clause({-lit, aux});
                    }
                }
            }
        }
        return node;
    }

    const std::size_t mid = begin + (end - begin) / 2;
    node->left = build_tree(groups, begin, mid, moduli, strict_bound, upper_cap, varmgr, cnf);
    node->right = build_tree(groups, mid, end, moduli, strict_bound, upper_cap, varmgr, cnf);
    node->total = safe_sum(node->left->total, node->right->total);
    node->reachable_sums = combine_reachable_sums(node->left->reachable_sums, node->right->reachable_sums, strict_bound);

    std::vector<std::vector<Weight>> domains = digit_domains_from_reachable(node->reachable_sums, moduli, upper_cap);
    node->digits.resize(domains.size());
    for (std::size_t level = 0; level < domains.size(); ++level) {
        node->digits[level].values = std::move(domains[level]);
        node->digits[level].lits.reserve(node->digits[level].values.size());
        for (std::size_t i = 0; i < node->digits[level].values.size(); ++i) {
            node->digits[level].lits.push_back(varmgr.new_var());
        }
    }

    for (Weight left_sum : node->left->reachable_sums) {
        const auto left_digits = decompose_number(left_sum, moduli);
        for (Weight right_sum : node->right->reachable_sums) {
            if (left_sum == 0 && right_sum == 0) {
                continue;
            }
            const auto right_digits = decompose_number(right_sum, moduli);
            const Weight out_sum = std::min(strict_bound, safe_sum(left_sum, right_sum));
            const auto out_digits = decompose_number(out_sum, moduli);

            std::vector<int> antecedent;
            antecedent.reserve(node->digits.size() * 2);
            for (std::size_t level = 0; level < node->digits.size(); ++level) {
                if (left_digits[level] > 0) {
                    Weight value = left_digits[level];
                    if (level + 1 == node->digits.size()) {
                        value = clip_upper_value(value, upper_cap);
                    }
                    antecedent.push_back(digit_lit(node->left->digits[level], value));
                }
                if (right_digits[level] > 0) {
                    Weight value = right_digits[level];
                    if (level + 1 == node->digits.size()) {
                        value = clip_upper_value(value, upper_cap);
                    }
                    antecedent.push_back(digit_lit(node->right->digits[level], value));
                }
            }

            for (std::size_t level = 0; level < node->digits.size(); ++level) {
                Weight value = out_digits[level];
                if (level + 1 == node->digits.size()) {
                    value = clip_upper_value(value, upper_cap);
                }
                if (value > 0) {
                    add_implication_clause(cnf, antecedent, digit_lit(node->digits[level], value));
                }
            }
        }
    }

    return node;
}

void add_comparator(const Node& root,
                    Weight strict_bound,
                    const std::vector<Weight>& moduli,
                    CnfFormula& cnf) {
    const auto bound_digits = decompose_number(strict_bound, moduli);
    const std::size_t levels = root.digits.size();

    for (std::size_t rev = 0; rev < levels; ++rev) {
        const std::size_t level = levels - 1 - rev;
        const Weight bound_value = bound_digits[level];
        const bool is_lowest = level == 0;

        std::vector<int> prefix;
        bool reachable_prefix = true;
        for (std::size_t higher = levels - 1; higher > level; --higher) {
            const Weight higher_bound = bound_digits[higher];
            if (higher_bound == 0) {
                continue;
            }
            const auto it = std::lower_bound(root.digits[higher].values.begin(),
                                             root.digits[higher].values.end(),
                                             higher_bound);
            if (it == root.digits[higher].values.end() || *it != higher_bound) {
                reachable_prefix = false;
                break;
            }
            prefix.push_back(-root.digits[higher].lits[static_cast<std::size_t>(it - root.digits[higher].values.begin())]);
        }
        if (!reachable_prefix) {
            continue;
        }

        if (is_lowest && bound_value == 0) {
            if (normalize_clause(prefix)) {
                cnf.add_clause(std::move(prefix));
            }
            continue;
        }

        for (std::size_t i = 0; i < root.digits[level].values.size(); ++i) {
            const Weight value = root.digits[level].values[i];
            const bool forbid = is_lowest ? (value >= bound_value) : (value > bound_value);
            if (!forbid) {
                continue;
            }
            Clause clause = prefix;
            clause.push_back(-root.digits[level].lits[i]);
            if (normalize_clause(clause)) {
                cnf.add_clause(std::move(clause));
            }
        }
    }
}

}  // namespace

EncodeResult GmtoEncoder::encode(const GroupedLeqConstraint& constraint,
                                 const EncodeOptions& options) const {
    constraint.validate();

    EncodeResult result;
    add_pairwise_amo(constraint, result.cnf);
    std::vector<GroupData> groups = preprocess_groups(constraint, result.cnf);

    const int input_top = max_input_var(constraint);
    const int base_top = std::max(input_top, options.top_id);
    result.cnf.num_vars = base_top;

    if (groups.empty()) {
        result.cnf.num_vars = std::max(result.cnf.num_vars, base_top);
        result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - base_top);
        result.stats.clauses = result.cnf.clauses.size();
        return result;
    }

    const Weight total = total_group_capacity(groups);
    if (total <= constraint.bound) {
        result.cnf.num_vars = std::max(result.cnf.num_vars, base_top);
        result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - base_top);
        result.stats.clauses = result.cnf.clauses.size();
        return result;
    }
    if (constraint.bound == std::numeric_limits<Weight>::max()) {
        result.cnf.num_vars = std::max(result.cnf.num_vars, base_top);
        result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - base_top);
        result.stats.clauses = result.cnf.clauses.size();
        return result;
    }

    const Weight strict_bound = constraint.bound + 1;
    const auto moduli = select_moduli(groups, strict_bound);
    const Weight upper_cap = decompose_number(strict_bound, moduli).back() + 1;
    groups = reorder_groups(std::move(groups), moduli);

    VariableManager varmgr(base_top);
    std::unique_ptr<Node> root = build_tree(groups, 0, groups.size(), moduli, strict_bound, upper_cap, varmgr, result.cnf);
    add_comparator(*root, strict_bound, moduli, result.cnf);

    result.cnf.num_vars = std::max(result.cnf.num_vars, varmgr.max_var());
    result.stats.auxiliary_variables = static_cast<std::size_t>(result.cnf.num_vars - base_top);
    result.stats.clauses = result.cnf.clauses.size();
    return result;
}

}  // namespace structuredpb
